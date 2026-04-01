# 1단계 제안서: prompt_engine 패키지

## 현재 문제

OpsClaw의 LLM 시스템 프롬프트는 `pi_adapter/runtime/client.py:120-136`에 3줄 고정 문자열로 정의되어 있다:

```python
_ROLE_SYSTEM_PROMPTS = {
    "manager": "You are the OpsClaw Manager agent. You orchestrate IT operations workflows...",
    "master":  "You are the OpsClaw Master agent. You perform high-level reasoning...",
    "subagent": "You are the OpsClaw SubAgent. You execute specific operational commands...",
}
```

반면 `docs/agent-system-prompt.md`(214줄)에는 역할 분담, 작업 순서, 실행 방법 선택, 안전 규칙, 에러 처리, 완료보고서 형식 등 풍부한 지침이 있지만, 이것이 런타임 프롬프트에 반영되지 않는다.

결과적으로:
- LLM이 OpsClaw의 작업 흐름(stage 전이, evidence 기록)을 모름
- Tool/Skill 목록을 동적으로 인식하지 못함
- 서버별 환경(IP, 역할)을 프롬프트에서 참조 불가
- RAG 검색 결과가 프롬프트 구조에 통합되지 않음

## 목표

Claude Code의 `getSystemPrompt()` 패턴을 참고하여, OpsClaw의 시스템 프롬프트를 **섹션 기반 동적 조합 시스템**으로 재설계한다.

## 설계

### 패키지 구조

```
packages/prompt_engine/
├── __init__.py          # compose() 진입점
├── sections/
│   ├── __init__.py
│   ├── identity.py      # 역할 정의
│   ├── safety.py        # 안전 규칙 + risk_level 예시
│   ├── tools.py         # 활성 Tool/Skill 목록 동적 삽입
│   ├── workflow.py      # 작업 순서, stage 전이, API 사용법
│   ├── environment.py   # 인프라 매핑, SubAgent URL
│   ├── experience.py    # RAG 검색 결과 포맷팅
│   ├── local_knowledge.py  # 서버별 지식
│   └── output.py        # 출력 형식 + 효율성
├── cache.py             # 정적/동적 경계 관리
└── registry.py          # 섹션 등록/해결
```

### 핵심 인터페이스

```python
# packages/prompt_engine/__init__.py

def compose(
    role: str,                    # "manager" | "master" | "subagent"
    context: dict | None = None,  # 동적 컨텍스트
) -> str:
    """
    역할과 컨텍스트에 따라 시스템 프롬프트를 조합한다.
    
    context 키:
      - tools: list[dict]         # 활성 도구 목록
      - skills: list[dict]        # 활성 스킬 목록
      - server: str               # 대상 서버명
      - project_id: str           # 프로젝트 ID (RAG 조회용)
      - rag_results: list[dict]   # 사전 검색된 RAG 결과
      - local_knowledge: dict     # 서버 지식
    """
```

### 섹션 예시

```python
# sections/identity.py

ROLE_IDENTITIES = {
    "manager": """# Identity

You are the OpsClaw Manager agent.
You orchestrate IT operations workflows on internal network assets through the Manager API.

Your responsibilities:
- Follow playbooks precisely — do not improvise
- Record all execution results as evidence
- Never skip validation or evidence steps
- Produce structured JSON outputs when asked""",

    "master": """# Identity

You are the OpsClaw External Master.
You analyze user requests, create work plans, call the Manager API, interpret results, and write completion reports.

Key principle: You are the brain. Manager is the control-plane. SubAgent is the hands.
You never touch servers directly — all commands go through Manager API.""",
}
```

```python
# sections/safety.py

def get_safety_section(role: str) -> str:
    return """# Safety Rules

## risk_level Judgment
| Level | Criteria | Examples |
|-------|----------|----------|
| low | Read-only, status check | df -h, systemctl status, cat /etc/os-release |
| medium | Install, config change (reversible) | apt-get install, systemctl restart |
| high | Data change, possible service disruption | systemctl stop, iptables -F |
| critical | Irreversible destructive operations | rm -rf, DROP TABLE, fdisk |

## Mandatory Behaviors
- critical tasks: always dry_run first, then user confirmation
- Destructive commands (rm -rf, DROP TABLE): explicit user approval required
- Never modify SubAgent URLs without user instruction
- One project = one work unit — do not mix unrelated tasks"""
```

```python
# sections/tools.py

def get_tools_section(tools: list[dict], skills: list[dict]) -> str | None:
    if not tools and not skills:
        return None
    
    lines = ["# Available Tools & Skills", ""]
    
    if tools:
        lines.append("## Tools (atomic operations)")
        lines.append("| Name | Description | Required Params |")
        lines.append("|------|-------------|----------------|")
        for t in tools:
            params = t.get("required_params", "—")
            lines.append(f"| `{t['name']}` | {t.get('description', '')} | {params} |")
    
    if skills:
        lines.append("")
        lines.append("## Skills (composite procedures)")
        lines.append("| Name | Description |")
        lines.append("|------|-------------|")
        for s in skills:
            lines.append(f"| `{s['name']}` | {s.get('description', '')} |")
    
    lines.append("")
    lines.append("## Execution Method Selection")
    lines.append("- Single status check → dispatch (mode=shell)")
    lines.append("- Multi-step work plan → execute-plan (tasks array)")
    lines.append("- Registered standard procedure → playbook/run")
    lines.append("- Do NOT use dispatch mode=auto in production.")
    
    return "\n".join(lines)
```

### 정적/동적 경계

```python
# cache.py

STATIC_SECTIONS = ["identity", "safety", "workflow", "output"]
DYNAMIC_SECTIONS = ["tools", "environment", "experience", "local_knowledge"]

CACHE_BOUNDARY = "__PROMPT_CACHE_BOUNDARY__"

def compose_with_cache(role: str, context: dict) -> tuple[str, str]:
    """(정적 부분, 동적 부분) 반환 — Ollama keep_alive와 연동 가능"""
```

### pi_adapter 통합

```python
# pi_adapter/runtime/client.py 변경

# 기존:
# system_prompt = request.context.get("system_prompt") or _role_system_prompt(role)

# 변경:
from packages.prompt_engine import compose

system_prompt = request.context.get("system_prompt") or compose(role, request.context)
```

## 영향 파일 (OpsClaw 기준)

| 파일 | 변경 내용 |
|------|----------|
| `packages/prompt_engine/` | **신규** — 전체 패키지 |
| `packages/pi_adapter/runtime/client.py:214` | `compose()` 호출로 교체 |
| `apps/subagent-runtime/src/main.py:363-404` | mission 프롬프트를 `compose("subagent", {...})` 활용 |
| `apps/manager-api/src/main.py:639-643` | dispatch 변환 프롬프트를 `compose("manager", {...})` 활용 |
| `apps/manager-api/src/main.py:2239-2243` | chat 프롬프트를 `compose("manager", {...})` 활용 |
| `apps/manager-api/src/portal_routes.py:964-986` | AI 튜터 프롬프트를 전용 섹션으로 |

## 구현 계획

1. `packages/prompt_engine/` 패키지 생성 (섹션 함수들)
2. `compose()` 함수 구현 (섹션 조합)
3. `pi_adapter/runtime/client.py` 통합
4. `subagent-runtime` mission/explore/daemon 프롬프트 모듈화
5. `manager-api` dispatch/chat 프롬프트 통합
6. 테스트: 동일 요청에 대한 LLM 응답 품질 비교

## 검증 방법

1. `compose("manager", {})` 호출 → 프롬프트 내용 확인 (print 검증)
2. `compose("master", {"tools": [...], "server": "secu"})` → 동적 섹션 포함 확인
3. OpsClaw Mode B 테스트 (`scripts/m15_mode_b_test.py`) 재실행
4. Before/After: "서버 현황 수집해줘" 요청에 대한 LLM 응답 비교
