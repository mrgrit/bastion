# 작업 진행 기록 (2026-04-01)

## 완료된 단계

### 1단계: prompt_engine (✅ 완료)
- OpsClaw 경로: `packages/prompt_engine/`
- 파일 9개: `__init__.py`, `compose.py`, `sections/{identity,safety,workflow,tools,environment,experience,output}.py`
- `pi_adapter/runtime/client.py`에 통합: `_role_system_prompt()` → `compose()` 호출
- 기존 3줄 고정 프롬프트 → 7개 섹션 동적 조합 (~7,800자)
- 검증: compose("manager"), compose("master", {"server": "secu"}), compose("tutor") 모두 통과

### 2단계: 프롬프트 엔지니어링 (✅ 완료)
- 6개 패턴이 prompt_engine 섹션에 반영됨
  - A: 섹션 분리 (Identity/Safety/Workflow/Tools/Environment/Output)
  - B: "하지 마라" → "이렇게 하라" 변환
  - C: 도구별 사용 가이드 (dispatch/execute-plan/playbook 선택 기준)
  - D: 출력 효율성 (completion-report 형식)
  - E: 안전 행동 구체적 예시 (risk_level별 명령 목록)
  - F: JSON 출력 강제 시 3-4개 예시 포함 (mission/explore/daemon)

### 3단계: hook_engine (✅ 완료)
- OpsClaw 경로: `packages/hook_engine/`
- 파일 5개: `__init__.py`, `events.py`, `models.py`, `registry.py`, `executor.py`
- 10개 이벤트: project_created, stage_changed, pre/post_dispatch, pre/post_playbook_step, evidence_recorded, incident_created, mission_step, daemon_alert
- 3가지 Hook 유형: webhook (HTTP POST), script (로컬 실행), notification (기존 알림)
- pre_dispatch, pre_playbook_step에서 실행 차단(block) 가능
- 조건부 실행: Python expression (예: `risk_level == 'critical'`)
- DB 테이블 `hooks` 자동 생성

### 4단계: tool_validator (✅ 완료)
- OpsClaw 경로: `packages/tool_validator/`
- 파일 4개: `__init__.py`, `schema.py`, `validator.py`
- 기존 `schemas/registry/tools/*.json` (6개 도구) 로드하여 런타임 검증
- 입력 검증: required 필드, 타입, min/max
- 도구 안전 분류: is_read_only, is_destructive, default_risk_level
- evidence 정규화: body_ref→command, stdout_ref→stdout 통일 함수

### 5단계: cost_tracker (✅ 완료)
- OpsClaw 경로: `packages/cost_tracker/`
- 파일 3개: `__init__.py`, `tracker.py`
- DB 테이블 `llm_usage` 자동 생성
- 프로젝트별/에이전트별/전체 사용량 조회
- 예산 체크: max_tokens, max_calls 한도 강제
- `pi_adapter/runtime/client.py`에 통합: 매 LLM 호출 시 자동 추적

### 6단계: permission_engine (✅ 완료)
- OpsClaw 경로: `packages/permission_engine/`
- 파일 3개: `__init__.py`, `decision.py`
- 기존 rbac_service + policy_engine + approval_engine 위에 통합 결정 레이어
- 5단계 체크: API Key → RBAC → Policy → Approval → Risk Auto
- 읽기전용 도구 즉시 허용 (tool_validator 연동)
- Denial tracking: 연속 거부 3회 → 자동 에스컬레이션
- 검증: read_file(critical)=allow, run_command(critical)=ask, prod+high=ask

### 7단계: memory_manager (✅ 완료)
- OpsClaw 경로: `packages/memory_manager/`
- 파일 5개: `__init__.py`, `types.py`, `extractor.py`, `capacity.py`
- 메모리 유형 5종: incident, runbook, failure, configuration, optimization
- "저장하지 않을 것" 규칙 (DO_NOT_SAVE 목록)
- 자동 추출: 프로젝트 완료 시 evidence/report에서 패턴 감지
  - exit_code!=0 → failure 메모리
  - systemctl/restart 등 → configuration 메모리
  - 전체 성공 → runbook 메모리
  - incident 키워드 → incident 메모리
- LRU 용량 관리: task_memories(200), experiences(100), local_knowledge(30)

## OpsClaw 변경 파일 전체 목록

### 신규 생성
```
packages/prompt_engine/__init__.py
packages/prompt_engine/compose.py
packages/prompt_engine/sections/__init__.py
packages/prompt_engine/sections/identity.py
packages/prompt_engine/sections/safety.py
packages/prompt_engine/sections/workflow.py
packages/prompt_engine/sections/tools.py
packages/prompt_engine/sections/environment.py
packages/prompt_engine/sections/experience.py
packages/prompt_engine/sections/output.py
packages/hook_engine/__init__.py
packages/hook_engine/events.py
packages/hook_engine/models.py
packages/hook_engine/registry.py
packages/hook_engine/executor.py
packages/tool_validator/__init__.py
packages/tool_validator/schema.py
packages/tool_validator/validator.py
packages/cost_tracker/__init__.py
packages/cost_tracker/tracker.py
packages/permission_engine/__init__.py
packages/permission_engine/decision.py
packages/memory_manager/__init__.py
packages/memory_manager/types.py
packages/memory_manager/extractor.py
packages/memory_manager/capacity.py
```

### 수정
```
packages/pi_adapter/runtime/client.py  (prompt_engine + cost_tracker 통합)
CLAUDE.md                              (Bastion 개선 패치 전체 문서)
```
