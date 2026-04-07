"""Bastion Agent 코어 — 자연어 대화 + Skill/Playbook 실행 + 결과 분석

1. LLM이 skill/playbook 선택 (프롬프트 기반 JSON) — 멀티스텝 체이닝 지원
2. SubAgent A2A로 실제 실행
3. LLM이 결과 분석 + 추천
4. Evidence DB에 영속화
"""
from __future__ import annotations
import os
import json
import re
import time
import sqlite3
from typing import Any, Generator

import httpx

from bastion.skills import SKILLS, execute_skill
from bastion.playbook import list_playbooks, run_playbook, load_playbook
from bastion.prompt import build_system_prompt
from bastion.rag import build_index, format_context


def _skills_for_prompt() -> str:
    lines = []
    for name, s in SKILLS.items():
        params_desc = ", ".join(f"{k}: {v.get('type','str')}" for k, v in s.get("params", {}).items())
        approval = " [승인필요]" if s.get("requires_approval") else ""
        lines.append(f'  - {name}({params_desc}): {s["description"]}{approval}')
    return "\n".join(lines)


# ── Evidence DB ─────────────────────────────────

class EvidenceDB:
    """실행 기록 영속화 (SQLite)"""

    def __init__(self, db_path: str = ""):
        self.db_path = db_path or os.path.join(os.path.dirname(__file__), "..", "..", "bastion_evidence.db")
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT (datetime('now')),
                    skill TEXT, params TEXT, success INTEGER,
                    output TEXT, analysis TEXT, session_id TEXT
                )""")
        except Exception:
            self.db_path = ":memory:"
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS evidence (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT DEFAULT (datetime('now')),
                    skill TEXT, params TEXT, success INTEGER,
                    output TEXT, analysis TEXT, session_id TEXT
                )""")

    def add(self, skill: str, params: dict, success: bool, output: str, analysis: str = "", session_id: str = ""):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("INSERT INTO evidence (skill, params, success, output, analysis, session_id) VALUES (?,?,?,?,?,?)",
                         (skill, json.dumps(params, ensure_ascii=False), int(success), output[:5000], analysis[:2000], session_id))

    def recent(self, limit: int = 10) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM evidence ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search(self, keyword: str, limit: int = 5) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT * FROM evidence WHERE skill LIKE ? OR output LIKE ? OR analysis LIKE ? ORDER BY id DESC LIMIT ?",
                                (f"%{keyword}%", f"%{keyword}%", f"%{keyword}%", limit)).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            total = conn.execute("SELECT COUNT(*) FROM evidence").fetchone()[0]
            success = conn.execute("SELECT COUNT(*) FROM evidence WHERE success=1").fetchone()[0]
        return {"total": total, "success": success, "fail": total - success}


class BastionAgent:
    """Bastion 에이전트 v2 — 결과 분석, 체이닝, Evidence DB, RAG"""

    def __init__(self, vm_ips: dict[str, str],
                 ollama_url: str = "", model: str = "",
                 knowledge_dir: str = "", evidence_db: str = ""):
        self.vm_ips = vm_ips
        self.ollama_url = ollama_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("LLM_MANAGER_MODEL", os.getenv("LLM_MODEL", "gpt-oss:120b"))
        self.history: list[dict] = []
        self.session_id = f"s{int(time.time())}"

        # Evidence DB
        self.evidence_db = EvidenceDB(evidence_db)

        # RAG
        self.rag_index = None
        kdir = knowledge_dir or os.path.join(os.path.dirname(__file__), "..", "..", "contents")
        if os.path.isdir(kdir):
            try:
                self.rag_index = build_index(kdir)
            except Exception:
                pass

    def chat(self, message: str, approval_callback=None) -> Generator[dict, None, None]:
        """자연어 메시지 처리 → skill/playbook 실행 → 결과 분석 → 스트리밍"""
        self.history.append({"role": "user", "content": message})

        # Playbook 직접 요청
        pb_match = re.search(r'playbook[:\s]+(\w+)', message, re.IGNORECASE)
        if pb_match:
            pb = load_playbook(pb_match.group(1))
            if pb:
                yield {"event": "message", "content": f"Playbook '{pb['title']}' 실행합니다."}
                yield from run_playbook(pb_match.group(1), self.vm_ips, ollama_url=self.ollama_url,
                                        model=self.model, approval_callback=approval_callback)
                return

        # RAG 검색
        rag_context = ""
        if self.rag_index:
            chunks = self.rag_index.search(message, top_k=3)
            rag_context = format_context(chunks)

        # 이전 실행 컨텍스트 (대화 연속성)
        prev_context = self._build_prev_context()

        # LLM에게 skill 선택 요청 — 멀티스텝 체이닝 지원
        system_prompt = build_system_prompt(self.vm_ips, extra_context=rag_context)
        skill_prompt = f"""{system_prompt}

{prev_context}

사용자 요청에 대해 다음 중 하나로 응답하세요:

1) skill 실행이 필요하면 JSON 형식으로 응답. 여러 skill을 순서대로 실행하려면 배열로:
단일: {{"skill": "skill_name", "params": {{"param1": "value1"}}}}
멀티: {{"steps": [{{"skill": "skill1", "params": {{}}}}, {{"skill": "skill2", "params": {{}}}}]}}

사용 가능한 skill:
{_skills_for_prompt()}

2) skill이 필요 없는 일반 질문이면 한국어로 직접 답변.

중요: skill을 사용할 때는 JSON만 출력. 위험도가 높은 작업은 반드시 승인 필요 skill을 사용."""

        try:
            response = self._call_llm(skill_prompt)
        except Exception as e:
            yield {"event": "error", "content": f"LLM 연결 실패: {e}"}
            return

        content = response.get("message", {}).get("content", "").strip()
        parsed = self._extract_skill_call(content)

        if parsed:
            # 멀티스텝 체이닝 지원
            steps = parsed.get("steps", [parsed]) if "steps" in parsed else [parsed]

            all_results = []
            for step in steps:
                skill_name = step.get("skill", "")
                params = step.get("params", {})

                if skill_name not in SKILLS:
                    yield {"event": "message", "content": f"알 수 없는 skill: {skill_name}"}
                    continue

                # 위험도 평가
                risk = self._assess_risk(skill_name, params)
                if risk == "high":
                    yield {"event": "risk_warning", "skill": skill_name, "risk": risk, "params": params}

                # 승인
                skill_def = SKILLS.get(skill_name, {})
                if (skill_def.get("requires_approval") or risk == "high") and approval_callback:
                    if not approval_callback(skill_name, skill_name, params):
                        yield {"event": "skill_skip", "skill": skill_name, "reason": "User denied"}
                        continue

                yield {"event": "skill_start", "skill": skill_name, "params": params}

                result = execute_skill(skill_name, params, self.vm_ips, self.ollama_url, self.model)
                output = str(result.get("output", ""))[:2000]
                success = result.get("success", False)

                yield {"event": "skill_result", "skill": skill_name, "success": success, "output": output[:1000]}

                all_results.append({"skill": skill_name, "params": params, "success": success, "output": output})

            # 결과 LLM 분석
            if all_results:
                analysis = self._analyze_results(message, all_results)
                yield {"event": "analysis", "content": analysis}

                # Evidence DB 저장
                for r in all_results:
                    self.evidence_db.add(
                        skill=r["skill"], params=r["params"], success=r["success"],
                        output=r["output"], analysis=analysis, session_id=self.session_id,
                    )

                self.history.append({"role": "assistant", "content": analysis})
        else:
            yield {"event": "message", "content": content}
            self.history.append({"role": "assistant", "content": content})

    def _call_llm(self, system_prompt: str, max_tokens: int = 500) -> dict:
        """Ollama API 호출"""
        messages = [{"role": "system", "content": system_prompt}]
        messages += self.history[-10:]
        r = httpx.post(f"{self.ollama_url}/api/chat", json={
            "model": self.model, "messages": messages, "stream": False,
            "options": {"temperature": 0.1, "num_predict": max_tokens},
        }, timeout=90.0)
        return r.json()

    def _analyze_results(self, user_msg: str, results: list[dict]) -> str:
        """실행 결과를 LLM이 분석 + 요약 + 다음 행동 추천"""
        results_text = "\n".join(
            f"[{r['skill']}] {'성공' if r['success'] else '실패'}: {r['output'][:300]}"
            for r in results
        )
        try:
            resp = httpx.post(f"{self.ollama_url}/api/chat", json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "너는 사이버보안 전문가다. 실행 결과를 분석하고 간결하게 한국어로 요약해. 이상 징후가 있으면 다음 행동을 추천해."},
                    {"role": "user", "content": f"사용자 요청: {user_msg}\n\n실행 결과:\n{results_text}\n\n분석 (3줄 이내):"},
                ],
                "stream": False,
                "options": {"temperature": 0.2, "num_predict": 300},
            }, timeout=60.0)
            return resp.json().get("message", {}).get("content", "분석 실패")
        except Exception as e:
            return f"분석 불가: {e}"

    def _assess_risk(self, skill_name: str, params: dict) -> str:
        """위험도 평가: low / medium / high"""
        high_risk = {"configure_nftables", "deploy_rule", "shell"}
        medium_risk = {"scan_ports", "web_scan"}
        if skill_name in high_risk:
            return "high"
        if skill_name in medium_risk:
            return "medium"
        return "low"

    def _build_prev_context(self) -> str:
        """이전 실행 결과 컨텍스트 (대화 연속성)"""
        recent = self.evidence_db.recent(3)
        if not recent:
            return ""
        lines = ["[이전 실행 기록]"]
        for e in recent:
            lines.append(f"- {e['skill']}: {'성공' if e['success'] else '실패'} | {e.get('analysis','')[:80]}")
        return "\n".join(lines)

    def _extract_skill_call(self, content: str) -> dict | None:
        """LLM 응답에서 skill JSON 추출 (단일 또는 멀티스텝)"""
        match = re.search(r'\{[^{}]*("skill"|"steps")\s*:', content)
        if not match:
            return None
        start = content.find("{", match.start())
        if start < 0:
            return None
        depth = 0
        for i in range(start, len(content)):
            if content[i] == "{":
                depth += 1
            elif content[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(content[start:i+1])
                    except json.JSONDecodeError:
                        return None
        return None

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
