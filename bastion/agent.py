"""Bastion Agent 코어 — 자연어 대화 + Skill/Playbook 실행

학생/관리자가 자연어로 보안 작업을 지시하면:
1. LLM이 적절한 skill 또는 playbook을 선택 (프롬프트 기반 JSON)
2. SubAgent A2A로 실제 실행
3. 결과를 요약하여 반환
"""
from __future__ import annotations
import os
import json
import re
from typing import Any, Generator

import httpx

from bastion.skills import SKILLS, execute_skill
from bastion.playbook import list_playbooks, run_playbook, load_playbook
from bastion.prompt import build_system_prompt
from bastion.rag import build_index, format_context


# Skill 목록을 프롬프트용 텍스트로 변환
def _skills_for_prompt() -> str:
    lines = []
    for name, s in SKILLS.items():
        params_desc = ", ".join(f"{k}: {v.get('type','str')}" for k, v in s.get("params", {}).items())
        lines.append(f'  - {name}({params_desc}): {s["description"]}')
    return "\n".join(lines)


class BastionAgent:
    """Bastion 에이전트 — 대화형 보안 운영 에이전트"""

    def __init__(self, vm_ips: dict[str, str],
                 ollama_url: str = "", model: str = "",
                 knowledge_dir: str = ""):
        self.vm_ips = vm_ips
        self.ollama_url = ollama_url or os.getenv("LLM_BASE_URL", "http://localhost:11434")
        self.model = model or os.getenv("LLM_MANAGER_MODEL", os.getenv("LLM_MODEL", "gpt-oss:120b"))
        self.history: list[dict] = []
        self.evidence: list[dict] = []
        # RAG
        self.rag_index = None
        kdir = knowledge_dir or os.path.join(os.path.dirname(__file__), "..", "..", "contents")
        if os.path.isdir(kdir):
            try:
                self.rag_index = build_index(kdir)
            except Exception:
                pass

    def chat(self, message: str, approval_callback=None) -> Generator[dict, None, None]:
        """자연어 메시지 처리 → skill/playbook 실행 → 결과 스트리밍"""
        self.history.append({"role": "user", "content": message})

        # Playbook 직접 요청 감지
        pb_match = re.search(r'playbook[:\s]+(\w+)', message, re.IGNORECASE)
        if pb_match:
            pb_id = pb_match.group(1)
            pb = load_playbook(pb_id)
            if pb:
                yield {"event": "message", "content": f"Playbook '{pb['title']}' 실행합니다."}
                yield from run_playbook(pb_id, self.vm_ips, ollama_url=self.ollama_url,
                                        model=self.model, approval_callback=approval_callback)
                return

        # RAG: 관련 교육 자료 검색
        rag_context = ""
        if self.rag_index:
            chunks = self.rag_index.search(message, top_k=3)
            rag_context = format_context(chunks)

        # LLM에게 skill 선택 요청 (프롬프트 기반 JSON)
        system_prompt = build_system_prompt(self.vm_ips, extra_context=rag_context)
        skill_prompt = f"""{system_prompt}

사용자 요청에 대해 다음 중 하나로 응답하세요:

1) skill 실행이 필요하면 반드시 아래 JSON 형식으로만 응답:
{{"skill": "skill_name", "params": {{"param1": "value1"}}}}

사용 가능한 skill:
{_skills_for_prompt()}

2) skill이 필요 없는 일반 질문이면 한국어로 직접 답변.

중요: skill을 사용할 때는 JSON만 출력하세요. 설명이나 다른 텍스트 없이 JSON만."""

        try:
            response = self._call_llm(skill_prompt)
        except Exception as e:
            yield {"event": "error", "content": f"LLM 연결 실패: {e}"}
            return

        content = response.get("message", {}).get("content", "").strip()

        # JSON 응답에서 skill 추출
        skill_call = self._extract_skill_call(content)

        if skill_call:
            skill_name = skill_call.get("skill", "")
            params = skill_call.get("params", {})

            if skill_name not in SKILLS:
                yield {"event": "message", "content": f"알 수 없는 skill: {skill_name}\n\n{content}"}
                return

            # 승인 필요 체크
            skill_def = SKILLS.get(skill_name, {})
            if skill_def.get("requires_approval") and approval_callback:
                approved = approval_callback(skill_name, skill_name, params)
                if not approved:
                    yield {"event": "skill_skip", "skill": skill_name, "reason": "User denied"}
                    return

            yield {"event": "skill_start", "skill": skill_name, "params": params}

            result = execute_skill(skill_name, params, self.vm_ips,
                                   self.ollama_url, self.model)
            self.evidence.append({"skill": skill_name, "params": params, "result": result})

            yield {"event": "skill_result", "skill": skill_name,
                   "success": result.get("success", False),
                   "output": str(result.get("output", ""))[:1000]}

            # 결과 요약
            self.history.append({"role": "assistant", "content": f"[{skill_name}] 실행 완료"})
        else:
            # 일반 텍스트 응답
            yield {"event": "message", "content": content}
            self.history.append({"role": "assistant", "content": content})

    def _call_llm(self, system_prompt: str) -> dict:
        """Ollama API 호출 — tools 없이 프롬프트 기반"""
        messages = [{"role": "system", "content": system_prompt}]
        # 최근 히스토리 10개만
        messages += self.history[-10:]

        r = httpx.post(f"{self.ollama_url}/api/chat", json={
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 500},
        }, timeout=60.0)
        return r.json()

    def _extract_skill_call(self, content: str) -> dict | None:
        """LLM 응답에서 skill JSON 추출"""
        # {"skill": "...", "params": {...}} 패턴 찾기
        match = re.search(r'\{[^{}]*"skill"\s*:\s*"[^"]+"\s*[,}]', content)
        if not match:
            return None
        # 매칭 위치에서 전체 JSON 추출
        start = content.find("{", match.start())
        if start < 0:
            return None
        # 중괄호 카운팅으로 JSON 범위 찾기
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
        """사용 가능한 skill 목록"""
        return [{"name": k, "description": v["description"],
                 "target_vm": v.get("target_vm", "auto"),
                 "requires_approval": v.get("requires_approval", False)}
                for k, v in SKILLS.items()]

    def get_playbooks(self) -> list[dict]:
        """등록된 playbook 목록"""
        return list_playbooks()
