"""Bastion Agent v3.1 — opsclaw 설계 원칙 기반

아키텍처 (3단계 상태 머신):
  PLANNING   → Playbook 우선 매칭 → 멀티스텝 Skill → 동적 Playbook 생성
  EXECUTING  → 파라미터 자동완성 → Pre-check → 실행 → Evidence 기록
  VALIDATING → LLM 결과 스트리밍 분석

품질 개선 (v3.1):
  1. Streaming   — LLM 응답을 토큰 단위로 실시간 출력
  2. 멀티스텝    — 한 요청에서 여러 Skill 순서 실행
  3. 동적 Playbook — 등록된 것 없으면 LLM이 즉석 생성
  4. 파라미터 자동완성 — role 이름 → IP 자동 변환
  5. Structured output — format:json 으로 파싱 신뢰도 향상
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
from typing import Generator

import httpx

from bastion.playbook import list_playbooks, load_playbook, run_playbook
from bastion.prompt import build_system_prompt, build_planning_prompt
from bastion.rag import build_index, format_context
from bastion.skills import SKILLS, execute_skill, preview_skill, skills_to_ollama_tools


# ── 입력 정제 ──────────────────────────────────────────────────────────────

def sanitize_text(text: str) -> str:
    """한글 IME 백스페이스 잔류 바이트·제어문자 제거."""
    result = []
    for ch in text:
        cp = ord(ch)
        if cp < 0x20 and ch not in ('\t', '\n'):
            continue
        if cp == 0x7F:
            continue
        cat = unicodedata.category(ch)
        if cat in ('Cc', 'Cf', 'Cs', 'Co', 'Cn'):
            continue
        result.append(ch)
    cleaned = re.sub(r'[\u00a0\u200b\u3000\ufeff]+', ' ', ''.join(result))
    return re.sub(r' {2,}', ' ', cleaned).strip()


# ── JSON 추출 (nested 대응) ────────────────────────────────────────────────

def extract_json(text: str) -> dict | None:
    """LLM 출력에서 JSON 객체 추출. 마크다운 코드블록·중첩 JSON 모두 처리."""
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```', '', text)
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    start = -1
    return None


def extract_json_array(text: str) -> list | None:
    """LLM 출력에서 JSON 배열 추출."""
    text = re.sub(r'```(?:json)?\s*', '', text)
    text = re.sub(r'```', '', text)
    stripped = text.strip()
    try:
        obj = json.loads(stripped)
        if isinstance(obj, list):
            return obj
        if isinstance(obj, dict):
            # {"skills": [...]} 또는 {"steps": [...]}
            for key in ("skills", "steps", "actions", "tasks"):
                if isinstance(obj.get(key), list):
                    return obj[key]
    except json.JSONDecodeError:
        pass
    # 배열 직접 탐색
    depth = 0
    start = -1
    for i, ch in enumerate(text):
        if ch == '[':
            if depth == 0:
                start = i
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0 and start >= 0:
                try:
                    obj = json.loads(text[start:i + 1])
                    if isinstance(obj, list):
                        return obj
                except json.JSONDecodeError:
                    start = -1
    return None


# ── Evidence DB ────────────────────────────────────────────────────────────

class EvidenceDB:
    """실행 기록 영속화 (SQLite) — evidence-first 원칙"""

    CREATE_SQL = """
    CREATE TABLE IF NOT EXISTS evidence (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp   TEXT    DEFAULT (datetime('now')),
        stage       TEXT,
        skill       TEXT,
        playbook_id TEXT,
        params      TEXT,
        success     INTEGER,
        exit_code   INTEGER,
        output      TEXT,
        analysis    TEXT,
        session_id  TEXT
    );
    CREATE TABLE IF NOT EXISTS assets (
        role        TEXT PRIMARY KEY,
        ip          TEXT,
        status      TEXT DEFAULT 'unknown',
        last_seen   TEXT,
        notes       TEXT
    )"""

    MIGRATIONS = [
        "ALTER TABLE evidence ADD COLUMN stage TEXT",
        "ALTER TABLE evidence ADD COLUMN playbook_id TEXT",
        "ALTER TABLE evidence ADD COLUMN exit_code INTEGER DEFAULT -1",
        "ALTER TABLE evidence ADD COLUMN session_id TEXT",
        "ALTER TABLE evidence ADD COLUMN course TEXT",
        "ALTER TABLE evidence ADD COLUMN lab_id TEXT",
        "ALTER TABLE evidence ADD COLUMN step_order INTEGER",
        "ALTER TABLE evidence ADD COLUMN test_session TEXT",
    ]

    def __init__(self, db_path: str = ""):
        self._conn = None  # persistent connection for :memory: mode
        self.db_path = ":memory:"
        for candidate in [
            db_path,
            os.path.join(os.getcwd(), "bastion_evidence.db"),
            os.path.join(os.path.expanduser("~"), "bastion_evidence.db"),
            "/tmp/bastion_evidence.db",
        ]:
            if not candidate:
                continue
            try:
                conn = sqlite3.connect(candidate)
                for stmt in self.CREATE_SQL.split(";"):
                    stmt = stmt.strip()
                    if stmt:
                        conn.execute(stmt)
                conn.commit()
                self._migrate(conn)
                conn.commit()
                conn.close()
                self.db_path = candidate
                return
            except Exception:
                continue
        # Fallback: persistent in-memory connection
        conn = sqlite3.connect(":memory:")
        for stmt in self.CREATE_SQL.split(";"):
            stmt = stmt.strip()
            if stmt:
                conn.execute(stmt)
        conn.commit()
        self._migrate(conn)
        conn.commit()
        self._conn = conn  # keep alive — :memory: is lost on close

    def _migrate(self, conn):
        """기존 DB에 누락 컬럼 추가 (idempotent)."""
        for sql in self.MIGRATIONS:
            try:
                conn.execute(sql)
            except sqlite3.OperationalError:
                pass  # 이미 존재하면 무시

    def _connect(self):
        """DB 연결 반환 — :memory: 모드에서는 영구 연결 재사용."""
        if self._conn is not None:
            return self._conn, False  # (conn, should_close)
        return sqlite3.connect(self.db_path), True

    def add(self, *, skill: str = "", playbook_id: str = "", params: dict = None,
            success: bool, exit_code: int = -1, output: str = "",
            analysis: str = "", stage: str = "", session_id: str = "",
            course: str = "", lab_id: str = "", step_order: int = 0,
            test_session: str = ""):
        conn, should_close = self._connect()
        try:
            # Ensure schema is up-to-date (e.g. old DB without stage column)
            self._migrate(conn)
            conn.execute(
                "INSERT INTO evidence "
                "(stage,skill,playbook_id,params,success,exit_code,output,analysis,"
                "session_id,course,lab_id,step_order,test_session) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (stage, skill, playbook_id,
                 json.dumps(params or {}, ensure_ascii=False),
                 int(success), exit_code,
                 output[:5000], analysis[:2000], session_id,
                 course, lab_id, step_order, test_session),
            )
            conn.commit()
            # 마지막 삽입 ID 반환 (테스트 추적용)
            row_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            if should_close:
                conn.close()
            return row_id
        except Exception:
            if should_close:
                conn.close()
            return None

    def recent(self, limit: int = 10) -> list[dict]:
        try:
            conn, should_close = self._connect()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM evidence ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
            result = [dict(r) for r in rows]
            if should_close:
                conn.close()
            return result
        except Exception:
            return []

    def search(self, keyword: str, limit: int = 5) -> list[dict]:
        try:
            conn, should_close = self._connect()
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM evidence WHERE skill LIKE ? OR output LIKE ? "
                "OR analysis LIKE ? OR playbook_id LIKE ? ORDER BY id DESC LIMIT ?",
                (f"%{keyword}%",) * 4 + (limit,),
            ).fetchall()
            result = [dict(r) for r in rows]
            if should_close:
                conn.close()
            return result
        except Exception:
            return []

    def stats(self) -> dict:
        try:
            conn, should_close = self._connect()
            total = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            success = conn.execute(
                "SELECT COUNT(*) FROM evidence WHERE success=1"
            ).fetchone()[0]
            if should_close:
                conn.close()
            return {"total": total, "success": success, "fail": total - success}
        except Exception:
            return {"total": 0, "success": 0, "fail": 0}

    def recent_context(self, limit: int = 3) -> str:
        records = self.recent(limit)
        if not records:
            return ""
        lines = ["[이전 실행 기록]"]
        for e in records:
            label = e.get("playbook_id") or e.get("skill") or "?"
            status = "성공" if e.get("success") else "실패"
            lines.append(f"- {label}: {status} | {(e.get('analysis') or '')[:80]}")
        return "\n".join(lines)

    def update_asset(self, role: str, ip: str, status: str, notes: str = ""):
        try:
            conn, should_close = self._connect()
            conn.execute(
                "INSERT OR REPLACE INTO assets (role, ip, status, last_seen, notes) "
                "VALUES (?, ?, ?, datetime('now'), ?)",
                (role, ip, status, notes),
            )
            conn.commit()
            if should_close:
                conn.close()
        except Exception:
            pass

    def get_assets(self) -> list[dict]:
        try:
            conn, should_close = self._connect()
            conn.row_factory = sqlite3.Row
            result = [dict(r) for r in conn.execute(
                "SELECT * FROM assets ORDER BY role"
            ).fetchall()]
            if should_close:
                conn.close()
            return result
        except Exception:
            return []


# ── Bastion Agent ──────────────────────────────────────────────────────────

class BastionAgent:
    """Bastion 에이전트 v3.1 — 3단계 상태 머신 + 5종 품질 개선"""

    def __init__(self, vm_ips: dict[str, str],
                 ollama_url: str = "", model: str = "",
                 knowledge_dir: str = "", evidence_db: str = ""):
        self.vm_ips = vm_ips
        from bastion import LLM_BASE_URL, LLM_MANAGER_MODEL
        self.ollama_url = (ollama_url or LLM_BASE_URL).rstrip("/")
        self.model = model or LLM_MANAGER_MODEL
        self.history: list[dict] = []
        self.session_id = f"s{int(time.time())}"
        self.evidence_db = EvidenceDB(evidence_db)
        self._test_meta: dict = {}  # 테스트 메타데이터 (course, lab_id, step_order, test_session)

        # Experience Learning Layer — 카테고리 수준 일반화 경험 학습
        from bastion.experience import ExperienceLearner
        self.experience = ExperienceLearner(db_path=self.evidence_db.db_path)

        self.rag_index = None
        kdir = knowledge_dir or os.path.join(os.path.dirname(__file__), "..", "..", "contents")
        if os.path.isdir(kdir):
            try:
                self.rag_index = build_index(kdir)
            except Exception:
                pass

    # ── Public API ──────────────────────────────────────────────────────────

    def chat(self, message: str, approval_callback=None) -> Generator[dict, None, None]:
        """자연어 메시지 처리 — 3단계 상태 머신 (Streaming 포함)"""
        message = sanitize_text(message)
        if not message:
            return
        self.history.append({"role": "user", "content": message})

        # History 압축 — 12턴 초과 시 오래된 6턴 LLM 요약 (4층 전략 간소화)
        self._compress_history()

        rag_ctx = ""
        if self.rag_index:
            chunks = self.rag_index.search(message, top_k=3)
            rag_ctx = format_context(chunks)
        prev_ctx = self.evidence_db.recent_context()
        exp_ctx = self.experience.get_context(message)

        # ══ STAGE 1: PLANNING ══════════════════════════════════════════════
        yield {"event": "stage", "stage": "planning"}

        # 1-a. 정적 Playbook 우선 (Playbooks are law)
        playbook_id = self._select_playbook(message)

        if playbook_id:
            yield {"event": "playbook_selected", "playbook_id": playbook_id,
                   "title": (load_playbook(playbook_id) or {}).get("title", "")}
            yield {"event": "stage", "stage": "executing"}

            pb_results = []
            for evt in run_playbook(playbook_id, self.vm_ips,
                                    ollama_url=self.ollama_url, model=self.model,
                                    approval_callback=approval_callback):
                yield evt
                if evt.get("event") == "step_done":
                    pb_results.append(evt)

            yield {"event": "stage", "stage": "validating"}
            analysis = yield from self._stream_analysis_events(
                message,
                [{"skill": r.get("name", ""), "success": r.get("success", False),
                  "output": r.get("output", "")} for r in pb_results],
            )
            passed = sum(1 for r in pb_results if r.get("success"))
            self.evidence_db.add(
                playbook_id=playbook_id, success=passed == len(pb_results),
                output="\n".join(r.get("output", "") for r in pb_results)[:3000],
                analysis=analysis, stage="playbook", session_id=self.session_id,
                **self._test_meta,
            )
            self.history.append({"role": "assistant", "content": analysis})
            return

        # 1-b. 멀티스텝 Skill 선택 (Tool Calling → JSON fallback)
        skill_steps = self._select_skills_multi(message, rag_ctx, prev_ctx, exp_ctx)

        # LLM이 target을 잘못 지정했을 수 있으므로 _infer_target_vm으로 보정
        if skill_steps:
            inferred_target = self._infer_target_vm(message)
            for i, (name, params) in enumerate(skill_steps):
                if name == "shell" and params.get("target") not in self.vm_ips:
                    params["target"] = inferred_target
                    skill_steps[i] = (name, params)

        if not skill_steps:
            # 1-c. 동적 Playbook 생성 (등록된 Playbook·Skill 매칭 없을 때)
            dyn_steps = self._generate_dynamic_playbook(message)
            if dyn_steps:
                yield {"event": "stage", "stage": "executing"}
                pb_results = []
                for evt in self._run_dynamic_steps(dyn_steps, "동적 Playbook"):
                    yield evt
                    if evt.get("event") == "step_done":
                        pb_results.append(evt)
                yield {"event": "stage", "stage": "validating"}
                analysis = yield from self._stream_analysis_events(message, pb_results)
                self.evidence_db.add(
                    playbook_id="dynamic", success=all(r.get("success") for r in pb_results),
                    output="\n".join(r.get("output", "") for r in pb_results)[:3000],
                    analysis=analysis, stage="dynamic_playbook", session_id=self.session_id,
                    **self._test_meta,
                )
                self.history.append({"role": "assistant", "content": analysis})
                return

            # 1-d. shell 자동 fallback — 실행 가능한 작업이면 Q&A 대신 shell로
            if self._should_execute(message):
                target = self._infer_target_vm(message)
                command = self._generate_shell_command(message, target)
                if command:
                    skill_steps = [("shell", {"target": target, "command": command})]
                    # → STAGE 2로 진행
                else:
                    # 명령어 생성 실패 → Q&A
                    yield {"event": "stage", "stage": "qa"}
                    response = yield from self._stream_qa_events(message)
                    self.history.append({"role": "assistant", "content": response})
                    return
            else:
                # 순수 Q&A
                yield {"event": "stage", "stage": "qa"}
                response = yield from self._stream_qa_events(message)
                self.history.append({"role": "assistant", "content": response})
                return

        # ══ STAGE 2: EXECUTING — 멀티스텝 Skill ═══════════════════════════
        yield {"event": "stage", "stage": "executing"}

        # Dry-run 미리보기: 실행 전 전체 계획을 보여줌
        previews = [preview_skill(n, p, self.vm_ips) for n, p in skill_steps]
        yield {"event": "plan_preview", "steps": previews}

        all_results = []
        for skill_name, params in skill_steps:
            # 파라미터 자동완성 (role→IP)
            params = self._enrich_params(skill_name, params)

            risk = self._assess_risk(skill_name, params)
            if risk == "high":
                yield {"event": "risk_warning", "skill": skill_name, "risk": risk}

            skill_def = SKILLS.get(skill_name, {})
            if (skill_def.get("requires_approval") or risk == "high") and approval_callback:
                if not approval_callback(skill_name, skill_name, params):
                    yield {"event": "skill_skip", "skill": skill_name, "reason": "User denied"}
                    continue

            pre_ok, pre_msg = self._pre_check(skill_name, params)
            if not pre_ok:
                yield {"event": "precheck_fail", "skill": skill_name, "message": pre_msg}
                yield {"event": "skill_skip", "skill": skill_name, "reason": pre_msg}
                all_results.append({"skill": skill_name, "params": params,
                                     "success": False, "output": f"pre-check failed: {pre_msg}"})
                continue

            yield {"event": "skill_start", "skill": skill_name, "params": params}
            result = execute_skill(skill_name, params, self.vm_ips, self.ollama_url, self.model)

            output = str(result.get("output", ""))
            success = result.get("success", False)
            exit_code = result.get("exit_code", -1 if not success else 0)

            yield {"event": "skill_result", "skill": skill_name,
                   "success": success, "output": output[:1000]}

            self.evidence_db.add(
                skill=skill_name, params=params, success=success,
                exit_code=exit_code, output=output,
                stage="skill", session_id=self.session_id,
                **self._test_meta,
            )
            all_results.append({"skill": skill_name, "params": params,
                                 "success": success, "output": output})

            # Experience Learning — 실행 결과를 카테고리 수준으로 일반화하여 축적
            self.experience.record(
                message=message, skill=skill_name,
                target_vm=params.get("target", ""),
                command=params.get("command", ""),
                success=success,
            )

            # Asset 상태 업데이트 (probe 계열)
            if skill_name in ("probe_host", "probe_all", "check_suricata",
                              "check_wazuh", "check_modsecurity"):
                self._update_assets_from_result(skill_name, params, success)

        # ══ STAGE 3: VALIDATING ════════════════════════════════════════════
        yield {"event": "stage", "stage": "validating"}
        analysis = yield from self._stream_analysis_events(message, all_results)
        self.history.append({"role": "assistant", "content": analysis})

        # Experience → Playbook 자동 승격 (10회마다 체크)
        stats = self.experience.stats()
        if stats.get("total_patterns", 0) % 10 == 0 and stats.get("total_patterns", 0) > 0:
            promoted = self.experience.promote_to_playbook()
            if promoted:
                yield {"event": "message", "message": f"경험 → Playbook 승격: {', '.join(promoted)}"}

    def get_skills(self) -> list[dict]:
        return [{"name": k, "description": v["description"],
                 "target_vm": v.get("target_vm", "auto"),
                 "requires_approval": v.get("requires_approval", False)}
                for k, v in SKILLS.items()]

    def get_playbooks(self) -> list[dict]:
        return list_playbooks()

    def get_evidence(self, limit: int = 10) -> list[dict]:
        return self.evidence_db.recent(limit)

    def search_evidence(self, keyword: str) -> list[dict]:
        return self.evidence_db.search(keyword)

    # ── Streaming helpers ───────────────────────────────────────────────────

    def _stream_llm(self, messages: list[dict],
                    max_tokens: int = 600, temperature: float = 0.3):
        """Streaming LLM 호출 — 토큰 단위로 yield."""
        try:
            with httpx.stream("POST", f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "options": {"temperature": temperature, "num_predict": max_tokens},
            }, timeout=90.0) as resp:
                for line in resp.iter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        token = data.get("message", {}).get("content", "")
                        if token:
                            yield token
                        if data.get("done"):
                            break
                    except (json.JSONDecodeError, KeyError):
                        continue
        except Exception as e:
            yield f"[스트림 오류: {e}]"

    def _stream_analysis_events(self, user_msg: str, results: list[dict]):
        """분석 결과를 stream_token 이벤트로 yield. 전체 텍스트 반환 (yield from 사용)."""
        # 각 스킬 결과를 명확히 구분 — 스킬명, 성패, 전체 출력
        parts = []
        for r in results:
            skill_name = r.get('skill', r.get('name', '?'))
            status = '성공' if r.get('success') else '실패'
            output = str(r.get('output', '')).strip()
            parts.append(f"## 스킬: {skill_name} ({status})\n{output[:2000]}")
        results_text = "\n\n".join(parts)

        messages = [
            {"role": "system",
             "content": (
                 "너는 사이버보안 전문가 Bastion 에이전트다.\n"
                 "규칙:\n"
                 "1. 출력에 있는 데이터를 있는 그대로 읽어라. 데이터가 있으면 '누락' '잘림' '없음'이라고 하지 마라.\n"
                 "2. 수치(CPU, 메모리, 디스크 %)를 반드시 포함해 요약해라.\n"
                 "3. 이상 징후가 있으면 구체적 행동을 추천해라.\n"
                 "4. 한국어로 답변해라. 5줄 이내."
             )},
            {"role": "user",
             "content": f"요청: {user_msg}\n\n실행 결과:\n{results_text}\n\n분석:"},
        ]
        yield {"event": "stream_start", "label": "분석"}
        full = ""
        for token in self._stream_llm(messages, max_tokens=600, temperature=0.1):
            yield {"event": "stream_token", "token": token}
            full += token
        yield {"event": "stream_end"}
        return full  # yield from으로 호출한 쪽에서 반환값 수신

    def _stream_qa_events(self, message: str):
        """Q&A 응답을 stream_token 이벤트로 yield. 전체 텍스트 반환."""
        messages = [
            {"role": "system",
             "content": (
                 "너는 사이버보안 전문가 Bastion 에이전트다. "
                 "한국어로 간결하고 정확하게 답변해."
             )},
        ] + self.history[-8:]
        yield {"event": "stream_start", "label": "답변"}
        full = ""
        for token in self._stream_llm(messages, max_tokens=600, temperature=0.3):
            yield {"event": "stream_token", "token": token}
            full += token
        yield {"event": "stream_end"}
        return full

    # ── PLANNING helpers ────────────────────────────────────────────────────

    # 구체적 명령어 패턴 — 이 패턴이 포함되면 Playbook 대신 Skill로 라우팅
    _CONCRETE_CMD_PATTERNS = re.compile(
        r'(curl\s|nmap\s|grep\s|sed\s|awk\s|systemctl\s|auditctl\s|chage\s|chmod\s|'
        r'docker\s|nft\s|hydra\s|nikto\s|sqlmap\s|ping\s|dig\s|nc\s|netcat\s|'
        r'python3\s|cat\s|echo\s|ls\s|find\s|tail\s|head\s|mkdir\s|useradd\s|usermod\s)',
        re.IGNORECASE
    )

    # 실행 가능한 작업 키워드 — 이 키워드가 있으면 Q&A가 아닌 shell 실행
    _EXEC_KEYWORDS = re.compile(
        r'(확인해줘|설정해줘|스캔해줘|실행해줘|점검해줘|테스트해줘|수행해줘|'
        r'조회해줘|추가해줘|삭제해줘|생성해줘|저장해줘|분석해줘|검색해줘|'
        r'활성화해줘|비활성화해줘|시작해줘|중지해줘|'
        r'확인하|설정하|스캔하|실행하|점검하|시오)',
        re.IGNORECASE
    )

    # VM 추론 패턴
    _VM_ROUTE_RULES = [
        (re.compile(r'attacker|nmap|hydra|nikto|sqlmap|searchsploit|metasploit|msfconsole', re.I), "attacker"),
        (re.compile(r'secu|방화벽|nftables|suricata|IDS|게이트웨이|감사|auditd|audit|패스워드|PAM|SSH.*설정|배너|rsyslog|sshd|login\.defs|chage|계정.*잠금|계정.*관리', re.I), "secu"),
        (re.compile(r'web|docker|apache|modsecurity|WAF|JuiceShop|DVWA|컨테이너|80|3000|8080', re.I), "web"),
        (re.compile(r'siem|wazuh|alerts|알림|에이전트.*목록|ossec|로그.*분석', re.I), "siem"),
        (re.compile(r'manager|ollama|LLM|python3.*스크립트|AI|가드레일|PII', re.I), "manager"),
    ]

    def _generate_shell_command(self, message: str, target_vm: str) -> str:
        """자연어 요청을 셸 명령어로 변환. LLM이 적절한 명령어를 생성한다."""
        # 메시지에 이미 구체적 명령어가 포함되어 있으면 추출
        cmd_match = self._CONCRETE_CMD_PATTERNS.search(message)
        if cmd_match:
            # 명령어 부분 추출 시도 — 전체 메시지가 명령어일 수 있음
            # "attacker에서 nmap -sV 10.20.30.80 실행해줘" → "nmap -sV 10.20.30.80"
            import re
            # VM 언급과 "에서" / "실행해줘" 같은 한국어 제거하고 명령어 부분만
            cleaned = re.sub(r'^.*?에서\s+', '', message)
            cleaned = re.sub(r'\s*(실행해줘|확인해줘|해줘|수행해줘|하시오).*$', '', cleaned)
            if cleaned and self._CONCRETE_CMD_PATTERNS.search(cleaned):
                return cleaned.strip()

        # LLM으로 명령어 생성
        vm_info = f"{target_vm} VM (IP: {self.vm_ips.get(target_vm, 'unknown')})"
        prompt = (
            f"다음 요청을 {vm_info}에서 실행할 셸 명령어 1줄로 변환하세요.\n"
            f"명령어만 출력하세요. 설명이나 주석은 붙이지 마세요.\n\n"
            f"요청: {message}\n\n명령어:"
        )
        try:
            r = httpx.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.0, "num_predict": 200},
            }, timeout=15.0)
            response = r.json().get("response", "").strip()
            # 마크다운 코드블록 제거
            import re
            response = re.sub(r'^```\w*\n?', '', response)
            response = re.sub(r'\n?```$', '', response)
            response = response.strip().split('\n')[0]  # 첫 줄만
            if response and not response.startswith('#'):
                return response
        except Exception:
            pass
        return ""

    def _should_execute(self, message: str) -> bool:
        """메시지가 실행 가능한 작업인지 판단."""
        # 구체적 명령어가 포함되면 무조건 실행
        if self._CONCRETE_CMD_PATTERNS.search(message):
            return True
        # 실행 키워드가 포함되면 실행
        if self._EXEC_KEYWORDS.search(message):
            return True
        return False

    def _infer_target_vm(self, message: str) -> str:
        """메시지에서 대상 VM role을 추론."""
        msg_lower = message.lower()
        # 명시적 VM 언급 확인
        for role in ["attacker", "secu", "web", "siem", "manager"]:
            if role in msg_lower:
                return role
        # 키워드 패턴 매칭
        for pattern, role in self._VM_ROUTE_RULES:
            if pattern.search(message):
                return role
        return "attacker"  # 기본값

    def _select_playbook(self, message: str) -> str | None:
        """LLM으로 정적 Playbook 매칭.
        구체적 명령어가 포함된 요청은 Playbook이 아닌 Skill로 라우팅."""
        # 구체적 명령어가 포함되면 Playbook 매칭 건너뜀
        if self._CONCRETE_CMD_PATTERNS.search(message):
            return None

        playbooks = list_playbooks()
        if not playbooks:
            return None
        pb_lines = "\n".join(
            f"- {p['playbook_id']}: {p['title']} — {p['description']}"
            for p in playbooks
        )
        prompt = (
            f"다음 Playbook 중 사용자 요청에 정확히 맞는 것을 선택하세요.\n"
            f"구체적인 명령어 실행 요청이면 반드시 'none'을 출력하세요.\n"
            f"없으면 정확히 'none' 만 출력하세요. 있으면 playbook_id 만 출력하세요.\n\n"
            f"Playbook:\n{pb_lines}\n\n"
            f"요청: {message}\n\nplaybook_id:"
        )
        try:
            r = httpx.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.0, "num_predict": 20},
            }, timeout=10.0)
            response = r.json().get("response", "").strip().lower()
            valid_ids = {p["playbook_id"] for p in playbooks}
            for word in re.split(r'[\s,]+', response):
                if word in valid_ids:
                    return word
        except Exception:
            pass
        return None

    def _select_skills_multi(self, message: str, rag_ctx: str,
                             prev_ctx: str, exp_ctx: str = "") -> list[tuple[str, dict]]:
        """멀티스텝 Skill 선택 — Tool Calling → JSON 배열 fallback."""
        system = build_planning_prompt(self.vm_ips, rag_ctx, prev_ctx, learned_context=exp_ctx)
        messages = [{"role": "system", "content": system}] + self.history[-8:]

        # ── 1차: Ollama Tool Calling (여러 tool_calls 지원) ────────────────
        try:
            r = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "tools": skills_to_ollama_tools(),
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 400},
            }, timeout=20.0)
            msg = r.json().get("message", {})
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                result = []
                for tc in tool_calls:
                    func = tc.get("function", {})
                    name = func.get("name", "")
                    args = func.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}
                    if name in SKILLS:
                        result.append((name, args))
                if result:
                    return result
        except Exception:
            pass

        # ── 2차: JSON 배열 fallback (format:json으로 신뢰도 향상) ──────────
        try:
            fallback_system = (
                f"{system}\n\n"
                "실행할 Skill을 JSON 배열로 출력 (순서대로 실행됨):\n"
                '[{"skill": "<name>", "params": {<key>: <val>}}]\n'
                "Skill이 필요 없으면 빈 배열: []"
            )
            r = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [{"role": "system", "content": fallback_system}]
                             + self.history[-6:],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1, "num_predict": 400},
            }, timeout=20.0)
            content = r.json().get("message", {}).get("content", "")
            items = extract_json_array(content)
            if items is not None:
                result = []
                for item in items:
                    if isinstance(item, dict):
                        name = item.get("skill", "")
                        args = item.get("params", {})
                        if name in SKILLS:
                            result.append((name, args if isinstance(args, dict) else {}))
                if result:
                    return result
                if items == []:
                    return []  # 명시적 빈 배열 → Q&A
        except Exception:
            pass

        return []

    def _generate_dynamic_playbook(self, message: str) -> list[dict]:
        """LLM이 요청 분석 → 동적 Playbook 스텝 생성 (format:json)."""
        skill_list = "\n".join(
            f"- {name}: {s['description']}"
            for name, s in SKILLS.items()
        )
        prompt = (
            f"사용자 요청을 분석하고 실행할 작업 단계를 JSON 배열로 생성하세요.\n"
            f"각 단계 형식: {{\"name\": \"단계 설명\", \"skill\": \"skill명\", \"params\": {{}}}}\n"
            f"Skill이 필요 없으면 빈 배열 [] 반환.\n\n"
            f"사용 가능한 Skill:\n{skill_list}\n\n"
            f"요청: {message}"
        )
        try:
            r = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "너는 보안 운영 에이전트다. JSON만 출력해."},
                    {"role": "user", "content": prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.0, "num_predict": 600},
            }, timeout=15.0)
            content = r.json().get("message", {}).get("content", "")
            items = extract_json_array(content)
            if items is not None:
                valid = []
                for step in items:
                    if isinstance(step, dict) and step.get("skill") in SKILLS:
                        valid.append(step)
                return valid
        except Exception:
            pass
        return []

    def _run_dynamic_steps(self, steps: list[dict],
                           title: str = "동적 Playbook") -> Generator[dict, None, None]:
        """동적으로 생성된 스텝 실행."""
        yield {"event": "playbook_start", "title": title, "total_steps": len(steps)}
        passed = 0
        for i, step in enumerate(steps, 1):
            skill_name = step.get("skill", "")
            params = self._enrich_params(skill_name, step.get("params", {}))
            name = step.get("name", skill_name)

            yield {"event": "step_start", "step": i, "name": name}
            result = execute_skill(skill_name, params, self.vm_ips, self.ollama_url, self.model)
            success = result.get("success", False)
            output = str(result.get("output", ""))
            if success:
                passed += 1
            self.evidence_db.add(
                skill=skill_name, params=params, success=success,
                output=output, stage="dynamic", session_id=self.session_id,
                **self._test_meta,
            )
            # Experience Learning
            self.experience.record(
                message=name, skill=skill_name,
                target_vm=params.get("target", ""),
                command=params.get("command", ""),
                success=success,
            )
            yield {"event": "step_done", "step": i, "name": name,
                   "success": success, "output": output}
        yield {"event": "playbook_done", "passed": passed, "total": len(steps)}

    # ── 파라미터 자동완성 ────────────────────────────────────────────────────

    def _enrich_params(self, skill_name: str, params: dict) -> dict:
        """role 이름 → IP 자동 변환, skill 고정 target_vm 자동 주입."""
        from bastion import INTERNAL_IPS
        enriched = dict(params)
        skill_def = SKILLS.get(skill_name, {})

        # role 이름을 IP로 변환 (target/host/ip 키)
        for key in ("target", "host", "ip"):
            val = str(enriched.get(key, ""))
            if val and not re.match(r'\d+\.\d+\.\d+\.\d+', val):
                ip = self.vm_ips.get(val) or INTERNAL_IPS.get(val, "")
                if ip:
                    enriched[key] = ip

        # skill에 고정 target_vm이 있으면 target/host 자동 채움
        target_vm = skill_def.get("target_vm", "")
        if target_vm and target_vm not in ("auto", "local"):
            ip = self.vm_ips.get(target_vm) or INTERNAL_IPS.get(target_vm, "")
            if ip:
                if "target" not in enriched:
                    enriched["target"] = ip
                if "host" not in enriched:
                    enriched["host"] = ip

        return enriched

    # ── EXECUTING helpers ───────────────────────────────────────────────────

    def _pre_check(self, skill_name: str, params: dict) -> tuple[bool, str]:
        """실행 전 타겟 VM 헬스 확인 (evidence-first)."""
        from bastion import health_check, INTERNAL_IPS
        skill_def = SKILLS.get(skill_name, {})
        target_vm = skill_def.get("target_vm", "auto")

        if target_vm == "local":
            return True, "local"

        ip = ""
        if target_vm == "auto":
            target = params.get("target", "")
            ip = self.vm_ips.get(target, INTERNAL_IPS.get(target, target))
        elif target_vm in self.vm_ips:
            ip = self.vm_ips[target_vm]
        elif target_vm in INTERNAL_IPS:
            ip = INTERNAL_IPS[target_vm]

        if not ip:
            return True, "ip unknown — skipping pre-check"

        h = health_check(ip)
        ok = h.get("status") == "healthy"
        return ok, f"{ip} {'healthy' if ok else 'unreachable'}"

    def _assess_risk(self, skill_name: str, params: dict) -> str:
        if skill_name in {"configure_nftables", "deploy_rule", "shell"}:
            return "high"
        if skill_name in {"scan_ports", "web_scan"}:
            return "medium"
        return "low"

    # ── History 압축 (4층 전략 간소화) ─────────────────────────────────────

    def _compress_history(self):
        """history > 12턴 시 오래된 6턴을 LLM 요약 → 1개 요약 메시지로 압축."""
        if len(self.history) <= 12:
            return
        to_compress = self.history[:6]
        self.history = self.history[6:]
        dialogue = "\n".join(
            f"[{m['role']}] {m['content'][:200]}"
            for m in to_compress
        )
        try:
            r = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "이전 대화를 3줄 이내로 한국어 요약해. 핵심 작업과 결과만 포함."},
                    {"role": "user", "content": dialogue},
                ],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 200},
            }, timeout=30.0)
            summary = r.json().get("message", {}).get("content", "")
            if summary:
                self.history.insert(0, {"role": "system", "content": f"[이전 대화 요약] {summary}"})
        except Exception:
            pass

    # ── Asset 추적 ───────────────────────────────────────────────────────────

    def _ip_to_role(self, ip: str) -> str:
        """IP → role 역방향 조회."""
        for role, r_ip in self.vm_ips.items():
            if r_ip == ip:
                return role
        from bastion import INTERNAL_IPS
        for role, r_ip in INTERNAL_IPS.items():
            if r_ip == ip:
                return role
        return ip  # 못 찾으면 IP 그대로

    def _update_assets_from_result(self, skill_name: str, params: dict, success: bool):
        """Skill 실행 결과로 Asset 상태 업데이트."""
        from bastion import INTERNAL_IPS
        status = "online" if success else "unreachable"
        if skill_name == "probe_all":
            for role, ip in self.vm_ips.items():
                self.evidence_db.update_asset(role, ip, status)
        elif skill_name == "probe_host":
            target = params.get("target", "")
            # target이 IP일 수도 있으므로 role로 역조회
            if target in self.vm_ips:
                role, ip = target, self.vm_ips[target]
            else:
                ip = target
                role = self._ip_to_role(ip)
            self.evidence_db.update_asset(role, ip, status)
        elif skill_name == "check_suricata":
            ip = self.vm_ips.get("secu", INTERNAL_IPS.get("secu", ""))
            self.evidence_db.update_asset("secu", ip, status, "Suricata 점검")
        elif skill_name == "check_wazuh":
            ip = self.vm_ips.get("siem", INTERNAL_IPS.get("siem", ""))
            self.evidence_db.update_asset("siem", ip, status, "Wazuh 점검")
        elif skill_name == "check_modsecurity":
            ip = self.vm_ips.get("web", INTERNAL_IPS.get("web", ""))
            self.evidence_db.update_asset("web", ip, status, "ModSecurity 점검")
        elif skill_name in ("probe_host", "onboard"):
            role = params.get("role") or params.get("target", "")
            ip = params.get("ip") or self.vm_ips.get(role, INTERNAL_IPS.get(role, ""))
            if role and ip:
                notes = "온보딩 완료" if skill_name == "onboard" else ""
                self.evidence_db.update_asset(role, ip, status, notes)
