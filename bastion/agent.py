"""Bastion Agent v3 — opsclaw 설계 원칙 기반

아키텍처 (3단계 상태 머신):
  PLANNING   → Playbook 우선 매칭, 없으면 Tool Calling으로 Skill 선택
  EXECUTING  → Pre-check(헬스) → 실행 → Evidence 기록
  VALIDATING → LLM 결과 분석 → 요약 → 다음 행동 추천

opsclaw 핵심 원칙 반영:
  - "Playbooks are law" : LLM은 선택/파라미터만, 즉흥 실행 금지
  - Evidence-first      : 실행 전 pre-check, 실행 후 output 검증
  - Tool Calling        : Ollama native function calling (수동 JSON 파싱 제거)
  - Asset-first         : VM은 role 기반 asset으로 참조
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import time
import unicodedata
from typing import Any, Generator

import httpx

from bastion.playbook import list_playbooks, load_playbook, run_playbook
from bastion.prompt import build_system_prompt, build_planning_prompt
from bastion.rag import build_index, format_context
from bastion.skills import SKILLS, execute_skill, skills_to_ollama_tools


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
    )"""

    def __init__(self, db_path: str = ""):
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
                with sqlite3.connect(candidate) as conn:
                    conn.execute(self.CREATE_SQL)
                self.db_path = candidate
                return
            except Exception:
                continue
        with sqlite3.connect(":memory:") as conn:
            conn.execute(self.CREATE_SQL)

    def add(self, *, skill: str = "", playbook_id: str = "", params: dict = None,
            success: bool, exit_code: int = -1, output: str = "",
            analysis: str = "", stage: str = "", session_id: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT INTO evidence "
                "(stage,skill,playbook_id,params,success,exit_code,output,analysis,session_id) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (stage, skill, playbook_id,
                 json.dumps(params or {}, ensure_ascii=False),
                 int(success), exit_code,
                 output[:5000], analysis[:2000], session_id),
            )

    def recent(self, limit: int = 10) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM evidence ORDER BY id DESC LIMIT ?", (limit,)
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def search(self, keyword: str, limit: int = 5) -> list[dict]:
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM evidence WHERE skill LIKE ? OR output LIKE ? "
                    "OR analysis LIKE ? OR playbook_id LIKE ? ORDER BY id DESC LIMIT ?",
                    (f"%{keyword}%",) * 4 + (limit,),
                ).fetchall()
            return [dict(r) for r in rows]
        except Exception:
            return []

    def stats(self) -> dict:
        try:
            with sqlite3.connect(self.db_path) as conn:
                total = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
                success = conn.execute(
                    "SELECT COUNT(*) FROM evidence WHERE success=1"
                ).fetchone()[0]
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
            analysis_snippet = (e.get("analysis") or "")[:80]
            lines.append(f"- {label}: {status} | {analysis_snippet}")
        return "\n".join(lines)


# ── Bastion Agent ──────────────────────────────────────────────────────────

class BastionAgent:
    """Bastion 에이전트 v3 — 3단계 상태 머신 (PLANNING→EXECUTING→VALIDATING)"""

    def __init__(self, vm_ips: dict[str, str],
                 ollama_url: str = "", model: str = "",
                 knowledge_dir: str = "", evidence_db: str = ""):
        self.vm_ips = vm_ips
        self.ollama_url = (ollama_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")).rstrip("/")
        self.model = model or os.getenv("LLM_MANAGER_MODEL", os.getenv("LLM_MODEL", "gpt-oss:120b"))
        self.history: list[dict] = []
        self.session_id = f"s{int(time.time())}"
        self.evidence_db = EvidenceDB(evidence_db)

        self.rag_index = None
        kdir = knowledge_dir or os.path.join(os.path.dirname(__file__), "..", "contents")
        if os.path.isdir(kdir):
            try:
                self.rag_index = build_index(kdir)
            except Exception:
                pass

    # ── Public API ──────────────────────────────────────────────────────────

    def chat(self, message: str, approval_callback=None) -> Generator[dict, None, None]:
        """자연어 메시지 처리 — 3단계 상태 머신"""
        message = sanitize_text(message)
        if not message:
            return
        self.history.append({"role": "user", "content": message})

        rag_ctx = ""
        if self.rag_index:
            chunks = self.rag_index.search(message, top_k=3)
            rag_ctx = format_context(chunks)

        prev_ctx = self.evidence_db.recent_context()

        # ══ STAGE 1: PLANNING ══════════════════════════════════════════════
        yield {"event": "stage", "stage": "planning"}

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
            analysis = self._analyze(
                message,
                [{"skill": r.get("name", ""), "success": r.get("success", False),
                  "output": r.get("output", "")} for r in pb_results],
            )
            yield {"event": "analysis", "content": analysis}

            passed = sum(1 for r in pb_results if r.get("success"))
            self.evidence_db.add(
                playbook_id=playbook_id, success=passed == len(pb_results),
                output="\n".join(r.get("output", "") for r in pb_results)[:3000],
                analysis=analysis, stage="playbook", session_id=self.session_id,
            )
            self.history.append({"role": "assistant", "content": analysis})
            return

        skill_name, params = self._select_skill(message, rag_ctx, prev_ctx)

        if not skill_name:
            yield {"event": "stage", "stage": "qa"}
            response = self._plain_chat(message)
            yield {"event": "message", "content": response}
            self.history.append({"role": "assistant", "content": response})
            return

        # ══ STAGE 2: EXECUTING (Skill) ═════════════════════════════════════
        yield {"event": "stage", "stage": "executing"}

        risk = self._assess_risk(skill_name, params)
        if risk == "high":
            yield {"event": "risk_warning", "skill": skill_name, "risk": risk, "params": params}

        skill_def = SKILLS.get(skill_name, {})
        if (skill_def.get("requires_approval") or risk == "high") and approval_callback:
            if not approval_callback(skill_name, skill_name, params):
                yield {"event": "skill_skip", "skill": skill_name, "reason": "User denied"}
                return

        pre_ok, pre_msg = self._pre_check(skill_name, params)
        if not pre_ok:
            yield {"event": "precheck_fail", "skill": skill_name, "message": pre_msg}

        yield {"event": "skill_start", "skill": skill_name, "params": params}
        result = execute_skill(skill_name, params, self.vm_ips, self.ollama_url, self.model)

        output = str(result.get("output", ""))
        success = result.get("success", False)
        exit_code = result.get("exit_code", -1 if not success else 0)

        yield {"event": "skill_result", "skill": skill_name,
               "success": success, "output": output[:1000]}

        # ══ STAGE 3: VALIDATING ════════════════════════════════════════════
        yield {"event": "stage", "stage": "validating"}

        analysis = self._analyze(message, [{"skill": skill_name, "params": params,
                                             "success": success, "output": output}])
        yield {"event": "analysis", "content": analysis}

        self.evidence_db.add(
            skill=skill_name, params=params, success=success,
            exit_code=exit_code, output=output, analysis=analysis,
            stage="skill", session_id=self.session_id,
        )
        self.history.append({"role": "assistant", "content": analysis})

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

    # ── PLANNING helpers ────────────────────────────────────────────────────

    def _select_playbook(self, message: str) -> str | None:
        playbooks = list_playbooks()
        if not playbooks:
            return None
        pb_lines = "\n".join(
            f"- {p['playbook_id']}: {p['title']} — {p['description']}"
            for p in playbooks
        )
        prompt = (
            f"다음 등록된 Playbook 중 사용자 요청에 가장 적합한 것을 선택하세요.\n"
            f"해당하는 것이 없으면 정확히 'none' 만 출력하세요.\n"
            f"있으면 playbook_id 만 출력하세요 (설명 없이).\n\n"
            f"등록된 Playbook:\n{pb_lines}\n\n"
            f"사용자 요청: {message}\n\n"
            f"playbook_id:"
        )
        try:
            r = httpx.post(f"{self.ollama_url}/api/generate", json={
                "model": self.model, "prompt": prompt, "stream": False,
                "options": {"temperature": 0.0, "num_predict": 20},
            }, timeout=30.0)
            response = r.json().get("response", "").strip().lower()
            valid_ids = {p["playbook_id"] for p in playbooks}
            for word in re.split(r'[\s,]+', response):
                if word in valid_ids:
                    return word
        except Exception:
            pass
        return None

    def _select_skill(self, message: str, rag_ctx: str,
                      prev_ctx: str) -> tuple[str | None, dict]:
        system = build_planning_prompt(self.vm_ips, rag_ctx, prev_ctx)
        messages = [{"role": "system", "content": system}] + self.history[-8:]

        try:
            r = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": messages,
                "tools": skills_to_ollama_tools(),
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300},
            }, timeout=60.0)
            msg = r.json().get("message", {})
            tool_calls = msg.get("tool_calls", [])
            if tool_calls:
                func = tool_calls[0].get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                if name in SKILLS:
                    return name, args
        except Exception:
            pass

        try:
            fallback_system = (
                f"{system}\n\n"
                "Skill 실행이 필요하면 JSON만 출력:\n"
                '{"skill": "<name>", "params": {<key>: <val>}}\n'
                "Skill이 필요 없으면 빈 JSON: {}"
            )
            r = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [{"role": "system", "content": fallback_system}]
                             + self.history[-6:],
                "stream": False,
                "options": {"temperature": 0.1, "num_predict": 300},
            }, timeout=60.0)
            content = r.json().get("message", {}).get("content", "")
            parsed = extract_json(content)
            if parsed:
                name = parsed.get("skill", "")
                args = parsed.get("params", {})
                if name in SKILLS:
                    return name, args
        except Exception:
            pass

        return None, {}

    # ── EXECUTING helpers ───────────────────────────────────────────────────

    def _pre_check(self, skill_name: str, params: dict) -> tuple[bool, str]:
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
        high = {"configure_nftables", "deploy_rule", "shell"}
        medium = {"scan_ports", "web_scan"}
        if skill_name in high:
            return "high"
        if skill_name in medium:
            return "medium"
        return "low"

    # ── VALIDATING helpers ──────────────────────────────────────────────────

    def _analyze(self, user_msg: str, results: list[dict]) -> str:
        results_text = "\n".join(
            f"[{r.get('skill', r.get('name', '?'))}] "
            f"{'성공' if r.get('success') else '실패'}: "
            f"{str(r.get('output', ''))[:300]}"
            for r in results
        )
        try:
            resp = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [
                    {"role": "system",
                     "content": (
                         "너는 사이버보안 전문가 Bastion 에이전트다. "
                         "실행 결과를 분석하고 3줄 이내로 한국어 요약해. "
                         "이상 징후가 있으면 다음 행동을 추천해."
                     )},
                    {"role": "user",
                     "content": f"요청: {user_msg}\n\n결과:\n{results_text}\n\n분석:"},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 300},
            }, timeout=60.0)
            return resp.json().get("message", {}).get("content", "분석 실패")
        except Exception as e:
            return f"분석 불가: {e}"

    def _plain_chat(self, message: str) -> str:
        try:
            resp = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [
                    {"role": "system",
                     "content": (
                         "너는 사이버보안 전문가 Bastion 에이전트다. "
                         "한국어로 간결하고 정확하게 답변해."
                     )},
                ] + self.history[-8:],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 600},
            }, timeout=60.0)
            return resp.json().get("message", {}).get("content", "응답 없음")
        except Exception as e:
            return f"LLM 연결 실패: {e}"

    def _call_llm(self, messages: list[dict], max_tokens: int = 500) -> dict:
        r = httpx.post(f"{self.ollama_url}/api/chat", json={
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }, timeout=90.0)
        return r.json()
