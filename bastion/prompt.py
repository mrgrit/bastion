"""Bastion 프롬프트 엔진 — 모듈식 시스템 프롬프트 조합

Bastion의 prompt_engine 패턴. 섹션별로 프롬프트를 구성하고 컨텍스트를 동적 주입.
"""
from __future__ import annotations
import os

from bastion.skills import SKILLS
from bastion.playbook import list_playbooks


def build_system_prompt(vm_ips: dict[str, str] = None,
                        student_info: dict = None,
                        extra_context: str = "") -> str:
    """컨텍스트에 맞는 시스템 프롬프트 동적 생성"""
    sections = []

    # 1. Identity
    sections.append("""너는 CCC(Cyber Combat Commander) Bastion 보안 운영 에이전트다.
학생의 사이버보안 인프라에서 보안 운영, 모니터링, 인시던트 대응 작업을 수행한다.
자연어 명령을 받아 적절한 skill을 선택하고 실행한다.""")

    # 2. Skills
    skill_list = "\n".join(f"  - {name}: {s['description']}" for name, s in SKILLS.items())
    sections.append(f"사용 가능한 skill:\n{skill_list}")

    # 3. Playbooks
    pbs = list_playbooks()
    if pbs:
        pb_list = "\n".join(f"  - {p['playbook_id']}: {p['title']} ({p['steps']}단계)" for p in pbs)
        sections.append(f"등록된 playbook:\n{pb_list}")

    # 4. Infrastructure
    if vm_ips:
        vm_list = "\n".join(f"  - {role}: {ip} (:8002 SubAgent)" for role, ip in vm_ips.items())
        sections.append(f"현재 인프라:\n{vm_list}")

    # 5. Constraints
    sections.append("""제약사항:
- skill이 있으면 반드시 skill을 사용한다 (직접 명령 생성 금지)
- 위험 작업(방화벽 변경, 룰 배포, 임의 명령)은 반드시 사용자에게 확인을 받는다
- playbook이 있는 작업은 playbook을 우선 사용한다
- 한국어로 답변한다
- 실행 결과를 간결하게 요약한다""")

    # 6. Student context
    if student_info:
        sections.append(f"현재 사용자: {student_info.get('name', '?')} (rank: {student_info.get('rank', 'rookie')}, blocks: {student_info.get('total_blocks', 0)})")

    # 7. CCC.md 장기 기억
    ccc_md = os.path.join(os.path.dirname(__file__), "..", "..", "CCC.md")
    if os.path.exists(ccc_md):
        try:
            with open(ccc_md, encoding="utf-8") as f:
                sections.append(f"[운영 지침]\n{f.read()[:2000]}")
        except Exception:
            pass

    # 8. Extra context
    if extra_context:
        sections.append(f"추가 컨텍스트:\n{extra_context}")

    return "\n\n".join(sections)
