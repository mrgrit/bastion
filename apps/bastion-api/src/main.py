"""bastion-api — 실무 운영/보안 에이전트 API (:9000)"""
from __future__ import annotations
import os
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

# ── DB ─────────────────────────────────────────────
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://bastion:bastion@127.0.0.1:5432/bastion")
API_KEY = os.getenv("BASTION_API_KEY", "bastion-api-key-2026")

# ── Pydantic Models ────────────────────────────────
class AssetCreate(BaseModel):
    name: str
    ip: str
    os_type: str = "linux"
    role: str = ""
    ssh_user: str = "root"
    ssh_port: int = 22
    subagent_port: int = 8002
    metadata: dict[str, Any] = {}

class AssetUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    metadata: dict[str, Any] | None = None

class BootstrapRequest(BaseModel):
    ssh_password: str | None = None
    ssh_key_path: str | None = None

class OnboardRequest(BaseModel):
    ssh_password: str | None = None
    ssh_key_path: str | None = None
    auto_bootstrap: bool = True

class TaskRequest(BaseModel):
    instruction: str
    risk_level: str = "low"
    subagent_url: str | None = None

class CentralRegisterRequest(BaseModel):
    central_url: str
    instance_name: str
    api_key: str = ""

# ── Auth ───────────────────────────────────────────
def verify_api_key(request: Request):
    key = request.headers.get("X-API-Key", "")
    if key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

# ── DB helpers ─────────────────────────────────────
import psycopg2
from psycopg2.extras import RealDictCursor

def _conn():
    return psycopg2.connect(DATABASE_URL)

def _init_db():
    """기본 테이블 생성"""
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    ip TEXT NOT NULL,
                    os_type TEXT DEFAULT 'linux',
                    role TEXT DEFAULT '',
                    ssh_user TEXT DEFAULT 'root',
                    ssh_port INT DEFAULT 22,
                    subagent_port INT DEFAULT 8002,
                    subagent_url TEXT,
                    status TEXT DEFAULT 'registered',
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    updated_at TIMESTAMPTZ DEFAULT now()
                );
                CREATE TABLE IF NOT EXISTS operations (
                    id TEXT PRIMARY KEY,
                    asset_id TEXT REFERENCES assets(id),
                    instruction TEXT NOT NULL,
                    risk_level TEXT DEFAULT 'low',
                    status TEXT DEFAULT 'pending',
                    result JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT now(),
                    completed_at TIMESTAMPTZ
                );
                CREATE TABLE IF NOT EXISTS pow_blocks (
                    id SERIAL PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    block_index INT NOT NULL,
                    block_hash TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    nonce INT DEFAULT 0,
                    difficulty INT DEFAULT 4,
                    task_id TEXT,
                    project_id TEXT,
                    reward_amount REAL DEFAULT 0,
                    ts_raw TEXT,
                    created_at TIMESTAMPTZ DEFAULT now()
                );
            """)
            conn.commit()

# ── Lifespan ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        _init_db()
    except Exception as e:
        print(f"[bastion] DB init warning: {e}")
    yield

# ── App ────────────────────────────────────────────
app = FastAPI(
    title="Bastion API",
    description="실무 운영/보안 AI 에이전트 시스템",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Root redirect ──────────────────────────────────
@app.get("/")
def root():
    from fastapi.responses import RedirectResponse
    return RedirectResponse("/app/")

# ── Health ─────────────────────────────────────────
@app.get("/health")
def health():
    return {"status": "ok", "service": "bastion-api"}

# ── Assets CRUD ────────────────────────────────────
@app.post("/assets", dependencies=[Depends(verify_api_key)])
def create_asset(body: AssetCreate):
    asset_id = str(uuid.uuid4())[:8]
    subagent_url = f"http://{body.ip}:{body.subagent_port}"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """INSERT INTO assets (id, name, ip, os_type, role, ssh_user, ssh_port, subagent_port, subagent_url, metadata)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (asset_id, body.name, body.ip, body.os_type, body.role,
                 body.ssh_user, body.ssh_port, body.subagent_port, subagent_url,
                 psycopg2.extras.Json(body.metadata)),
            )
            row = cur.fetchone()
            conn.commit()
    return {"asset": dict(row) if row else {"id": asset_id}}

@app.get("/assets", dependencies=[Depends(verify_api_key)])
def list_assets(status: str | None = None, role: str | None = None):
    q = "SELECT * FROM assets WHERE 1=1"
    params: list = []
    if status:
        q += " AND status=%s"; params.append(status)
    if role:
        q += " AND role=%s"; params.append(role)
    q += " ORDER BY created_at DESC"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
    return {"assets": [dict(r) for r in rows]}

@app.get("/assets/{asset_id}", dependencies=[Depends(verify_api_key)])
def get_asset(asset_id: str):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM assets WHERE id=%s", (asset_id,))
            row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Asset not found")
    return {"asset": dict(row)}

@app.put("/assets/{asset_id}", dependencies=[Depends(verify_api_key)])
def update_asset(asset_id: str, body: AssetUpdate):
    sets, params = [], []
    if body.name is not None:
        sets.append("name=%s"); params.append(body.name)
    if body.role is not None:
        sets.append("role=%s"); params.append(body.role)
    if body.metadata is not None:
        sets.append("metadata=%s"); params.append(psycopg2.extras.Json(body.metadata))
    if not sets:
        raise HTTPException(400, "No fields to update")
    sets.append("updated_at=now()")
    params.append(asset_id)
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(f"UPDATE assets SET {','.join(sets)} WHERE id=%s RETURNING *", params)
            row = cur.fetchone()
            conn.commit()
    if not row:
        raise HTTPException(404, "Asset not found")
    return {"asset": dict(row)}

@app.delete("/assets/{asset_id}", dependencies=[Depends(verify_api_key)])
def delete_asset(asset_id: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM assets WHERE id=%s", (asset_id,))
            conn.commit()
            if cur.rowcount == 0:
                raise HTTPException(404, "Asset not found")
    return {"deleted": asset_id}

# ── Bootstrap & Onboard ───────────────────────────
@app.post("/assets/{asset_id}/bootstrap", dependencies=[Depends(verify_api_key)])
def bootstrap_asset(asset_id: str, body: BootstrapRequest):
    """SubAgent 원격 설치"""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM assets WHERE id=%s", (asset_id,))
            asset = cur.fetchone()
    if not asset:
        raise HTTPException(404, "Asset not found")
    # TODO: paramiko SSH → SubAgent 설치
    # bootstrap_service.bootstrap_asset(config)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE assets SET status='bootstrapped', updated_at=now() WHERE id=%s", (asset_id,))
            conn.commit()
    return {"status": "bootstrapped", "asset_id": asset_id, "message": "SubAgent 설치 완료 (stub)"}

@app.post("/assets/{asset_id}/onboard", dependencies=[Depends(verify_api_key)])
def onboard_asset(asset_id: str, body: OnboardRequest):
    """전체 온보딩: 등록 확인 → 부트스트랩 → 헬스체크"""
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM assets WHERE id=%s", (asset_id,))
            asset = cur.fetchone()
    if not asset:
        raise HTTPException(404, "Asset not found")
    steps = []
    # Step 1: Bootstrap if needed
    if asset["status"] == "registered" and body.auto_bootstrap:
        steps.append("bootstrap: stub (SSH SubAgent install)")
    # Step 2: Health check
    import httpx
    try:
        r = httpx.get(f"{asset['subagent_url']}/health", timeout=5.0)
        health_ok = r.status_code == 200
        steps.append(f"health_check: {'ok' if health_ok else 'fail'}")
    except Exception as e:
        health_ok = False
        steps.append(f"health_check: error ({e})")
    # Update status
    new_status = "healthy" if health_ok else "bootstrapped"
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE assets SET status=%s, updated_at=now() WHERE id=%s", (new_status, asset_id))
            conn.commit()
    return {"status": new_status, "asset_id": asset_id, "steps": steps}

@app.get("/assets/{asset_id}/health", dependencies=[Depends(verify_api_key)])
def check_health(asset_id: str):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM assets WHERE id=%s", (asset_id,))
            asset = cur.fetchone()
    if not asset:
        raise HTTPException(404, "Asset not found")
    import httpx
    try:
        r = httpx.get(f"{asset['subagent_url']}/health", timeout=5.0)
        return {"asset_id": asset_id, "subagent_url": asset["subagent_url"], "healthy": r.status_code == 200, "detail": r.json()}
    except Exception as e:
        return {"asset_id": asset_id, "subagent_url": asset["subagent_url"], "healthy": False, "detail": str(e)}

# ── Dashboard ──────────────────────────────────────
@app.get("/dashboard/summary", dependencies=[Depends(verify_api_key)])
def dashboard_summary():
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT status, count(*) as cnt FROM assets GROUP BY status")
            asset_stats = {r["status"]: r["cnt"] for r in cur.fetchall()}
            cur.execute("SELECT count(*) as cnt FROM assets")
            total = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) as cnt FROM operations")
            ops_total = cur.fetchone()["cnt"]
            cur.execute("SELECT count(*) as cnt FROM pow_blocks")
            blocks_total = cur.fetchone()["cnt"]
    return {
        "assets": {"total": total, "by_status": asset_stats},
        "operations": {"total": ops_total},
        "blockchain": {"blocks": blocks_total},
    }

# ── Blockchain ─────────────────────────────────────
@app.get("/blockchain/blocks", dependencies=[Depends(verify_api_key)])
def list_blocks(agent_id: str | None = None, limit: int = 50):
    q = "SELECT * FROM pow_blocks WHERE 1=1"
    params: list = []
    if agent_id:
        q += " AND agent_id=%s"; params.append(agent_id)
    q += " ORDER BY created_at DESC LIMIT %s"; params.append(limit)
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
    return {"blocks": [dict(r) for r in rows]}

@app.get("/blockchain/verify", dependencies=[Depends(verify_api_key)])
def verify_chain(agent_id: str | None = None):
    q = "SELECT * FROM pow_blocks"
    params: list = []
    if agent_id:
        q += " WHERE agent_id=%s"; params.append(agent_id)
    q += " ORDER BY block_index ASC"
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(q, params)
            rows = cur.fetchall()
    # Simple chain verification
    valid = True
    tampered = []
    for i in range(1, len(rows)):
        if rows[i]["prev_hash"] != rows[i-1]["block_hash"]:
            valid = False
            tampered.append(rows[i]["block_index"])
    return {"valid": valid, "blocks": len(rows), "tampered": tampered}

@app.get("/blockchain/leaderboard", dependencies=[Depends(verify_api_key)])
def leaderboard():
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("""
                SELECT agent_id, count(*) as blocks, sum(reward_amount) as total_reward
                FROM pow_blocks GROUP BY agent_id ORDER BY total_reward DESC
            """)
            rows = cur.fetchall()
    return {"leaderboard": [dict(r) for r in rows]}

# ── Central Server Registration ────────────────────
@app.post("/central/register", dependencies=[Depends(verify_api_key)])
def register_with_central(body: CentralRegisterRequest):
    """중앙서버에 이 bastion 인스턴스 등록"""
    # TODO: CentralProtocol 연동
    return {
        "status": "registered (stub)",
        "central_url": body.central_url,
        "instance_name": body.instance_name,
    }

# ── AI Agent ───────────────────────────────────────
@app.post("/agent/task", dependencies=[Depends(verify_api_key)])
def ai_task(body: TaskRequest):
    """AI 작업 요청: 자연어 → LLM 계획 → SubAgent 실행 → PoW"""
    from packages.agent_orchestrator import run as orchestrate, asdict, OrchestratorResult

    # 자산 목록 가져오기
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM assets")
            assets = [dict(r) for r in cur.fetchall()]

    subagent = body.subagent_url
    if not subagent and assets:
        # 첫 번째 healthy 자산의 SubAgent 사용
        for a in assets:
            if a.get("status") == "healthy":
                subagent = a["subagent_url"]
                break
        if not subagent:
            subagent = assets[0].get("subagent_url", "http://localhost:8002")

    result = orchestrate(
        instruction=body.instruction,
        subagent_url=subagent or "http://localhost:8002",
        assets=assets,
        agent_id=subagent or "bastion-agent",
        db_conn_func=_conn,
    )

    # 작업 기록
    import uuid as _uuid
    op_id = str(_uuid.uuid4())[:8]
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO operations (id, instruction, risk_level, status, result)
                   VALUES (%s, %s, %s, %s, %s)""",
                (op_id, body.instruction, body.risk_level,
                 "completed" if not result.error else "failed",
                 psycopg2.extras.Json({
                     "plan": [{"order": t.order, "command": t.command, "description": t.description, "risk_level": t.risk_level} for t in result.plan],
                     "results": [{"order": r.order, "command": r.command, "exit_code": r.exit_code, "stdout": r.stdout[:500], "stderr": r.stderr[:500], "success": r.success} for r in result.results],
                     "block_hash": result.block_hash,
                     "error": result.error,
                 })),
            )
            conn.commit()

    return {
        "operation_id": op_id,
        "instruction": result.instruction,
        "plan": [{"order": t.order, "command": t.command, "description": t.description, "risk_level": t.risk_level} for t in result.plan],
        "results": [{"order": r.order, "command": r.command, "exit_code": r.exit_code, "stdout": r.stdout[:1000], "stderr": r.stderr[:500], "success": r.success} for r in result.results],
        "block_hash": result.block_hash,
        "error": result.error,
    }

@app.post("/agent/analyze", dependencies=[Depends(verify_api_key)])
def ai_analyze(body: TaskRequest):
    """시스템 분석 요청 (실행 없이 계획만)"""
    from packages.agent_orchestrator import plan as make_plan

    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM assets")
            assets = [dict(r) for r in cur.fetchall()]

    try:
        tasks = make_plan(body.instruction, assets)
        return {
            "instruction": body.instruction,
            "plan": [{"order": t.order, "command": t.command, "description": t.description, "risk_level": t.risk_level} for t in tasks],
            "note": "분석 결과입니다. 실행하려면 /agent/task를 사용하세요.",
        }
    except Exception as e:
        return {"error": str(e), "instruction": body.instruction}

@app.get("/agent/operations", dependencies=[Depends(verify_api_key)])
def list_operations(limit: int = 20):
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM operations ORDER BY created_at DESC LIMIT %s", (limit,))
            rows = cur.fetchall()
    return {"operations": [dict(r) for r in rows]}

# ── Static files (bastion-ui) ─────────────────────
import pathlib
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

_ui_dist = pathlib.Path(__file__).parent.parent.parent / "bastion-ui" / "dist"
if _ui_dist.exists():
    @app.get("/app/{path:path}")
    def spa_fallback(path: str):
        # SPA: 실제 파일이 있으면 서빙, 없으면 index.html
        fpath = _ui_dist / path
        if fpath.is_file():
            return FileResponse(str(fpath))
        return FileResponse(str(_ui_dist / "index.html"))

    app.mount("/app", StaticFiles(directory=str(_ui_dist), html=True), name="ui")
