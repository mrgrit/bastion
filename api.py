#!/usr/bin/env python3
"""bastion API 서버 — 비대화형 HTTP 인터페이스

Claude 또는 외부 시스템이 bastion을 headless로 호출할 때 사용.
TUI(main.py) 없이 agent.chat()을 직접 실행하고 이벤트 스트림을 반환.

Usage:
    python -m apps.bastion.api          # uvicorn 기본 실행 (port 8003)
    ./dev.sh bastion-api

Endpoints:
    POST /chat          — 자연어 요청 실행 (NDJSON 스트림)
    GET  /skills        — Skill 목록
    GET  /playbooks     — Playbook 목록
    GET  /evidence      — 최근 실행 기록
    GET  /assets        — Asset 레지스트리
    GET  /health        — 헬스체크
"""
import json
import os
import sys

BASTION_DIR = os.path.abspath(os.path.dirname(__file__))
BASTION_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASTION_DIR)

# .env 로드
ENV_PATH = os.path.join(BASTION_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel
except ImportError:
    import subprocess
    subprocess.run([sys.executable, "-m", "pip", "install", "fastapi", "uvicorn[standard]", "-q"], check=True)
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import StreamingResponse
    from pydantic import BaseModel

from bastion.agent import BastionAgent
from bastion import INTERNAL_IPS


# ── 초기화 ─────────────────────────────────────────────────────────────────

def _get_vm_ips() -> dict[str, str]:
    vm_ips = {}
    for role in ["attacker", "secu", "web", "siem", "manager"]:
        ip = os.getenv(f"VM_{role.upper()}_IP", "")
        if ip:
            vm_ips[role] = ip
    return vm_ips or dict(INTERNAL_IPS)


_vm_ips = _get_vm_ips()
_ollama_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
_model = os.getenv("LLM_MANAGER_MODEL", os.getenv("LLM_MODEL", "gpt-oss:120b"))

agent = BastionAgent(vm_ips=_vm_ips, ollama_url=_ollama_url, model=_model)

app = FastAPI(
    title="Bastion API",
    description="CCC Bastion 보안 운영 에이전트 — Headless HTTP 인터페이스",
    version="1.0.0",
)


# ── 스키마 ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    auto_approve: bool = False   # True: 고위험 작업 자동 승인 (주의)
    stream: bool = True          # False: 전체 이벤트 배열 한번에 반환


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": _model,
        "llm": _ollama_url,
        "skills": len(agent.get_skills()),
        "playbooks": len(agent.get_playbooks()),
    }


@app.get("/skills")
def skills():
    return agent.get_skills()


@app.get("/playbooks")
def playbooks():
    return agent.get_playbooks()


@app.get("/evidence")
def evidence(limit: int = 20):
    return agent.get_evidence(limit)


@app.get("/assets")
def assets():
    return agent.evidence_db.get_assets()


@app.post("/chat")
def chat(req: ChatRequest):
    """자연어 요청을 bastion에 실행.

    stream=True (기본): NDJSON 스트림 — 이벤트마다 한 줄씩 반환.
    stream=False: 전체 이벤트 배열을 JSON으로 한번에 반환.

    NDJSON 예시 (curl):
        curl -N -X POST http://localhost:8003/chat \\
             -H 'Content-Type: application/json' \\
             -d '{"message": "suricata 상태 확인해줘"}'
    """
    def approval_callback(step_name: str, skill: str, params: dict) -> bool:
        return req.auto_approve

    def event_generator():
        for evt in agent.chat(req.message, approval_callback=approval_callback):
            yield json.dumps(evt, ensure_ascii=False) + "\n"

    if req.stream:
        return StreamingResponse(
            event_generator(),
            media_type="application/x-ndjson",
        )
    else:
        events = list(agent.chat(req.message, approval_callback=approval_callback))
        return {"events": events}


# ── 직접 실행 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BASTION_API_PORT", "8003"))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
