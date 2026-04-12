"""Bastion 프롬프트 엔진 — 목적별 분리된 시스템 프롬프트

PLANNING 단계에서 두 가지 프롬프트를 순서대로 사용:
  1. build_planning_prompt() — Skill 선택용 (Tool Calling 또는 JSON fallback)
  2. build_system_prompt()   — 일반 컨텍스트 (Q&A 및 결과 분석용)
"""
from __future__ import annotations
import os

from bastion.skills import SKILLS
from bastion.playbook import list_playbooks


def build_planning_prompt(vm_ips: dict[str, str] = None,
                          rag_context: str = "",
                          prev_context: str = "") -> str:
    """Skill 선택 전용 프롬프트 — 간결하고 명확한 지시만 포함.

    Tool Calling 모드: 모델이 tool_calls 필드로 응답.
    JSON fallback 모드: {"skill": "...", "params": {...}} 형식으로 응답.
    """
    sections = []

    sections.append(
        "너는 Bastion 보안 운영 에이전트다.\n"
        "사용자 요청을 분석하고 적절한 Skill을 선택해 실행한다.\n"
        "Skill이 필요 없는 질문에는 도구 없이 직접 한국어로 답변한다."
    )

    # VM 인프라 정보
    if vm_ips:
        vm_lines = "\n".join(f"  {role}: {ip}" for role, ip in vm_ips.items())
        sections.append(f"현재 인프라 (role: internal_ip):\n{vm_lines}")

    # 이전 실행 컨텍스트
    if prev_context:
        sections.append(prev_context)

    # RAG 컨텍스트
    if rag_context:
        sections.append(rag_context)

    return "\n\n".join(sections)


def build_system_prompt(vm_ips: dict[str, str] = None,
                        student_info: dict = None,
                        extra_context: str = "") -> str:
    """범용 시스템 프롬프트 — Q&A·결과 분석용."""
    sections = []

    sections.append(
        "너는 CCC Bastion 보안 운영 에이전트다.\n"
        "학생의 사이버보안 인프라에서 보안 운영, 모니터링, 인시던트 대응을 수행한다.\n"
        "항상 한국어로 답변하며 결과는 간결하게 요약한다."
    )

    # Skill 목록
    skill_lines = "\n".join(
        f"  {name}: {s['description']}"
        for name, s in SKILLS.items()
    )
    sections.append(f"사용 가능한 Skill:\n{skill_lines}")

    # Playbook 목록
    playbooks = list_playbooks()
    if playbooks:
        pb_lines = "\n".join(
            f"  {p['playbook_id']}: {p['title']} ({p['steps']}단계)"
            for p in playbooks
        )
        sections.append(f"등록된 Playbook (우선 적용):\n{pb_lines}")

    # VM 인프라
    if vm_ips:
        vm_lines = "\n".join(f"  {role}: {ip}" for role, ip in vm_ips.items())
        sections.append(f"현재 인프라:\n{vm_lines}")

    # 학생 컨텍스트
    if student_info:
        sections.append(
            f"사용자: {student_info.get('name', '?')} "
            f"(rank: {student_info.get('rank', 'rookie')}, "
            f"blocks: {student_info.get('total_blocks', 0)})"
        )

    # CCC.md 운영 지침
    ccc_md = os.path.join(os.path.dirname(__file__), "..", "..", "CCC.md")
    if os.path.exists(ccc_md):
        try:
            with open(ccc_md, encoding="utf-8") as f:
                content = f.read()[:2000]
            if content:
                sections.append(f"[운영 지침]\n{content}")
        except Exception:
            pass

    # 추가 컨텍스트
    if extra_context:
        sections.append(f"[추가 컨텍스트]\n{extra_context}")

    return "\n\n".join(sections)
