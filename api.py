#!/usr/bin/env python3
"""bastion API 서버 — 비대화형 HTTP 인터페이스

Claude 또는 외부 시스템이 bastion을 headless로 호출할 때 사용.
TUI(main.py) 없이 agent.chat()을 직접 실행하고 이벤트 스트림을 반환.

Usage:
    python -m apps.bastion.api          # uvicorn 기본 실행 (port 8003)
    ./dev.sh bastion-api

Endpoints:
    POST /chat              — 자연어 요청 실행 (NDJSON 스트림)
    POST /onboard           — VM 온보딩 (NDJSON 스트림, 타임아웃 없음)
    GET  /skills            — Skill 목록
    GET  /playbooks         — Playbook 목록
    GET  /evidence          — 최근 실행 기록
    GET  /assets            — Asset 레지스트리
    PUT  /assets/{role}     — Asset 직접 등록/갱신
    GET  /health            — 헬스체크
"""
import json
import os
import sys

BASTION_DIR = os.path.abspath(os.path.dirname(__file__))
CCC_DIR = os.path.abspath(os.path.join(BASTION_DIR, "..", ".."))
sys.path.insert(0, CCC_DIR)

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


from bastion import LLM_BASE_URL, LLM_MANAGER_MODEL

_vm_ips = _get_vm_ips()
agent = BastionAgent(vm_ips=_vm_ips, ollama_url=LLM_BASE_URL, model=LLM_MANAGER_MODEL)

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
    # 테스트 메타데이터 — evidence DB에 함께 기록
    course: str = ""
    lab_id: str = ""
    step_order: int = 0
    test_session: str = ""


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

@app.get("/health")
def health():
    return {
        "status": "ok",
        "model": agent.model,
        "llm": agent.ollama_url,
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


class AssetUpdateBody(BaseModel):
    ip: str
    status: str = "healthy"
    notes: str = ""


@app.put("/assets/{role}")
def update_asset(role: str, body: AssetUpdateBody):
    """온보딩 완료 후 asset 등록/갱신. LLM 호출 없이 직접 등록."""
    agent.evidence_db.update_asset(role, body.ip, body.status, body.notes)
    return {"role": role, "ip": body.ip, "status": body.status}


# ── Ollama 호환 프록시 엔드포인트 ─────────────────────────────────────────────
# 실습 스크립트가 기존 Ollama API 형식 그대로 사용하되 bastion을 통해 라우팅

@app.post("/api/generate")
def ollama_generate_proxy(request: dict):
    """Ollama /api/generate 호환 프록시 — bastion을 통해 LLM으로 포워딩.
    모델이 지정되지 않거나 없는 모델 요청 시 bastion 설정 모델(LLM_SUBAGENT_MODEL)로 교체.
    """
    import httpx
    # 모델을 설정된 서브에이전트 모델로 강제 지정 (gemma3:4b 등 없는 모델 방지)
    request["model"] = agent.model
    request.setdefault("stream", False)
    try:
        resp = httpx.post(
            f"{agent.ollama_url}/api/generate",
            json=request,
            timeout=120,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e), "response": ""}


@app.post("/api/chat")
def ollama_chat_proxy(request: dict):
    """Ollama /api/chat 호환 프록시 — bastion을 통해 LLM으로 포워딩.
    모델을 bastion 설정 모델로 교체.
    """
    import httpx
    request["model"] = agent.model
    request.setdefault("stream", False)
    try:
        resp = httpx.post(
            f"{agent.ollama_url}/api/chat",
            json=request,
            timeout=120,
        )
        return resp.json()
    except Exception as e:
        return {"error": str(e), "message": {"content": ""}}


@app.get("/api/tags")
def ollama_tags_proxy():
    """Ollama /api/tags 호환 프록시"""
    import httpx
    try:
        resp = httpx.get(f"{agent.ollama_url}/api/tags", timeout=10)
        return resp.json()
    except Exception as e:
        return {"models": [], "error": str(e)}


@app.get("/api/version")
def ollama_version_proxy():
    """Ollama /api/version 호환 프록시"""
    import httpx
    try:
        resp = httpx.get(f"{agent.ollama_url}/api/version", timeout=10)
        return resp.json()
    except Exception as e:
        return {"version": "unknown", "error": str(e)}


class OnboardRequest(BaseModel):
    role: str
    ip: str
    ssh_user: str = "ccc"
    ssh_password: str = "1"
    gpu_url: str = ""


@app.post("/onboard")
def onboard(req: OnboardRequest):
    """VM 온보딩 — SubAgent 설치 + 역할별 소프트웨어 + Asset 등록.

    NDJSON 스트림으로 단계별 진행상황 실시간 반환. 타임아웃 없음.

    예시:
        curl -N -X POST http://localhost:8003/onboard \\
             -H 'Content-Type: application/json' \\
             -d '{"role": "secu", "ip": "192.168.208.155"}'
    """
    from bastion import onboard_vm, LLM_BASE_URL, LLM_MANAGER_MODEL, LLM_SUBAGENT_MODEL

    def event_generator():
        yield json.dumps({"event": "start", "role": req.role, "ip": req.ip}, ensure_ascii=False) + "\n"
        try:
            result = onboard_vm(
                ip=req.ip, role=req.role,
                user=req.ssh_user, password=req.ssh_password,
                gpu_url=req.gpu_url or LLM_BASE_URL,
                manager_model=LLM_MANAGER_MODEL,
                subagent_model=LLM_SUBAGENT_MODEL,
            )
            for step in result.get("steps", []):
                yield json.dumps({"event": "step", **step}, ensure_ascii=False) + "\n"

            healthy = result.get("healthy", False)
            internal_ip = result.get("internal_ip", req.ip)

            # Asset 등록
            status = "healthy" if healthy else "unreachable"
            agent.evidence_db.update_asset(req.role, internal_ip, status, "온보딩")

            yield json.dumps({
                "event": "done",
                "role": req.role,
                "healthy": healthy,
                "internal_ip": internal_ip,
                "error": result.get("error", ""),
            }, ensure_ascii=False) + "\n"

        except Exception as e:
            yield json.dumps({"event": "error", "role": req.role, "message": str(e)}, ensure_ascii=False) + "\n"

    return StreamingResponse(event_generator(), media_type="application/x-ndjson")


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

    # 테스트 메타데이터를 agent에 주입 → evidence DB 기록 시 사용
    agent._test_meta = {
        "course": req.course,
        "lab_id": req.lab_id,
        "step_order": req.step_order,
        "test_session": req.test_session,
    } if req.course else {}

    def event_generator():
        for evt in agent.chat(req.message, approval_callback=approval_callback):
            yield json.dumps(evt, ensure_ascii=False) + "\n"
        agent._test_meta = {}

    if req.stream:
        return StreamingResponse(
            event_generator(),
            media_type="application/x-ndjson",
        )
    else:
        events = list(agent.chat(req.message, approval_callback=approval_callback))
        agent._test_meta = {}
        return {"events": events}


class AskRequest(BaseModel):
    message: str
    auto_approve: bool = True  # /ask는 기본 자동승인 (실습용)


@app.post("/ask")
def ask(req: AskRequest):
    """실습 스크립트용 단순 질문 API — LLM 답변 텍스트만 반환.

    /chat의 간소화 버전. 스트리밍 없이 답변 텍스트만 반환하여 셸 스크립트에서 쉽게 사용 가능.

    예시:
        curl -s -X POST http://localhost:8003/ask \\
             -H 'Content-Type: application/json' \\
             -d '{"message": "프롬프트 인젝션이란?"}' \\
             | python3 -c "import sys,json; print(json.load(sys.stdin)['answer'])"
    """
    def approval_callback(step_name: str, skill: str, params: dict) -> bool:
        return req.auto_approve

    answer = ""
    skill_outputs = []
    events = []
    for evt in agent.chat(req.message, approval_callback=approval_callback):
        events.append(evt)
        e = evt.get("event", "")
        if e == "stream_token":
            answer += evt.get("token", "")
        elif e == "skill_result":
            skill_outputs.append({
                "skill": evt.get("skill", ""),
                "output": evt.get("output", ""),
                "success": evt.get("success", False),
            })

    return {
        "answer": answer,
        "success": True,
        "skill_outputs": skill_outputs,
        "event_count": len(events),
    }


# ── 직접 실행 ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("BASTION_API_PORT", "8003"))
    uvicorn.run("apps.bastion.api:app", host="0.0.0.0", port=port, reload=False)
