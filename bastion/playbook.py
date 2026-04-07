"""Bastion Playbook 엔진 — YAML 기반 구조화된 작업 실행

"Playbook이 법이다" — LLM이 즉흥하지 않고 등록된 Playbook의 순서대로 실행.
LLM은 Playbook 선택과 파라미터 채우기만 담당.
"""
from __future__ import annotations
import os
import glob
from typing import Any, Generator

import yaml

from bastion.skills import execute_skill, SKILLS


PLAYBOOKS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "contents", "playbooks")


def load_playbook(playbook_id: str) -> dict | None:
    """Playbook YAML 로드"""
    for f in glob.glob(os.path.join(PLAYBOOKS_DIR, "*.yaml")):
        with open(f, encoding="utf-8") as fh:
            pb = yaml.safe_load(fh)
        if pb and pb.get("playbook_id") == playbook_id:
            return pb
    return None


def list_playbooks() -> list[dict]:
    """등록된 Playbook 목록"""
    result = []
    for f in sorted(glob.glob(os.path.join(PLAYBOOKS_DIR, "*.yaml"))):
        with open(f, encoding="utf-8") as fh:
            pb = yaml.safe_load(fh)
        if pb:
            result.append({
                "playbook_id": pb.get("playbook_id", ""),
                "title": pb.get("title", ""),
                "description": pb.get("description", ""),
                "steps": len(pb.get("steps", [])),
            })
    return result


def run_playbook(playbook_id: str, vm_ips: dict[str, str],
                 params: dict[str, Any] = None,
                 ollama_url: str = "", model: str = "",
                 approval_callback=None) -> Generator[dict, None, None]:
    """Playbook 실행 — 스텝별 SSE 이벤트 스트리밍

    approval_callback: requires_approval=True 스텝에서 호출. True 반환 시 실행, False면 스킵.
    """
    pb = load_playbook(playbook_id)
    if not pb:
        yield {"event": "error", "message": f"Playbook not found: {playbook_id}"}
        return

    params = params or {}
    steps = pb.get("steps", [])
    evidence = []

    yield {"event": "playbook_start", "playbook_id": playbook_id, "title": pb.get("title", ""), "total_steps": len(steps)}

    for i, step in enumerate(steps):
        step_name = step.get("name", f"Step {i+1}")
        skill_name = step.get("skill", "")
        step_params = {**params, **step.get("params", {})}
        on_failure = step.get("on_failure", "continue")
        requires_approval = step.get("requires_approval", False)

        # 파라미터 템플릿 치환 ({suspect_ip} → 실제 값)
        for k, v in step_params.items():
            if isinstance(v, str):
                for pk, pv in params.items():
                    v = v.replace(f"{{{pk}}}", str(pv))
                step_params[k] = v

        yield {"event": "step_start", "step": i+1, "name": step_name, "skill": skill_name}

        # 승인 필요
        if requires_approval or SKILLS.get(skill_name, {}).get("requires_approval"):
            if approval_callback:
                approved = approval_callback(step_name, skill_name, step_params)
                if not approved:
                    yield {"event": "step_skip", "step": i+1, "name": step_name, "reason": "User denied"}
                    continue

        # Skill 실행
        if skill_name and skill_name in SKILLS:
            result = execute_skill(skill_name, step_params, vm_ips, ollama_url, model)
        else:
            result = {"success": False, "error": f"Unknown skill: {skill_name}"}

        evidence.append({"step": step_name, "skill": skill_name, "result": result})

        yield {
            "event": "step_done", "step": i+1, "name": step_name,
            "success": result.get("success", False),
            "output": str(result.get("output", ""))[:500],
        }

        # 실패 정책
        if not result.get("success") and on_failure == "abort":
            yield {"event": "playbook_abort", "step": i+1, "name": step_name, "reason": "Step failed with on_failure=abort"}
            break

    passed = sum(1 for e in evidence if e["result"].get("success"))
    yield {
        "event": "playbook_done",
        "playbook_id": playbook_id,
        "passed": passed,
        "total": len(steps),
        "evidence_count": len(evidence),
    }
