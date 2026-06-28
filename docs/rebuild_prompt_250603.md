# Bastion — 완전 재구축 프롬프트 (Rebuild Prompt)

> **목적**: 이 단일 문서만으로 Bastion 프로젝트 전체를 처음부터 재구축(rebuild)할 수 있도록,
> 모든 모듈·클래스·함수·DB 스키마·프롬프트·인프라·운영 규칙을 최신 상태(2026-06-03 / HEAD `c0a07b3`)로 정리한다.
> AI 에이전트(예: Claude Code)에게 이 문서를 그대로 전달하면 동일한 시스템을 복원할 수 있어야 한다.
>
> **기준 커밋**: `c0a07b3 feat(cycle2): 분석 4축 형식 강제 + 필드 부재 시 3가지 대안 탐색`
> **리포지토리**: https://github.com/mrgrit/bastion

---

## 0. 한 줄 요약 / 재구축 지시문

당신은 **Bastion**을 재구축한다. Bastion은 *자연어로 사이버보안 인프라를 운영하는 LLM 에이전트*다.
학생/운영자가 자연어로 보안 작업을 지시하면, Manager LLM(`gpt-oss:120b`, Ollama 서빙)이
Skill/Playbook을 선택하고 **ReAct 루프**로 도구를 실행하며, 각 VM에 상주하는 **SubAgent**에게
**A2A HTTP 프로토콜**로 명령을 위임한다. 모든 실행은 **Knowledge Graph(KG)** + **Experience Layer** +
**append-only 해시체인 Audit**에 기록되어 점진적으로 학습/개선된다.

언어: 코드 주석·프롬프트·사용자 출력은 모두 **한국어**. 코드는 Python 3.10+ (`from __future__ import annotations`).
방어적 코딩 철학: 외부 호출(LLM/KG/graph/audit/history/experience)은 거의 전부 try/except로 감싸 실패해도 `chat()`이 멈추지 않게 한다(KG만 stderr에 `[KG-WARN]` 가시화).

---

## 1. 시스템 토폴로지 / 두 개의 HTTP 서버 (혼동 금지)

| 서버 | 위치 | 포트 | 프레임워크 | 역할 |
|---|---|---|---|---|
| **Bastion API** (`api.py`) | bastion/manager 호스트 (`/opt/bastion`) | **8003** | FastAPI + uvicorn | 헤드리스 제어평면 API. `BastionAgent.chat()` 구동, KG/History/Audit/Work 엔드포인트, Ollama 프록시. 모든 인프라 스크립트가 관리. |
| **CCC SubAgent** (생성되는 `agent.py`) | 각 학생 VM (`/opt/ccc-subagent`) | **8002** | Python stdlib `http.server` (프레임워크 없음) | A2A 명령 실행기. `onboard_vm()`이 설치. FastAPI 아님. |

추가 외부 의존: **Ollama**(기본 `http://192.168.0.105:11434`), **syslog 송신**(514/udp, facility LOCAL5 → `SIEM_HOST` 기본 `10.20.32.100`).

### 실습 인프라 (6-VM 사이버 레인지)

| 역할(role) | 내부 IP | 외부 IP(예시) | 설명 |
|---|---|---|---|
| attacker | 10.20.30.201 | 192.168.0.112 | Kali 도구 (nmap, hydra, sqlmap, nikto) |
| secu | 10.20.30.1 | 192.168.0.114 | Security GW (nftables, Suricata IDS) |
| web | 10.20.30.80 | 192.168.0.100 | Apache, ModSecurity WAF, JuiceShop, DVWA |
| siem | 10.20.30.100 | 192.168.0.111 | Wazuh Manager SIEM |
| manager(bastion) | 10.20.30.200 | 192.168.0.115 | Bastion API + Ollama 연결 |
| windows | 10.20.30.50 | — | (수동 온보딩) |

일부 환경은 el34 **컨테이너** 인프라로 동작(`el34-bastion`, `el34-attacker`, `el34-ips`, `el34-siem`, `el34-web`, `el34-fw`, `el34-dvwa` 등). `bastion` 호스트(127.0.0.1)는 docker.sock(RO)을 마운트하고 KG DB를 보유하므로 `run_command`가 SubAgent를 거치지 않고 로컬 subprocess로 직접 실행한다.

---

## 2. 디렉터리 구조 / 파일 목록

```
/opt/bastion/                  (= 리포지토리 루트, .venv/ 포함)
  api.py                       (1243줄) Bastion 헤드리스 제어평면 API (FastAPI:8003)
  main.py                      (498줄)  Rich TUI 프런트엔드
  setup.sh                     첫 설치(venv+pip+systemd)
  bastion.sh                   TUI 런처
  upgrade.sh                   인플레이스 업그레이드(git pull + 재시작 + 헬스체크)
  sync_knowledge.sh            CCC 서버 → bastion 교육콘텐츠 동기화
  requirements.txt             6개 의존성
  .env.example                 환경변수 템플릿
  .gitignore                   .venv/ __pycache__/ *.pyc .env
  bastion-api.service          systemd 유닛 (uvicorn api:app :8003)
  CCC.md                       운영 지침서(시스템 프롬프트에 주입)
  README.md / ARCHITECTURE.md  문서
  bastion/                     — 에이전트 코어 패키지
    __init__.py                (1694줄) Config, A2A 클라이언트, SSH 온보딩, run_command/health_check, INTERNAL_IPS
    agent.py                   (3829줄) BastionAgent + EvidenceDB + ReAct 루프 (핵심)
    skills.py                  (1317줄) SKILLS 레지스트리(33개) + execute_skill/preview_skill
    playbook.py                (325줄)  YAML Playbook 엔진 (schema v2)
    prompt.py                  (190줄)  build_planning_prompt / build_system_prompt
    rag.py                     (214줄)  교육콘텐츠 RAG (인메모리 BM25-like)
    experience.py              (443줄)  Experience Learning Layer (오버피팅 방지)
    audit.py                   (348줄)  append-only SHA-256 해시체인 감사로그
    verify.py                  (267줄)  온보딩 인프라 검증 (SSE)
    lab_verify.py              (128줄)  Lab 콘텐츠 검증 (SSE)
    history.py                 (342줄)  PE-KG-H L4 History 레이어(이벤트/내러티브/앵커/체인지로그)
    graph.py                   (435줄)  KnowledgeGraph (SQLite + FTS5)
    graph_migrate.py           (278줄)  KG 1회성 마이그레이션 임포터
    kg_context.py              (381줄)  KG 컨텍스트 빌더(프롬프트 주입)
    kg_recorder.py             (247줄)  구조화 결과 앵커 레코더
    kg_metrics.py              (73줄)   인메모리 Prometheus형 메트릭
    lookup.py                  (318줄)  KG-4 playbook reuse/adapt/new 결정 엔진
    compaction.py              (287줄)  KG-5 경험 압축/증류(Insight 생성)
    work_domain.py             (268줄)  9계층 작업 위계(Mission..Todo) KG 헬퍼
    asset_domain.py            (162줄)  자산/아키텍처 도메인 KG 헬퍼
  contents/
    playbooks/*.yaml           8개 정적 Playbook
    docs/bastion-prompt-guide.md  프롬프트 작성 가이드
```

> **참고**: 리포지토리에는 `src/`(TypeScript Claude Code 벤더 코드), `src.zip`이 존재하나 Bastion 런타임과 무관 — 재구축 대상 아님.

---

## 3. 환경변수 / 설정 (`bastion/__init__.py` 상단)

`_require_env(key)` 는 미설정 시 `ValueError(f"{key} is not set — add it to .env")` 를 던진다.

### `.env.example` (그대로 생성)
```
# Bastion 독립 실행 환경변수
LLM_BASE_URL=http://192.168.0.105:11434
LLM_MANAGER_MODEL=gpt-oss:120b
LLM_SUBAGENT_MODEL=qwen3:8b

# VM IP (내부 네트워크)
VM_ATTACKER_IP=10.20.30.201
VM_SECU_IP=10.20.30.1
VM_WEB_IP=10.20.30.80
VM_SIEM_IP=10.20.30.100
VM_MANAGER_IP=10.20.30.200

# Bastion API 포트
BASTION_API_PORT=8003
```

### 코드가 읽는 전체 환경변수
| 변수 | 기본/예시 | 의미 |
|---|---|---|
| `LLM_BASE_URL` | `http://192.168.0.105:11434` | Ollama 베이스 URL. **필수**. |
| `LLM_MANAGER_MODEL` | `gpt-oss:120b` | Manager/디스패처 모델. **필수**. `LLM_MODEL`=이 값. |
| `LLM_SUBAGENT_MODEL` | `qwen3:8b` | SubAgent/경량 모델. **필수**. Ollama 프록시가 강제하는 모델. |
| `LLM_MANAGER_MODEL_UNSAFE` | `gurubot/gpt-oss-derestricted:120b` | 공격/대전 과정용 derestricted 모델. |
| `LLM_FAST_ATTACK` | `1`/`true`/`yes` | 공격 과정도 일반 모델 강제. |
| `VM_ATTACKER_IP`/`VM_SECU_IP`/`VM_WEB_IP`/`VM_SIEM_IP`/`VM_MANAGER_IP` | 위 표 | 내부 IP. |
| `VM_WINDOWS_IP` | `10.20.30.50` | windows VM. |
| `VM_BASTION_IP` | `127.0.0.1` | bastion 자기 자신. |
| `VM_INTERNAL_SUBNET` | `10.20.30.0/24` | 내부 서브넷. |
| `BASTION_API_PORT` | `8003` | API 포트(`__main__`). |
| `SIEM_HOST` | `10.20.32.100` | 라이프사이클/감사 syslog 수신지(UDP 514, LOCAL5). |
| `SSH_USER` | `ccc` | 로컬 subprocess 실행 사용자(`su - ccc`). |
| `CCC_DIR` | `<pkg>/../..` | CCC 루트. |
| `SUBAGENT_PORT` | `8002` | SubAgent 포트. |
| `BASTION_GRAPH_DB` | (해석규칙) | KG SQLite 경로 override. |
| `BASTION_AUDIT_DB` | (해석규칙) | 감사 SQLite 경로 override. |
| `BASTION_PLAYBOOKS_DIR` | (해석규칙) | Playbook 디렉터리 override. |
| `DATABASE_URL` | `postgresql://ccc:ccc@127.0.0.1:5434/ccc` | (main.py의 선택적 VM IP 조회) |

### 모듈 상수 (`__init__.py`)
```python
LLM_MODEL = LLM_MANAGER_MODEL
SUBAGENT_PORT = 8002
SSH_TIMEOUT = 120
INTERNAL_IPS = {  # 각 항목 env VM_<ROLE>_IP 로 override
  "attacker":"10.20.30.201", "secu":"10.20.30.1", "web":"10.20.30.80",
  "siem":"10.20.30.100", "manager":"10.20.30.200",
  "windows":"10.20.30.50", "bastion":"127.0.0.1",
}
SECU_GW = INTERNAL_IPS["secu"]
VM_INTERNAL_SUBNET 기본 "10.20.30.0/24"
```

---

## 4. A2A 클라이언트 + SSH 온보딩 (`bastion/__init__.py`)

이 모듈은 (1) 저수준 A2A 클라이언트 헬퍼, (2) SSH 온보딩, (3) CCC 운영 에이전트용 `PROMPT_SECTIONS`(identity/architecture/capabilities/constraints/reasoning)를 제공한다. `agent.py`의 `BastionAgent`는 여기서 `run_command`, `health_check`, `INTERNAL_IPS`, `LLM_*`를 임포트한다.

### A2A 클라이언트 헬퍼
- `_is_local_ip(ip)` — `127.0.0.1` 또는 bastion 자기 IP면 True.
- `health_check(ip) -> dict` — 로컬이면 subprocess, 아니면 `GET http://{ip}:8002/health`. 반환 `{"status":"healthy", ...}`.
- `run_command(ip, script, timeout=60) -> dict` — 로컬이면 `su - {SSH_USER} -c` 로 직접 실행(필요 시 `ssh -tt` 자동 주입), 아니면 `POST http://{ip}:8002/a2a/run_script` body `{"script","timeout"}`. 반환 `{stdout, stderr, exit_code}`(필요 시 `output`).
- `audit_start/run/stop(ip, session_id, ...)` — A2A 감사 세션 변형.

### SubAgent A2A 프로토콜 (각 VM 8002, stdlib http.server)
```
GET  /health                 → {"status":"healthy","hostname","role"}
POST /a2a/run_script         body {script, timeout=60}
                             → {exit_code, stdout(≤10000), stderr(≤5000)}  # subprocess.run(shell=True)
POST /a2a/audit/start        body {session_id, lab_id, student_id}
POST /a2a/audit/run          body {session_id, script, timeout_s}
POST /a2a/audit/stop         body {session_id}  → transcript
```
SubAgent systemd: `ccc-subagent.service`, `ExecStart=python3 /opt/ccc-subagent/agent.py`, `Environment=CCC_ROLE=<role>`, `Restart=always/5s`.

### `onboard_vm(ip, role, user="ccc", password="1", gpu_url, manager_model, subagent_model)` — 제너레이터(SSE)
sshpass로 외부 IP에 SSH 접속 후: SSH/sudo 검증(`ssh_test`) → SubAgent 설치(`SUBAGENT_INSTALL_SCRIPT`가 `/opt/ccc-subagent/agent.py` + `ccc-subagent.service` 작성, `systemctl enable --now`) → 역할별 SW 설치 → 내부 고정 IP 설정 → 기본 게이트웨이를 Security GW 경유로 변경(`role=="secu"` 제외, NAT off) → 8002 헬스체크. `role=="windows"`는 스킵. manager/bastion 역할은 `/opt/bastion` git clone + venv 빌드 + 호스트네임 `bastion` 설정 + `ccc` 사용자용 chown/symlink. 단계별 `{event:"step",...}` yield.

---

## 5. `bastion/agent.py` — 핵심 오케스트레이션 (3829줄)

모듈 docstring: "Bastion Agent v3.1 — opsclaw 설계 원칙 기반". 3-stage 상태머신 `PLANNING → EXECUTING → VALIDATING`.

### 5.1 임포트
```python
from __future__ import annotations
import json, os, re, sqlite3, sys, time, unicodedata
from typing import Generator
import httpx
from bastion.playbook import list_playbooks, load_playbook, run_playbook
from bastion.prompt import build_system_prompt, build_planning_prompt
from bastion.rag import build_index, format_context
from bastion.skills import SKILLS, SKILL_CATEGORIES, execute_skill, preview_skill, skills_to_ollama_tools
```
나머지(experience/history/kg_context/kg_metrics/lookup/graph/kg_recorder/audit/asset_domain 등)는 메서드 내부에서 lazy 임포트.

### 5.2 모듈 헬퍼 함수
- `sanitize_text(text)` — 제어문자/IME 잔여(` ​　﻿`) 제거, `\t\n` 유지, 공백 정규화, strip.
- `extract_json(text)` — 코드펜스 제거 후 `json.loads`, 실패 시 중괄호 깊이 카운트로 첫 균형 객체 추출. dict만 반환.
- Harmony 포맷 처리(gpt-oss/abliterated): `_HARMONY_TOKEN_RE`, `_HARMONY_BLOCK_RE`(channel: analysis/thinking/final), `_strip_harmony(text)`, `_HARMONY_TOOLCALL_RE`(`to=functions.NAME {ARGS}`), `_extract_harmony_tool_calls(text)->[(name,args)]`.
- JSON tool-call fallback: `_JSON_TOOLCALL_PATTERNS`(4개 정규식: `name/arguments`, `tool/parameters`, `function/args`, `tool_name/input`), `_extract_json_tool_calls(text)`.
- 프로즈/명령 추출: `_PROSE_CMD_RE`, `_BACKTICK_CMD_RE`, `_BANG_CMD_RE`, `_CODEBLOCK_CMD_RE`, `_CMD_LINE_PREFIXES`(~80개 도구명), `_CMD_LINE_RE`, `_extract_command_from_acceptable_methods(methods)`(verify ground-truth fallback), `_extract_shell_from_prose(text)`(백틱>코드블록>"Running:"동사>prefix라인>!cmd, 한국어 조사 필터링 후 도구명+IP/포트/URL 조합 합성, 상위 3개), `extract_json_array(text)`.

### 5.3 `EvidenceDB` 클래스 (evidence-first SQLite)
DDL `CREATE_SQL`:
```sql
CREATE TABLE IF NOT EXISTS evidence (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT DEFAULT (datetime('now')),
    stage TEXT, skill TEXT, playbook_id TEXT, params TEXT,
    success INTEGER, exit_code INTEGER, output TEXT, analysis TEXT, session_id TEXT
);
CREATE TABLE IF NOT EXISTS assets (
    role TEXT PRIMARY KEY, ip TEXT, status TEXT DEFAULT 'unknown',
    last_seen TEXT, notes TEXT
);
```
`MIGRATIONS`(idempotent ALTER, OperationalError 무시): `stage, playbook_id, exit_code INTEGER DEFAULT -1, session_id, course, lab_id, step_order INTEGER, test_session` 추가.

DB 경로 해석: `db_path` 인자 → `cwd/bastion_evidence.db` → `~/bastion_evidence.db` → `/tmp/bastion_evidence.db`. 첫 오픈 가능 후보 채택. 모두 실패 시 persistent `:memory:`.

메서드:
- `add(*, skill="", playbook_id="", params=None, success, exit_code=-1, output="", analysis="", stage="", session_id="", course="", lab_id="", step_order=0, test_session="") -> rowid` (`success` 키워드 필수, output≤5000, analysis≤2000, params json.dumps).
- `recent(limit=10)`, `search(keyword, limit=5)`(skill/output/analysis/playbook_id LIKE), `stats()->{total,success,fail}`, `recent_context(limit=3)->"[이전 실행 기록]..."`, `update_asset(role, ip, status, notes="")`(INSERT OR REPLACE + datetime('now')), `get_assets()`(ORDER BY role).

### 5.4 `BastionAgent.__init__(self, vm_ips, ollama_url="", model="", knowledge_dir="", evidence_db="", approval_mode="normal")`
인스턴스 속성: `vm_ips`, `ollama_url`(rstrip "/"), `model`(=model or LLM_MANAGER_MODEL), `history=[]`, `session_id=f"s{int(time.time())}"`, `evidence_db=EvidenceDB(...)`, `_test_meta={}`(course/lab_id/step_order/test_session/user_id/source_ip), `_eg_mode="full"`, `approval_mode`, `experience=ExperienceLearner(db_path=evidence_db.db_path)`, `history_layer=HistoryLayer() or None`, `rag_index=build_index(kdir) or None`(kdir 기본 `<file>/../../contents`), `_last_kg_status={}`, `_last_kg_record={}`. 외부 설정 속성: `attack_mode`(getattr default False), `_verify_context`(intent/success_criteria/acceptable_methods/negative_signs), `_retry_history`.

### 5.5 `chat(message, approval_callback=None) -> Generator[dict]` (공개 진입점)
스텝 재시도 + 감사 로깅 래퍼. 1 chat = 1 audit row.
1. `original = sanitize_text(message)`; 빈 값 return.
2. 감사 초기화: `request_id=uuid4().hex`, `ts_start`, 버퍼(`audit_turns/skills/lookup/judge/final_answer`).
3. 내부 `_audit_record_turn(evt)` 가 이벤트별 누적: `lookup_decision`, `skill_start`, `skill_result`, `risk_warning`, `skill_skip`, `self_verify_fail`, `stream_token`(→final_answer 누적).
4. **스텝 재시도 루프** `MAX_STEP_RETRY=2`: `_chat_once` 이벤트를 yield/버퍼링. 실패 시 `step_retry{attempt,feedback}` yield 후 `[자기 수정 — 이전 시도가 부족함]` 프롬프트로 재시도.
5. **`finally`**: `kg_status{context,record}` 이벤트 emit, 필요 시 `_kg_warn` stderr, **`get_audit_log().append(...)`** (request_id/session_id/user/source_ip/ts/duration/user_prompt(raw)/final_answer/approval_mode/course/lab_id/step_order/verify_intent/lookup/turns/skill_calls/judge/outcome/model_used/bastion_version="kg-v1"/test_meta). 전부 try/except.

`_step_attempt_ok(original, events)->(bool,reason)`: skill_result 성공 / subtask_done 달성 / Q&A 충분(`_classify_intent.execute==False`)이면 OK.

### 5.6 `_chat_once(message, approval_callback=None) -> Generator` (코어 파이프라인)
1. **멀티태스크 분할** `_maybe_split_multitask` (힌트 + 번호목록 ≥3) → `multitask_split{count,tasks}`, 각 subtask `subtask_start`/recurse `self.chat(sub)`/`subtask_done`; return.
2. user를 history 추가, `_compress_history()`.
3. 컨텍스트: `rag_ctx`(rag_index.search top_k=3 → format_context), `prev_ctx`(recent_context), `exp_ctx`(experience.get_context — **`_eg_mode in ("experience","full")` 일 때만**).
4. **STAGE 1 PLANNING**: `stage{stage:"planning"}`.
5. **정적 Playbook(1-a)**: `_select_playbook(message)` — **`_eg_mode in ("playbook","full")` 일 때만**. 매칭 시 `playbook_selected` → `stage:executing` → `run_playbook(...)` → `stage:validating` → `_stream_analysis_events` → evidence.add(stage="playbook") → return.
6. **ReAct 진입**: `intent_quick=_classify_intent(message)`. `intent_quick.execute` 또는 `_is_action_request(message)` → `_chat_react(...)`; 아니면 `_qa_with_extraction(message)`.
7. (line 968 이후는 LEGACY dead code — `return` 이후. 보존하되 비활성으로 표시: 구 4-stage fallback `_select_skills_multi`→`_generate_dynamic_playbook`/`_run_dynamic_steps`→`_qa_with_extraction`, `plan_preview`, `MAX_RETRY=2` 재시도, IoC 앵커, asset autoscan 등.)

### 5.7 ReAct 루프 `_chat_react(message, rag_ctx, prev_ctx, exp_ctx, approval_callback=None)` (핵심)
- `sys_prompt = _build_react_system_prompt()`.
- **KG-4 lookup**(`_eg_mode in ("playbook","full")`): `decide(message, ollama_url, model)` → `lookup_decision{decision,playbook_id,confidence,reason}` → `build_lookup_prompt` 결과를 sys_prompt에 append. 아니면 `lookup_decision{decision:"skipped_eg_mode"}`.
- 컨텍스트 append(`## 참고 자료 (RAG)`, `## 최근 실행 컨텍스트`, `## 학습된 패턴`).
- `msgs=[system,user]`; **`msgs=_inject_kg_context(msgs)`** (ReAct는 httpx.post 직접 호출이라 명시 주입; KG 블록이 6턴 내내 system에 유지).
- `tools_spec=_select_relevant_tools(message, max_n=12)`.
- 루프 상수: `MAX_TURNS=6`, `SELF_VERIFY_RETRY=1`, `FIRST_TURN_RETRY=1`, `EMPTY_CONTENT_RETRY=2`.
- **턴**: `POST /api/chat {model, messages, tools, stream:False, options:{temperature:0.2, num_predict:1500}, timeout:180}`. `content/thinking/tool_calls` 추출.
  - tool_calls 없으면 합성 fallback: ① harmony(`synthesized_tool_calls{source:"harmony_format"}`) ② json_markdown ③ prose_fallback(shell 합성). 각 첫 ≤2 valid SKILLS.
  - content 스트리밍(100자 청크 `stream_token`), assistant 메시지 append.
  - **종료 후보(tool_calls 없음)**: EMPTY_CONTENT_RETRY(content<30 & thinking<50 → 강제 tool 호출 유도), FIRST_TURN_RETRY(turn0 무출력, refusal 감지 시 lab-context 힌트), `_force_self_verify`, **self-verify(1회)** `_self_verify_completion` 실패 시 `self_verify_fail` + raw-dump 감지(`_is_raw_dump`) → 분석전용 지시 / 미인용 재시도 / 기준 5단계 가이드. OK면 break.
  - **tool_calls 있음**: turn0 → `stage:executing`. 각 tc: `_enrich_params` → `_assess_risk`(high/critical → `risk_warning`) → `_should_ask_approval`+approval_callback(거부 시 `skill_skip{reason:"denied"}`) → `_pre_check`(실패 `precheck_fail`) → `skill_start{attempt:1}` → `execute_skill` → `skill_result{output[:2500],attempt:1}` → tool 메시지 append(`[skill=.. success=.. exit=..]\nstdout(앞 3000자)`) → evidence.add(stage="skill") + experience.record + probe/check_* 자산 갱신.
- **포스트 루프 fallback**(MAX_TURNS 소진+무출력 또는 `_is_general_punt`): ① prose ② acceptable_methods ③ LLM translate(컨테이너명→IP 변환 금지, docker exec/ssh/quotes 보존, temp 0.0). → `prompt_fallback_attempt`/`synthesized_tool_calls`/실행/`skill_result`.
- **VALIDATING** `stage:validating`: punt/plan-only 감지(`_content_is_punt`), 필요+`all_tool_outputs` 있으면 **synthesis**(`_synth_prompt` 9개 anti-hallucination 규칙; 도구 실패만이면 "가짜 결과 금지"). LLM `temp 0.0, num_predict 800, timeout 60`, `stream_token`. → history append → `_persist_react_run_to_graph(...)` → 경험→Playbook 승격(10패턴마다).

### 5.8 `_build_react_system_prompt()` 주요 섹션 (프롬프트 텍스트로 구현)
SKILL_CATEGORIES별 카탈로그(`▼ {cat} — 트리거: {trigger}`), vm_info, **`## 채점 기준`**(verify_context 있을 때 의도/성공기준/허용방법/피해야할 신호), **attack_preamble**(attack_mode 시 "★ LAB CONTEXT — 격리 사이버 레인지, 합법 학습. 거부 금지"), `## 작업 흐름`(ReAct 4-step: 첫 턴 GOAL/SUCCESS/todo + 첫 tool 호출; tool_calls 없는 응답=작업 끝, "GOAL 충족됨:" 명시), `## ★ 실행 원칙`(코드예시만 금지/실제 shell·python3 호출/장애처리 command not found→apt-get·pip3, 404→다른 경로, 401→토큰; **빈 필드 시 최소 3가지 대안**: ① 다른 필드(data.src_ip/srcip/client_ip/user/rule.id) ② 다른 decoder/rule.groups(syslog,sshd,haproxy-denat,modsec) ③ de-NAT 원본 srcip — shell jq/python3로 3개 시도 후 "데이터 없음"), **`## ★ 분석·조사 task 의 final 답변 형식 (4축 모두 채울 것)`**(cycle2 최신: ① 타임라인 HH:MM:SS—event ② 정량수치 count/avg/stddev/ratio/% ③ 표준매핑 OWASP A0X/MITRE T1XXX/CVE/rule.id ④ 결론·권고 1~3개 IP/rule/command), `## ★ el34 실제 자산 매핑`(컨테이너 IP표 + docker exec 요구), `## ★ 조회 vs 변경 — 절대 혼동 금지`, Skill 선택 휴리스틱, Attack-mode 매핑, IR/build/CI/test 카테고리(probe 금지), `## ★★ Web-vuln-ai`(OWASP 페이로드 라이브러리 A01 IDOR/A03 SQLi·NoSQL/XSS/A05 SSRF/JWT/역직렬화/SSTI/GraphQL DoS/prototype pollution/CORS/CSRF/HTTP smuggling/path traversal/cmd injection), `## ★ 응답 분석·검증 명령 패턴`(curl -i/-sIL/diff), `## ★★ 최종 답변 작성 규칙`(4 필수 섹션: 실행결과 코드블록 필수/취약점 입증 payload→response/방어 언급/한계·인지), 도구 호출 예시 5개, VM 인프라, `## 핵심 원칙 (★ 강제)`(첫 턴 ≥1 tool_call, 비대화형 shell, self-eval).

### 5.9 KG 주입/스트리밍/검증 헬퍼
- `_inject_kg_context(messages)`: `_last_kg_status` 리셋. `_eg_mode=="off"`면 skip(`eg_mode_off`). `get_builder().build(last_user, model, eg_mode).format()` → 비어있지 않으면 첫 system에 `\n\n---\n\n{block}` append. 실패 시 `_kg_warn`+metric.
- `_kg_warn(msg)` → stderr `[KG-WARN] {msg}`. `_kg_metric_inc(name, labels=None)`.
- `_stream_llm(messages, max_tokens=600, temperature=0.3)` → KG 주입 후 `httpx.stream POST /api/chat stream:True`. 토큰 yield.
- `_stream_analysis_events(user_msg, results)` → `stream_start{label:"분석"}`/token/end, max_tokens=600 temp 0.1. 전체 텍스트 반환.
- `_stream_qa_events(message)` → `stream_start{label:"답변"}`, history[-8:], max_tokens=600 temp 0.3.
- `_self_verify_completion(original, tool_outputs, final_content)->(bool,why)`: stdout 인용 검사(16자 청크), criteria 없으면 any-success, 있으면 LLM judge(`format:json temp 0.0 num_predict 200 timeout 30`).
- `_diagnose_and_correct(...)` → `{diagnosis,action,skill,params}` (format:json temp 0.1 num_predict 300 timeout 20).

### 5.10 분류/라우팅/리스크
- `_classify_intent(message)->{execute,target_vm,command}`: concrete cmd / exec keyword / (infra+verify) fast-path → execute True; 아니면 LLM(format:json temp 0.0 num_predict 600 timeout 20), infra/verify 멘션 시 execute 승격. 예외 시 execute=True.
- `_is_action_request`, `_infer_target_vm`(키워드+`_VM_ROUTE_RULES`, 기본 attacker), `_select_playbook`(concrete cmd면 None, 아니면 LLM `/api/generate` temp 0.0 num_predict 20 timeout 10 → playbook_id|none).
- 정규식 상수: `_CONCRETE_CMD_PATTERNS`(~70 도구명), `_EXEC_KEYWORDS`, `_INFRA_MENTIONS`, `_VERIFIABLE_ASK`, `_VM_ROUTE_RULES`, `_QA_ONLY_PATTERNS`, `_QA_CODE_BLOCK`, `_QA_INLINE_CMD`, `_DESTRUCTIVE`, IoC 정규식(`_IOC_IP_RE`/`_IOC_SHA256_RE`/`_IOC_DOMAIN_RE`+`_IOC_BLACKLIST`), `_CORE_SKILLS={shell,file_manage,probe_host,probe_all,ollama_query}`, `_SKILL_TRIGGERS`.
- **리스크**: `_SAFE_COMMAND_HEADS`(~90 읽기전용), `_SAFE_PREFIX_RE`, `_CRITICAL_PATTERNS`(rm -rf, kill -9, dd of=/dev/sd, mkfs, shutdown/reboot, fork bomb, chmod 777 /, iptables -F, nft flush, systemctl stop sshd/wazuh, userdel/groupdel, DROP TABLE, TRUNCATE, DELETE FROM), `_HIGH_PATTERNS`, `_classify_command_risk(cmd)->safe|low|medium|high|critical`(파이프 분할, 최악 우선), `_assess_risk(skill,params)`(shell→cmd risk; configure_nftables/deploy_rule→high; scan_ports/web_scan/attack_simulate→medium; else low).
- `_should_ask_approval(risk, skill_def=None)`: **approval_mode** — `danger_danger_danger`/`yolo`=never; `danger_danger`=critical만; `normal`=high/critical 또는 `requires_approval`.
- `_pre_check(skill,params)`: docker 기반 skill(`docker_manage,check_modsecurity,check_suricata,check_wazuh,probe_host,probe_all`)·`docker ` 명령은 스킵; local→True; 아니면 health_check.
- `_enrich_params(skill,params)`: role→IP(target/host/ip), 고정 target_vm 자동 채움.

### 5.11 그래프 영속화 `_persist_react_run_to_graph(message, turn_traces, tool_outputs, final_content, lookup_result=None)`
`_eg_mode=="off"` 또는 무출력 시 스킵. CATEGORY_RULES 분류. `sig=sha1(message[:200]+"|"+skills)[:10]`, `pb_id`(lookup reuse/adapt면 pb- 접두, 아니면 `pb-auto-{slug}-{sig}`). 기존 노드면 `update_exec_history`, 아니면 `write_playbook`(version 1, reasoning, plan, exec_history, _auto_generated:True) + `Playbook` 노드 + `uses/targets/handles` 엣지. 매번 **Experience 노드**(`exp-{ts}-{sig}`) + `derived_from/uses/targets/handles` 엣지. **KGRecorder.record_task_outcome**(mitre_ids=extract_mitre_ids, evidence_excerpt[:500]) → `_last_kg_record`.

### 5.12 기타 메서드
`_qa_with_extraction`(QA 스트리밍 후 명령 추출 실행/`ask_user`), `_extract_commands_from_qa`/`_subagent_extract_commands`(gemma3:4b fallback), `_verify_output_satisfies`(format:json default True), `_generate_shell_command`, `_select_skills_multi`(legacy: tool calling→json array→prose), `_generate_dynamic_playbook`(legacy), `_run_dynamic_steps`(legacy), `_compress_history`(>12턴 시 오래된 6턴 LLM 3줄 요약 → index0 system 삽입), `_select_relevant_tools(message, max_n=12)`(name+10, trigger+3, _CORE_SKILLS 항상 포함), `_extract_iocs`, `_update_assets_from_result`, `_ip_to_role`. 공개: `get_skills/get_playbooks/get_evidence/search_evidence`.

### 5.13 LLM 호출 패턴 요약
| 호출자 | 엔드포인트 | stream | format | temp | num_predict | timeout |
|---|---|---|---|---|---|---|
| `_stream_llm` | /api/chat | True | — | 0.3 | 600 | 90 |
| ReAct 메인 턴 | /api/chat(+tools) | False | — | 0.2 | 1500 | 180 |
| ReAct synthesis | /api/chat | False | — | 0.0 | 800 | 60 |
| ReAct fallback translate | /api/chat | False | — | 0.0 | 200 | 20 |
| `_self_verify_completion` | /api/chat | False | json | 0.0 | 200 | 30 |
| `_verify_output_satisfies` | /api/chat | False | json | 0.0 | 100 | 15 |
| `_diagnose_and_correct` | /api/chat | False | json | 0.1 | 300 | 20 |
| `_classify_intent` | /api/chat | False | json | 0.0 | 600 | 20 |
| `_generate_dynamic_playbook` | /api/chat | False | json | 0.0 | 600 | 15 |
| `_subagent_extract_commands` | /api/chat | False | — | 0.1 | 200 | 15 |
| `_compress_history` | /api/chat | False | — | 0.1 | 200 | 30 |
| `_select_playbook` | /api/generate | False | — | 0.0 | 20 | 10 |
| `_generate_shell_command` | /api/generate(manager+subagent) | False | — | 0.0 | 200/120 | 15/12 |

### 5.14 이벤트 인벤토리 (yield되는 dict의 `event`)
`stage`(planning/executing/validating/qa), `multitask_split{count,tasks}`, `subtask_start{index,total,task}`, `subtask_done`, `step_retry{attempt,feedback}`, `kg_status{context,record}`, `playbook_selected{playbook_id,title}`, `lookup_decision{decision,playbook_id,confidence,reason}`, `lookup_error`, `synthesized_tool_calls{source,skill,args/command}`, `empty_content_retry{content_len,thinking_len,attempt}`, `first_turn_retry{reason}`, `self_verify_fail{reason}`, `risk_warning{skill,risk}`, `skill_skip{skill,reason}`, `precheck_fail{skill,message}`, `skill_start{skill,params,attempt}`, `skill_result{skill,success,output,attempt}`, `error{stage,error}`, `prompt_fallback_attempt{command,source}`, `graph_persist_error`, `message{content}`, `stream_start{label}`, `stream_token{token}`, `stream_end`, `qa_to_exec{extracted,preview}`, `ask_user{question,context}`. (Legacy dead path: `plan_preview`, `verify_miss`, `self_correct`, `repeat_ioc_match`, `asset_autoregistered(_bulk)`, `autoscan_error`, `playbook_start/step_start/step_done/playbook_done`, `playbook_abort`.)

### 5.15 EG-mode ablation (`_eg_mode`: off/playbook/experience/full)
| 메커니즘 | off | playbook | experience | full |
|---|---|---|---|---|
| experience 주입(exp_ctx) | ✗ | ✗ | ✓ | ✓ |
| 정적 playbook `_select_playbook` | ✗ | ✓ | ✗ | ✓ |
| KG context 주입 | ✗(skip `eg_mode_off`) | ✓ | ✓ | ✓ |
| lookup decide+inject | ✗(`skipped_eg_mode`) | ✓ | ✗ | ✓ |
| 그래프/앵커 영속화 | ✗(early return) | ✓ | ✓ | ✓ |

`off` = 진짜 No-KG/No-EG. 기본 운영=`full`.

---

## 6. `bastion/skills.py` — 33개 Skill 레지스트리 (1317줄)

```python
from __future__ import annotations
import re
from typing import Any
from bastion import run_command, health_check, INTERNAL_IPS
```
> **재구축 주의(잠재 버그)**: `execute_skill`이 `ioc_export/memory_dump/prompt_fuzz`에서 `time.*`/`json.*`를 사용하지만 상단에 `import time, json`이 없어 NameError 발생. **상단에 `import time, json` 추가 권장.** 그 외 의존은 브랜치 내 lazy 임포트(`base64`, `httpx`, `urllib`, `uuid`).

### 6.1 `SKILL_CATEGORIES` (시스템 프롬프트 그룹핑)
키→`{"skills":[...],"trigger":"..."}`:
- `"정찰 (Recon)"`: probe_host, probe_all, scan_ports, dns_recon, web_scan, cve_lookup — trigger `"포트/서비스/도메인/취약점/배너/CVE 식별, 초기 정찰"`
- `"탐지·SIEM (Detect)"`: check_suricata, check_wazuh, check_modsecurity, analyze_logs, wazuh_api
- `"방어·룰 (Defend)"`: configure_nftables, deploy_rule, enroll_wazuh_agent
- `"공격·모의해킹 (Attack)"`: attack_simulate, password_attack, web_scan
- `"IR·포렌식 (IR/Forensic)"`: forensic_collect, memory_dump, process_kill, ioc_export
- `"AI 보안 (AI Sec)"`: prompt_fuzz, garak_probe, model_isolate, rag_corpus_check
- `"컴플라이언스 (Compliance)"`: compliance_scan, secret_scan
- `"장기기억 (History)"`: history_anchor, history_narrative
- `"범용 (Generic)"`: shell, file_manage, http_request, docker_manage, ollama_query

### 6.2 `SKILLS` — 전체 33개 (name → {description, params, target_vm, [requires_approval], [danger]})
각 skill의 정확한 description/params/target_vm/위험표시 (`danger`="danger"|"danger-danger"):

1. **probe_host** "호스트 상태 점검 — uptime, 디스크, 메모리, 실패 서비스 확인" / `target`(req) / auto
2. **scan_ports** "nmap 포트 스캔 — 대상의 열린 포트와 서비스 버전 확인" / `target`(req),`ports` / attacker
3. **check_suricata** "Suricata IDS 상태 확인 + 최근 알림 조회" / `lines` / secu
4. **check_wazuh** "Wazuh SIEM 매니저 상태 + 에이전트 목록 + 최근 알림" / {} / siem
5. **check_modsecurity** "ModSecurity WAF 상태 + 최근 차단 로그" / `lines` / web
6. **configure_nftables** "nftables 방화벽 관리 — 테이블/체인/set/룰 구조화 조작..." / `action`(req,enum=[list,list_tables,list_table,add_table,add_chain,add_set,add_element,add_rule,insert_rule,delete_table,delete_chain,delete_element,add,delete,raw]),`family,table,chain,set,set_type,hook,priority,policy,element,rule,command` / secu / **requires_approval**
7. **analyze_logs** "로그 파일을 수집하고 LLM으로 분석 — 이상 징후, 패턴, 요약" / `log_source`(req),`query`(req),`target`(req) / auto / uses_llm
8. **deploy_rule** "Suricata 또는 Wazuh 탐지 룰 배포" / `rule_type`(req,enum=[suricata,wazuh]),`rule_content`(req) / auto / **requires_approval**
9. **web_scan** "웹 취약점 스캔 — nikto 또는 curl 기반 헤더/디렉토리 점검" / `url`(req) / attacker
10. **shell** "임의 셸 명령 실행 — 다른 skill로 불가능한 작업 시 사용" / `command`(req),`target`(req, 라우팅 규칙 설명 포함) / auto / **requires_approval**
11. **ollama_query** "Ollama LLM API 직접 호출..." / `prompt`(req),`model,system,temperature,max_tokens` / local
12. **http_request** "HTTP 요청 전송 — GET/POST/PUT/DELETE..." / `url`(req),`method,headers,body,target` / attacker
13. **docker_manage** "Docker 컨테이너 관리 — ps/logs/exec/inspect/stats 등" / `action`(req,enum=[ps,logs,exec,inspect,stats,restart]),`container,command,target` / auto
14. **wazuh_api** "Wazuh REST API 호출..." / `endpoint`(req),`method,body` / siem
15. **file_manage** "파일 읽기/쓰기/검색..." / `action`(req,enum=[read,write,append,search,exists,list]),`path`(req),`content,pattern,target` / auto
16. **attack_simulate** "공격 시뮬레이션 — SQLi/XSS/brute-force/포트스캔..." / `attack_type`(req,enum=[sqli,xss,brute_ssh,brute_http,dir_scan,port_scan]),`target_url`(req),`payload` / attacker / **requires_approval**
17. **probe_all** "전체 인프라 상태 일괄 점검..." / {} / local
18. **enroll_wazuh_agent** "대상 VM에 wazuh-agent를 Wazuh Manager(siem)에 등록..." / `target`(req) / siem / **requires_approval**
19. **memory_dump** "휘발성 메모리 캡처 — LiME/winpmem..." / `target`(req),`out_path` / auto / danger / **requires_approval**
20. **process_kill** "특정 프로세스 격리·종료 — IR 컨테인먼트..." / `target`(req),`pid,name,signal` / auto / danger-danger / **requires_approval**
21. **ioc_export** "추출된 IoC를 STIX 2.1 Indicator JSON으로 직렬화..." / `iocs`(req),`title` / local
22. **forensic_collect** "포렌식 아티팩트 일괄 수집 — /var/log + ps + netstat + 최근 변경 파일" / `target`(req),`since_min` / auto / danger (approval 없음)
23. **prompt_fuzz** "프롬프트 변형 자동 생성 — base64/upper/reverse/multilingual..." / `base_prompt`(req),`system_prompt,leak_marker,model,mutations` / manager
24. **garak_probe** "garak LLM 보안 스캐너 실행..." / `probe`(req),`model` / manager / danger
25. **model_isolate** "Ollama 모델 격리 — 의심 모델 unload + 외부 호출 차단" / `model`(req) / manager / danger-danger / **requires_approval**
26. **rag_corpus_check** "RAG 인덱스 무결성 검증 — 문서 hash 비교..." / `corpus_path`(req),`baseline_hash_file` / manager
27. **cve_lookup** "CVE 조회 — 로컬 NVD 캐시 또는 CISA-KEV..." / `cve`(req) / local
28. **password_attack** "패스워드 공격 도구 wrapper — hydra/medusa/john" / `tool`(req,enum=[hydra,medusa,john]),`target`(req),`service,userlist,passlist` / attacker / danger-danger / **requires_approval**
29. **dns_recon** "DNS 정찰 — dig + sublist3r/amass..." / `domain`(req),`deep` / attacker
30. **compliance_scan** "OS 컴플라이언스 스캔 — lynis/OpenSCAP CIS·STIG" / `target`(req),`profile` / auto
31. **secret_scan** "코드/설정 파일에서 자격증명 노출 탐지 — gitleaks/trufflehog(없으면 grep)" / `target`(req),`path` / auto
32. **history_anchor** "압축 면역 anchor 등록 — IoC/규제/정책결정/침해기록..." / `kind`(req,enum=[ioc,regulatory,policy_decision,breach_record]),`label`(req),`body`(req),`related_ids` / local
33. **history_narrative** "장기 narrative 생성·종료..." / `action`(req,enum=[open,close]),`narrative_id,title,summary,tags` / local

### 6.3 헬퍼 + `execute_skill`
- `skills_to_ollama_tools()` → Ollama tools 포맷(`{type:function,function:{name,description,parameters:{type:object,properties,required}}}`).
- `_shq(s)` 싱글쿼트 wrap, `_resolve_vm_ip(target, vm_ips)`, `preview_skill(name, params, vm_ips)`(dry-run cmd_preview + risk HIGH/MEDIUM/LOW).
- `execute_skill(name, params, vm_ips, ollama_url="", model="") -> dict` — name 디스패치. Unknown→`{success:False,error}`. **하드코딩 보존 필수**:
  - `scan_ports/check_suricata/check_wazuh/check_modsecurity`는 레지스트리 target_vm과 무관하게 **bastion 호스트에서 `docker exec el34-<name>`** 로 실행(컨테이너명: el34-attacker, el34-ips, el34-siem, el34-web).
  - **shell**: `_bastion_patterns`(docker 서브커맨드/df/du/free/uptime/ip route/curl localhost:9100/ssh el34-*/for h in fw 등) 매칭 시 target=bastion으로 강제. R3 fix: target=attacker일 때 `10.20.30.80→192.168.0.108`, `http://10.20.30.100→http://192.168.0.108` 치환. curl 재시도: exit0 & curl & `-i/-I` 없음 & stdout<60자 → `curl -i -L` 재실행.
  - Wazuh API 자격: `wazuh-wui:wazuh-wui` @ `https://localhost:55000`. wazuh-agent 핀: `wazuh-agent=4.10.3-1`. 기본 fuzz/probe 모델 `ccc-vulnerable:4b`, ollama_query 기본 `gpt-oss:120b`, prompt_fuzz 기본 ollama `http://192.168.0.109:11434`.
  - 각 skill의 정확한 bash 스크립트는 위 카테고리별 동작을 따른다(probe_host: uptime/CPU/disk/mem/failed services; deploy_rule: base64 + sid dedup + HUP/restart; attack_simulate: sqli/xss/brute_ssh hydra/brute_http/dir_scan dirb/port_scan nmap; ioc_export: STIX 2.1 bundle; history_anchor: HistoryLayer.add_anchor; 등).

---

## 7. `bastion/playbook.py` — YAML Playbook 엔진 (schema v2)

`PLAYBOOK_SCHEMA_VERSION=2`. 필드: `playbook_id`(pb-...), `name`/`title`, `description`, `version`(1), `schema_version`(2), `risk_level`(low/med/high), `reasoning`(task_decomposition/considered_alternatives[{tool,rejected_reason}]/why_this_approach/assumptions/known_risks), `plan`(우선) 또는 `steps`(v1 fallback, normalize가 plan으로 복사), step 필드(`step,intent,thinking,success_signal,on_error,skill,params,name,on_failure,requires_approval`), `exec_history`(total/success/recent_5), `known_pitfalls`, `related_concepts`(MITRE).

함수: `_slugify`, `normalize_playbook`, `validate_playbook`(경고만), `write_playbook`(yaml.safe_dump allow_unicode sort_keys=False, 존재 시 version+1+supersedes_version), `update_exec_history`(recent_5 슬라이딩), `_resolve_playbooks_dir`(env `BASTION_PLAYBOOKS_DIR` → `../../contents/playbooks` → `../contents/playbooks`), `load_playbook`, `list_playbooks`.

`run_playbook(playbook_id, vm_ips, params=None, ollama_url="", model="", approval_callback=None) -> Generator`:
> **재구축 주의**: `steps = pb.get("steps", [])` 로 **raw steps** 키를 순회(normalized plan 아님). 출하된 8개 YAML 모두 `steps:` 사용. 이벤트: `playbook_start{playbook_id,title,total_steps}` → step별 `step_start` → (requires_approval 시 approval_callback, 거부 `step_skip`) → `execute_skill` → `step_done{step,name,success,output[:500]}` → on_failure=="abort" 시 `playbook_abort` → `playbook_done{playbook_id,passed,total,evidence_count}`. param 템플릿 `{key}` 치환.

### 8개 정적 Playbook (`contents/playbooks/*.yaml`, 모두 v1 steps 스키마)
- **attack_simulation** "공격 시뮬레이션 — Red Team 기본 공격 체인": scan_ports{target:10.20.30.80} → web_scan{url:http://10.20.30.80} → attack_simulate{sqli,...:3000/rest/user/login} → attack_simulate{xss,...:3000} → check_suricata
- **hardening** "시스템 경화 체크리스트": probe_host{secu} → configure_nftables{list} → check_suricata → probe_host{web} → check_modsecurity → check_wazuh
- **incident_response** "인시던트 대응 절차"(all on_failure:continue): check_wazuh → check_suricata{lines:20} → check_modsecurity{lines:15} → configure_nftables{add, rule:"ip saddr {suspect_ip} drop", **requires_approval:true**} → analyze_logs{eve.json, secu}
- **log_investigation** "로그 조사": check_suricata{20} → check_wazuh → check_modsecurity → analyze_logs{eve.json,secu} → analyze_logs{alerts.json,siem}
- **probe_all** "전체 인프라 상태 점검": probe_all → check_suricata → check_wazuh → check_modsecurity → configure_nftables{list}
- **security_audit** "보안 감사": configure_nftables{list} → check_suricata → check_modsecurity → check_wazuh → probe_all
- **vuln_scan** "취약점 스캔": scan_ports{web,-p 22,80,443,3000,8080} → scan_ports{secu,-p 22,80,8002} → web_scan{:3000} → web_scan{:8080}
- **wazuh_health** "Wazuh 종합 점검": check_wazuh → wazuh_api{/agents} → file_manage{read,local_rules.xml,siem} → analyze_logs{alerts.json,siem}

---

## 8. `bastion/prompt.py` — 프롬프트 빌더

`build_planning_prompt(vm_ips=None, rag_context="", prev_context="", learned_context="")`: 섹션 join("\n\n"). 핵심 섹션 1(대형 f-string): 정체성 → `## 분류 원칙 — 실행 vs 답변`(실행 트리거 동사 `확인/설정/스캔/시도/추가/삭제/조회/공격/삽입/우회/추출/전송/생성/점검`, 답변=정의/원리/이론) → `## 사용 가능한 Skill`(SKILLS map) → `## VM 추론`(키워드→VM) → `## ★ el34 컨테이너 인프라 컨텍스트` R1~R7(R1 ssh el34-bastion→manager self, R2 ssh el34-X→매핑, R3 docker exec 유지, R4 학생PC 가정 무시, R5 ssh el34-bastion 금지, R6 shell skill 우선+lab 타겟 auto-approve, R7 stdout verbatim 인용) → `## 현재 인프라 상세`(vm_ips 있을 때) → prev/learned/rag context append.

`build_system_prompt(vm_ips=None, student_info=None, extra_context="")`: 정체성("CCC Bastion 보안 운영 에이전트... 한국어 간결") → Skill 목록 → 등록 Playbook → 현재 인프라 → 사용자 정보 → **CCC.md 첫 2000자**(`[운영 지침]`) → extra_context.

---

## 9. `bastion/rag.py` — 교육콘텐츠 RAG (인메모리)

`KNOWLEDGE_DIR=<pkg>/../knowledge`(agent는 `<repo>/../contents` 전달). 클래스 `RAGIndex`: `chunks`, `inverted`. `add_chunk`(보안용어 정규식 + 일반 한/영 토큰 추출), `search(query, top_k=3)`(BM25-like: `idf=log((N-df+0.5)/(df+0.5)+1)`, tf=1.0), `stats()`. `build_index`는 4종 인덱싱: lectures(`education/*/*/lecture.md` `## ` 분할), labs(`labs/*/*.yaml` 1청크), manuals(`manuals/*.md`), playbooks(`../contents/playbooks/*.yaml`). `format_context(chunks, max_chars=3000)` → `[관련 교육 자료]` + `--- {source} | {title} ---\n{content[:800]}`.

---

## 10. `bastion/experience.py` — Experience Learning Layer

오버피팅 방지 5전략: 카테고리 일반화, 최소증거, 성공률 게이팅, 부정경험 경고, 용량캡+LRU+시간감쇠.

`CATEGORY_RULES`: 19개 `(re.compile(...,re.I), category)` 순서 매칭(system_auth, network_scan, web_request, web_vuln_scan, credential_attack, ids_ops, siem_ops, firewall_ops, container_ops, audit_ops, ssh_ops, log_ops, ai_ops, tls_ops, waf_ops, backup_ops, schedule_ops, privesc, reporting). 무매칭→"general".

`ExperienceLearner` 상수: `MIN_EVIDENCE=3, SUCCESS_THRESHOLD=0.7, MAX_EXPERIENCES=100, DECAY_DAYS=30, PROMOTE_TO_PLAYBOOK_THRESHOLD=5, PROMOTE_SUCCESS_RATE=0.8`. EvidenceDB 공유. DDL `experience`(id,created_at,updated_at,last_used,pattern_key UNIQUE,category,skill,target_vm,command_template,success_count,fail_count,total_count,keywords '[]',examples '[]',outcome '').

메서드: `classify`, `extract_keywords`(한2+/영문3+ -stopwords), `_make_pattern_key(f"{cat}:{vm}:{skill}")`, `_generalize_command`(IP→{IP}, /tmp/X→{TMPFILE}, 200자), `record(message,skill,target_vm,command,success)`, `lookup(message,top_k=5)`(점수=success_rate×freq×decay), `_decay_weight`(max(0.1,1-(days/30)*0.5)), `get_context(message)`(승격/부정 경험만 `[학습된 경험]`), `enforce_capacity`(>100 시 LRU 삭제), `promote_to_playbook`(5회+80%→`exp-{key}.yaml` 생성), `stats`.

---

## 11. `bastion/audit.py` — append-only SHA-256 해시체인 감사

경로: arg → `BASTION_AUDIT_DB` → `../../data/bastion_audit.db`/`../data/...` → `/tmp/bastion_audit.db`(별도 파일).

DDL `audit`(id, request_id UNIQUE, session_id, user_id, source_ip, ts_start, ts_end, duration_ms, user_prompt, final_answer, approval_mode, course, lab_id, step_order, verify_intent, lookup_json, turns_json, skill_calls_json, judge_json, outcome, model_used, bastion_version, test_meta_json, prev_hash, self_hash, created_at) + 인덱스(session/user/ts/outcome).

`AuditLog`: `_canonical`(json.dumps ensure_ascii=False sort_keys=True separators(",",":")), `append(...)`(payload에 prev_hash 포함, `self_hash=sha256(canonical)`; **duration_ms는 해시 제외**), SIEM forward(logger `bastion-audit`, SysLogHandler LOCAL5 UDP `SIEM_HOST:514` + FileHandler `/var/log/bastion-audit.log`, JSON 1줄), `recent(filters)`, `get`, `verify_chain(start_id=1)`(불일치 시 stop, `{verified,broken,ok}`), `stats`. 싱글톤 `get_audit_log`.

---

## 12. `bastion/history.py` — PE-KG-H L4 History (KG SQLite 공유)

4 테이블(KG DB와 동일 파일, 별도 테이블): `history_events`(id,ts,kind,actor,asset_id,narrative_id,audit_seq,summary,payload), `history_narratives`(id,title,started_at,ended_at,status 'open',summary,tags,meta), `history_anchors`(id,kind,label,body,related_ids,created_at,valid_from,valid_until,immune 1), `history_changelogs`(id,target_kind,target_id,version,ts,actor,diff,rationale,audit_seq, UNIQUE(target_kind,target_id,version)).

`HistoryLayer`: `add_event(kind,summary,*,actor,asset_id,narrative_id,audit_seq,payload,ts)`(`evt-{hex12}`), `list_events`, `open_narrative`(`nar-{hex12}`)/`close_narrative`/`get_narrative`, `add_anchor(kind,label,body,*,related_ids,valid_from,valid_until)`(`anc-{hex12}` immune=1), `find_anchors(*,kind,label_like,limit)`, `is_anchored(label_or_body)`(`label=? OR body LIKE %?%`), `add_changelog`(version=MAX+1), `changelog`, `handoff(asset_id,since)`, `range_query`, `match_repeat_iocs(observed)`. 모듈 함수 `is_compaction_immune(history,experience_id,summary_text)`(anchored 또는 narrative-bound).

---

## 13. KG 서브시스템

### 13.1 `bastion/graph.py` — KnowledgeGraph (SQLite + FTS5)
`NODE_TYPES`(set): Playbook,Experience,Skill,Error,Recovery,Concept,Insight,Narrative,Anchor,Asset,Mission,Vision,Goal,Strategy,KPI,Plan,Todo. `EDGE_TYPES`(set): uses,handles,targets,supersedes,depends_on,often_chains,derived_from,encountered,recovered_by,applied_in,parent_of,abstracts,reuse,adapt,generalize,refute,precedes,follows,belongs_to,relates_to,connects_to,data_flows_to,hosts,manages,trusts,monitors,realizes,measures,contributes_to,blocks,owned_by,scheduled_for,derives_from.

`_resolve_db_path`: arg → `BASTION_GRAPH_DB` → 후보(`../../data/bastion_graph.db`, `../../../data/...`, `../data/...`, `/home/ccc/ccc/data/bastion_graph.db`) 중 **존재하는 것 중 가장 큰 파일**(DB 분기 방지) → 첫 쓰기가능 후보 → `/tmp/bastion_graph.db`.

DDL `SCHEMA`:
```sql
CREATE TABLE nodes(id TEXT PRIMARY KEY, type TEXT NOT NULL, name TEXT NOT NULL,
  content TEXT DEFAULT '{}', embedding BLOB, meta TEXT DEFAULT '{}',
  created_at TEXT DEFAULT (datetime('now')), updated_at TEXT DEFAULT (datetime('now')));
CREATE INDEX idx_nodes_type/idx_nodes_name;
CREATE TABLE edges(id INTEGER PRIMARY KEY AUTOINCREMENT, src TEXT, dst TEXT, type TEXT,
  weight REAL DEFAULT 1.0, meta TEXT DEFAULT '{}', created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(src,dst,type));
CREATE INDEX idx_edges_src/dst/type;
CREATE VIRTUAL TABLE nodes_fts USING fts5(id UNINDEXED, type UNINDEXED, name, content_text,
  tokenize='unicode61 remove_diacritics 1');
```
`_conn`: timeout=15, WAL, busy_timeout=15000, foreign_keys ON. 메서드: `add_node`(type 검증, UPSERT content/meta/embedding/updated_at, FTS 재삽입; **type/created_at은 conflict 시 미갱신**), `get_node`, `find_nodes`, `all_nodes`, `delete_node`(노드+FTS+엣지 캐스케이드), `add_edge`(UPSERT weight **누적**), `all_edges`, `neighbors(node_id,edge_type,direction)`, `backlinks`, `traverse(start,max_depth=2,edge_types)`(BFS), `search_fts(query,type,limit=20)`(쿼리를 `"..."` phrase로 wrap, `bm25` 정렬), `stats`, `_extract_fts_text`(name+description/intent/task_summary/notes+reasoning+plan). 싱글톤 `get_graph(db_path="")`.
> 알려진 불일치(보존): kg_context가 `"Policy"` 타입 질의(NODE_TYPES에 없음→항상 빈 결과); `search_fts` phrase wrap으로 lookup의 `" OR "` 조인이 phrase로 동작; edges에 실제 FK 없음.

### 13.2 `bastion/graph_migrate.py` — 1회성 마이그레이션
`VM_ROLES`(attacker 10.20.30.201, secu 10.20.30.1, web 10.20.30.80, siem 10.20.30.100, manager 10.20.30.200). `migrate_skills`(`skill-{name}`), `migrate_assets`(`asset-vm-{role}`), `migrate_concepts`(`concept-{cat}`), `migrate_playbooks`(`pb-{id}` + uses/targets/handles 엣지), `migrate_experience_db`(legacy), `migrate_all() -> 카운트 dict`. `__main__` JSON 출력.

### 13.3 `bastion/kg_context.py` — 컨텍스트 빌더
`_TOKEN_BUDGETS`: gemma{total:1500,anchor:600,concept:400,policy:300,playbook:200,asset:200}, gpt-oss{total:4000,anchor:1500,concept:1000,policy:800,playbook:700,asset:500}, default{=gemma}. `KGContextBuilder`(_CACHE_TTL_SEC=300, _CACHE_MAX=256): `build(message,*,model,token_budget,eg_mode="full")` — 캐시키 `sha1(message+"|eg="+mode)[:16]`, tier별 `search_fts(message,type,limit=3)`(Concept/Policy/Playbook/Asset), `find_anchors(label_like=message[:60],limit=5)`(fallback 키워드), **F10 관련성 필터**(메시지 키워드 무교집합 앵커 제거), eg ablation tier 필터(playbook→앵커 제거, experience→playbook 제거), `_apply_budget`, **빈 결과는 캐시 안 함**. `format(result,*,char_budget=1500)` → `# KG 컨텍스트 (사전 참조...)` + tier별 `## {header} ({n}건)` 불릿. 싱글톤 `get_builder`.

### 13.4 `bastion/kg_recorder.py` — 앵커 레코더
`SCHEMA_VERSION=1`. kinds: task_outcome, observation, finding, asset_state, playbook_exec. `extract_mitre_ids`(`\bT\d{4}(?:\.\d{3})?\b`), `_semantic_hash`. `KGRecorder`: `record_task_outcome/observation/finding/asset_state/playbook_exec` → `_record(kind,label,body_doc,dedup_key,related_ids)`(is_anchored 중복 시 `kg_record_dedup`, 아니면 add_anchor+`kg_record_total`). 싱글톤 `get_recorder`.

### 13.5 `bastion/kg_metrics.py` — 인메모리 메트릭
`KGMetrics`(threading.Lock, counters defaultdict, observations max 1000): `inc/observe/snapshot(p50/p95/max/avg)/reset`. 싱글톤 `get_metrics`. 메트릭명: kg_context_cache_hit, kg_context_search, kg_context_search_took_ms, kg_record_dedup/total/error, kg_context_skip, kg_record_skip.

### 13.6 `bastion/lookup.py` — KG-4 결정 엔진
임계값: `THRESH_REUSE=0.92, THRESH_NEW=0.70, THRESH_SUCCESS_RATE=0.80, DESTRUCTIVE_CATEGORIES={exploit,privesc,credential_attack,deploy_rule}`. `_tokens/_jaccard/_coverage/_success_rate`. `collect_candidates(message,top_k=3)`(FTS + 전체 playbook, sim*0.6+cov*0.3+sr*0.1 정렬), `hard_decision`(sim≥0.92&sr≥0.80&cov≥0.85&exec≥2&비파괴→reuse; sim<0.70→new; sr<0.5&exec≥5→adapt; 아니면 None), `llm_verifier`(format:json temp 0.0 num_predict 600 timeout 30 → reuse/adapt/new), `decide`, `build_lookup_prompt`(reuse/adapt 시 `[lookup]...` 시스템 프롬프트 주입, new→"").

### 13.7 `bastion/compaction.py` — KG-5 경험 압축
`MIN_EXPERIENCES=5, MIN_FAIL_RECURRENCE=2, NOISE_AGE_DAYS=1`. `compact_playbook(playbook_id,...)`(derived_from 경험 ≥5 수집 → LLM JSON `{pitfalls,recovery_patterns,insights,drop_ids,summary}` temp 0.0 num_predict 2000 → Insight 노드(abstracts)/Error+Recovery(recovered_by)/known_pitfalls 병합(cap15)/noise deprecated(**삭제 안 함**, History 면역 게이트)). `compact_all`. CLI `python -m bastion.compaction [id|all]`.

### 13.8 `bastion/work_domain.py` / `bastion/asset_domain.py`
work: STRATEGIC(Mission/Vision/Goal/Strategy/KPI)+TACTICAL(Plan/Todo), `add_mission/vision/goal/strategy/kpi/plan/todo`, `record_kpi`(history 200), `update_status`, `trace_to_mission`, `strategic_dashboard`. asset: ASSET_KINDS(host/application/model/data_store/...), ARCH_EDGES(connects_to/depends_on/data_flows_to/hosts/manages/trusts/monitors), `register_asset`(id 예 `asset:host:web`)/`list_assets`/`link_assets`/`architecture_topology`/`architecture_packet_flow`/`autoscan_register`.

### 13.9 `bastion/verify.py` / `bastion/lab_verify.py`
verify: 역할별 인프라 체크(`_check` modes: contains/not_empty/gt_zero/exit_zero/http_ok), `verify_role`/`verify_all_stream`(SSE), 네트워크 E2E(attacker→web SQLi→403, suricata eve, modsec block). lab_verify: `verify_lab_step`(python3 heredoc 변환, LLM_URL env 치환, verify type output_contains/output_regex/exit_code), `verify_lab_stream`/`verify_all_labs_stream`.

---

## 14. `api.py` — Bastion 헤드리스 제어평면 API (FastAPI:8003)

`app=FastAPI(title="Bastion API", version="1.0.0")`. `__main__`: `uvicorn.run("apps.bastion.api:app", host="0.0.0.0", port=int(BASTION_API_PORT or 8003))`. 싱글톤 `agent=BastionAgent(...)`, `_model_swap_lock=threading.Lock()`. **인증/CORS 없음**(0.0.0.0 전개방).

라이프사이클: `_emit_bastion_syslog`(logger `bastion-lifecycle`, SysLogHandler LOCAL5 UDP `SIEM_HOST:514` + FileHandler `/var/log/bastion-lifecycle.log`, request_id 상관). startup hooks: `_startup_kg_banner`(kg_context/recorder/metrics/graph/history 프로빙 → ENABLED/DEGRADED stderr), 자산 자동등록(.env VM_*_IP → `update_asset`). 과정별 모델 라우팅 `_resolve_manager_model`: `ATTACK_COURSES`(attack-ai, attack-adv-ai, battle-ai, battle-adv-ai, web-vuln-ai, physical-pentest-ai, ai-security-ai, agent-ir-ai, agent-ir-adv-ai, autonomous-ai, autonomous-systems-ai, ai-safety-adv-ai) → `LLM_MANAGER_MODEL_UNSAFE`(LLM_FAST_ATTACK 시 일반).

데이터 모델(pydantic): ChatRequest(message, auto_approve=False, stream=True, approval_mode="normal", course="", lab_id="", step_order=0, test_session="", verify_intent="", verify_success_criteria=[], verify_acceptable_methods=[], verify_negative_signs=[], eg_mode="full"), AskRequest, OnboardRequest, AssetUpdateBody, AssetRegisterBody, AssetLinkBody, NarrativeOpenBody, AnchorBody, ConceptBody, IocCheckBody, ChangelogBody, Work 도메인 바디들.

### 엔드포인트 (전부 무인증)
- **Core/health**: `GET /health`, `GET /kg/health`, `GET /kg/audit?limit=20`, `GET /skills`, `GET /playbooks`, `GET /evidence?limit=20`.
- **Chat**: `POST /chat`(ChatRequest, stream 시 NDJSON `application/x-ndjson` 라인당 이벤트, 아니면 `{events:[...]}`; 과정별 모델 스왑, 라이프사이클 syslog), `POST /ask`(AskRequest 비스트리밍 → `{answer,success,skill_outputs,event_count}`).
- **Onboard**: `POST /onboard`(NDJSON, no timeout, `onboard_vm` 호출).
- **Audit**: `GET /audit?limit=50&...filters`, `GET /audit/{request_id}`(404), `GET /audit/_stats`, `GET /audit/_verify-chain?start_id=1`.
- **KG**: `POST /graph/compact/{playbook_id}`, `POST /graph/compact`, `GET /graph/stats`, `GET /graph/nodes?types=&limit=500`, `GET /graph/edges`, `GET /graph/node/{id}`, `GET /graph/search?q=&type=&limit=30`, `GET /graph/lineage/{id}?max_depth=3`, `DELETE /graph/node/{id}`, `GET /kg/metrics`, `GET /kg/anchors/recent`.
- **History**: `GET /history/handoff/{asset_id}`, `/history/range`, `/history/events`, `GET/POST /history/narratives[/{id}/close]`, `GET/POST /history/anchors`, `POST /history/repeat-iocs`, `POST /history/changelog`, `GET /history/changelog/{kind}/{id}`, `GET /history/graph-view`, `GET /history/asset-timeline/{id}`.
- **Knowledge**: `POST /knowledge/concept`.
- **Asset**: `POST /assets/register`, `GET /assets/list`, `POST /assets/link`, `GET /assets`, `PUT /assets/{role}`.
- **Architecture**: `GET /architecture/topology?root=&max_depth=3`, `GET /architecture/flow?src=&dst=`.
- **Work**: `POST /work/{mission|vision|goal|strategy|kpi|kpi/record|plan|todo|status}`, `GET /work/trace/{id}`, `GET /work/dashboard`.
- **Ollama 프록시**(모델을 agent.model로 강제): `POST /api/generate`, `POST /api/chat`, `GET /api/tags`, `GET /api/version`.

---

## 15. `main.py` — Rich TUI

한글 IME 인코딩 근본수정: `builtins.input`을 `_safe_input`(stdin.buffer 직접 읽기 errors='ignore')으로 패치. `.env` 수동 로드. `get_vm_ips()`(env → PostgreSQL student_infras → INTERNAL_IPS). ASCII `BANNER`. CLI 플래그 `--danger-danger-danger`(yolo)/`--danger-danger`. `BastionAgent` 생성 후 배너/인프라테이블/Panel 출력. 내장 명령: `/skills /playbooks /evidence /assets /search <kw> /stats /clear /quit`. `approval_callback`(Y/n). 메인 루프: `agent.chat()` 이벤트를 Rich로 렌더(stage/stream_token/skill_start/skill_result/risk_warning/plan_preview/playbook 이벤트, planning 중 spinner).

---

## 16. 인프라 스크립트

### `setup.sh`(set -euo pipefail)
cd repo → INSTALL_DIR → `python3 -m venv .venv` → activate → `pip install -r requirements.txt -q` → hostname `bastion` → `.env` 부트스트랩(cp .env.example) → systemd: `sed "s|/opt/bastion|${INSTALL_DIR}|g" bastion-api.service | sudo tee /etc/systemd/system/bastion-api.service` → daemon-reload/enable/restart → "http://localhost:8003".

### `bastion.sh`
cd → venv 보장 → activate → `pip install -r requirements.txt -q` → `.env` source → `PYTHONPATH=$(pwd)` → `python3 main.py`.

### `upgrade.sh`(5단계)
[1] OLD_REV → [2] `git stash --include-untracked` + `git pull --ff-only origin main` + stash pop → [3] `.venv/bin/pip install -r requirements.txt -q` → [4] systemd restart 또는 nohup fallback(`uvicorn api:app --host 0.0.0.0 --port 8003`) → [5] `curl http://localhost:8003/health`. 로그 `/tmp/bastion_api.log`, `/tmp/bastion_health.json`.

### `sync_knowledge.sh`(CCC 서버에서 실행)
`bash sync_knowledge.sh <bastion_ip=10.20.30.200> <ssh_user=ccc> <ssh_password=1>`. tar(`contents/education/ contents/labs/*-nonai/`) → sshpass scp → remote 추출 → `/opt/bastion/knowledge`.

### `requirements.txt`
```
fastapi>=0.115
uvicorn>=0.34
httpx>=0.28
pyyaml>=6.0
pydantic>=2.0
paramiko>=3.0
```

### `bastion-api.service`
```ini
[Unit]
Description=Bastion Headless API Server
After=network.target
[Service]
Type=simple
WorkingDirectory=/opt/bastion
EnvironmentFile=-/opt/bastion/.env
ExecStart=/opt/bastion/.venv/bin/uvicorn api:app --host 0.0.0.0 --port 8003
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
[Install]
WantedBy=multi-user.target
```

### `.gitignore`
```
.venv/
__pycache__/
*.pyc
.env
```

---

## 17. 데이터 저장소 / 포트 / 경로 요약

- **SQLite 3종**: (a) `bastion_audit.db`(감사, env `BASTION_AUDIT_DB`, 별도) (b) `bastion_graph.db`(KG + History L4 테이블, env `BASTION_GRAPH_DB`) (c) EvidenceDB(experience 공유, `:memory:` 가능). RAG는 순수 인메모리.
- **포트**: Bastion API 8003, SubAgent 8002, Ollama 11434(외부), syslog 514/udp LOCAL5.
- **systemd**: `bastion-api.service`(manager), `ccc-subagent.service`(VM별).
- **경로**: 설치 `/opt/bastion`(venv `.venv/`), 지식 동기화 `/opt/bastion/knowledge`, SubAgent `/opt/ccc-subagent/agent.py`, 로그 `/var/log/bastion-lifecycle.log`/`/var/log/bastion-audit.log`/`/tmp/bastion_api.log`/`/tmp/bastion_health.json`.
- **필수 env**(미설정 시 hard-fail): `LLM_BASE_URL, LLM_MANAGER_MODEL, LLM_SUBAGENT_MODEL`.

---

## 18. 보안 / 운영 주의 (의도적으로 보존 또는 의도적으로 하드닝)

- API는 인증/CORS 없이 0.0.0.0:8003 바인딩; SubAgent는 `shell=True`로 임의 셸 실행; 온보딩 기본 SSH `ccc`/`1` + `StrictHostKeyChecking=no` + sshpass.
- 파괴적 작업(`rm -rf /`, DROP TABLE 등) 금지; 학생 데이터 임의 삭제 금지; 서비스 중지/재시작 시 사용자 확인; 배포 전 git status 확인.
- compaction은 경험을 **삭제하지 않고** `meta.deprecated`만 설정; History 앵커/내러티브로 면역.
- 감사 `_canonical`은 append/verify 간 바이트 동일해야 함(`duration_ms` 해시 제외).

---

## 19. 재구축 시 반드시 보존할 "load-bearing" 디테일 체크리스트

1. `skills.py` 상단 `import time, json` 추가(미존재 시 ioc_export/memory_dump/prompt_fuzz NameError).
2. `scan_ports/check_suricata/check_wazuh/check_modsecurity`는 레지스트리 target_vm 무시하고 bastion 호스트 `docker exec el34-<name>`.
3. `shell` skill의 `_bastion_patterns` 라우팅 + R3 IP 치환(10.20.30.80→192.168.0.108) + curl `-i -L` 자동 재시도.
4. `run_playbook`은 normalized plan이 아닌 `pb.get("steps")` 순회.
5. ReAct는 live path; 구 4-stage fallback(`_chat_once` line 968+)은 dead code(보존, 비활성).
6. ReAct는 httpx.post 직접 호출이므로 `_inject_kg_context(msgs)`를 명시 호출(KG 6턴 유지).
7. cycle2 "4축 분석 형식" + "빈 필드 시 3가지 대안"은 코드 분기가 아니라 `_build_react_system_prompt()` 텍스트.
8. eg_mode `off`는 진짜 No-KG: experience/정적playbook/KG주입/lookup/그래프영속화 모두 게이팅.
9. KG `_resolve_db_path`는 존재하는 후보 중 **가장 큰 파일** 선택(DB 분기 방지).
10. graph `add_edge` weight 누적, `add_node` UPSERT 시 type/created_at 미갱신.
11. 하드코딩 자격/엔드포인트: Wazuh `wazuh-wui:wazuh-wui`@`https://localhost:55000`, fuzz/probe 모델 `ccc-vulnerable:4b`, prompt_fuzz ollama `http://192.168.0.109:11434`, wazuh-agent `4.10.3-1`.
12. approval_mode 3단계: normal(high/critical 묻기) / danger_danger(critical만) / danger_danger_danger(yolo).

---

## 20. 빌드/실행 순서 (재구축 검증)

```bash
git clone https://github.com/mrgrit/bastion.git /opt/bastion
cd /opt/bastion
bash setup.sh                 # venv + pip + systemd(bastion-api :8003)
vi .env                       # LLM_BASE_URL / LLM_MANAGER_MODEL / LLM_SUBAGENT_MODEL / VM_*_IP
./bastion.sh                  # Rich TUI
# 또는 API: systemctl status bastion-api && curl http://localhost:8003/health
python -m bastion.graph_migrate   # KG 초기 시드(선택)
```

> 본 문서 기준: 2026-06-03, HEAD `c0a07b3`. 테스트 실증(`bastion-test-report.md`): 2,570 케이스, 정형 도구 실행 25~45% 성공, Experience Layer 반복 시 +7%, 컨텍스트 수준 최적화(모델 재학습 없음).
