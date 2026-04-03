"""agent_orchestrator — bastion AI 에이전트 오케스트레이터

자연어 작업 요청 → LLM 실행 계획 → SubAgent 실행 → 결과 반환.

Flow:
  1. plan(instruction, assets) → LLM이 실행 계획 생성
  2. execute(plan, subagent_url) → SubAgent로 명령 실행
  3. record(result) → PoW 블록 + evidence 기록
"""
from __future__ import annotations
import json
import hashlib
import time
import os
from dataclasses import dataclass, field, asdict
from typing import Any

import httpx

def _get_ollama_url():
    try:
        from packages.opsclaw_common.config_client import get_config
        return get_config("llm.ollama.url", fallback=os.getenv("OLLAMA_BASE_URL", "http://192.168.0.105:11434"))
    except Exception:
        return os.getenv("OLLAMA_BASE_URL", "http://192.168.0.105:11434")

def _get_model():
    try:
        from packages.opsclaw_common.config_client import get_config
        return get_config("llm.default_model", fallback=os.getenv("BASTION_LLM_MODEL", "gpt-oss:120b"))
    except Exception:
        return os.getenv("BASTION_LLM_MODEL", "gpt-oss:120b")

OLLAMA_URL = _get_ollama_url()
MODEL = _get_model()

SYSTEM_PROMPT = """너는 Bastion AI 에이전트다. IT 인프라 운영/보안 작업을 자동화한다.

사용자가 자연어로 작업을 요청하면:
1. 실행 가능한 bash 명령어 목록을 생성한다
2. 각 명령어에 risk_level(low/medium/high/critical)을 부여한다
3. 명령어는 반드시 Linux bash에서 바로 실행 가능해야 한다

자산 정보가 주어지면 해당 서버에 맞는 명령을 생성한다.

반드시 아래 JSON 형식으로만 응답:
{"tasks":[{"order":1,"command":"실행할 bash 명령","description":"설명","risk_level":"low"}]}
"""


@dataclass
class TaskPlan:
    order: int
    command: str
    description: str
    risk_level: str = "low"


@dataclass
class TaskResult:
    order: int
    command: str
    exit_code: int = -1
    stdout: str = ""
    stderr: str = ""
    success: bool = False


@dataclass
class OrchestratorResult:
    instruction: str
    plan: list[TaskPlan] = field(default_factory=list)
    results: list[TaskResult] = field(default_factory=list)
    block_hash: str = ""
    error: str = ""


def plan(instruction: str, assets: list[dict] | None = None) -> list[TaskPlan]:
    """LLM에 실행 계획 요청"""
    asset_info = ""
    if assets:
        asset_info = "\n\n등록된 자산:\n"
        for a in assets:
            asset_info += f"- {a['name']}: {a['ip']} (role={a.get('role','')}, subagent={a.get('subagent_url','')})\n"

    user_msg = f"{instruction}{asset_info}"

    try:
        r = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "stream": False,
                "options": {"temperature": 0.3},
            },
            timeout=120.0,
        )
        r.raise_for_status()
        content = r.json().get("message", {}).get("content", "")

        # JSON 추출
        start = content.find("{")
        end = content.rfind("}") + 1
        if start >= 0 and end > start:
            data = json.loads(content[start:end])
            tasks = data.get("tasks", [])
            return [TaskPlan(**t) for t in tasks]
    except Exception as e:
        raise RuntimeError(f"LLM plan failed: {e}")
    return []


def execute_on_subagent(command: str, subagent_url: str) -> TaskResult:
    """SubAgent에 명령 실행 요청"""
    try:
        import uuid as _uuid
        r = httpx.post(
            f"{subagent_url}/a2a/run_script",
            json={
                "project_id": f"bastion-{_uuid.uuid4().hex[:8]}",
                "job_run_id": _uuid.uuid4().hex[:8],
                "script": command,
                "timeout_s": 60,
            },
            timeout=90.0,
        )
        r.raise_for_status()
        raw = r.json()
        data = raw.get("detail", raw)  # SubAgent wraps in "detail"
        return TaskResult(
            order=0,
            command=command,
            exit_code=data.get("exit_code", -1),
            stdout=data.get("stdout", ""),
            stderr=data.get("stderr", ""),
            success=data.get("exit_code", -1) == 0,
        )
    except Exception as e:
        return TaskResult(order=0, command=command, stderr=str(e))


def record_pow(agent_id: str, task_desc: str, db_conn_func) -> str:
    """간이 PoW 블록 생성"""
    conn = db_conn_func()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT block_hash FROM pow_blocks WHERE agent_id=%s ORDER BY id DESC LIMIT 1", (agent_id,))
            row = cur.fetchone()
            prev_hash = row[0] if row else "0" * 64

            nonce = 0
            ts = str(time.time())
            block_data = f"{agent_id}:{task_desc}:{prev_hash}:{nonce}:{ts}"
            block_hash = hashlib.sha256(block_data.encode()).hexdigest()

            cur.execute(
                """INSERT INTO pow_blocks
                   (agent_id, block_index,
                    block_hash, prev_hash, nonce, difficulty, task_id, reward_amount)
                   VALUES (%s,
                    (SELECT COALESCE(MAX(block_index),0)+1 FROM pow_blocks WHERE agent_id=%s),
                    %s, %s, %s, 4, %s, %s)""",
                (agent_id, agent_id, block_hash, prev_hash, nonce, task_desc, 10.0),
            )
            conn.commit()
        return block_hash
    finally:
        conn.close()


def run(
    instruction: str,
    subagent_url: str = "http://localhost:8002",
    assets: list[dict] | None = None,
    agent_id: str = "bastion-agent",
    db_conn_func=None,
) -> OrchestratorResult:
    """전체 오케스트레이션: plan → execute → record"""
    result = OrchestratorResult(instruction=instruction)

    # 1. Plan
    try:
        tasks = plan(instruction, assets)
        result.plan = tasks
    except Exception as e:
        result.error = f"Plan failed: {e}"
        return result

    if not tasks:
        result.error = "LLM returned empty plan"
        return result

    # 2. Execute
    for t in tasks:
        tr = execute_on_subagent(t.command, subagent_url)
        tr.order = t.order
        result.results.append(tr)

    # 3. Record PoW
    if db_conn_func:
        try:
            result.block_hash = record_pow(agent_id, instruction[:100], db_conn_func)
        except Exception as e:
            result.error = f"PoW record failed: {e}"

    return result
