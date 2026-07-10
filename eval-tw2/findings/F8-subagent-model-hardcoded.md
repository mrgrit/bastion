# F8 — 서브에이전트 일부 경로가 gemma3:4b 하드코딩 (qwen3.5:9b 미적용)

- 발견: gemma4:31b 조사 중 코드 확인 (2026-07-10)
- 심각도: **중** ("qwen3.5:9b 로 테스트" 전제의 부분 위배)
- 상태: OPEN — 수정 대상

## 증상
`LLM_SUBAGENT_MODEL=qwen3.5:9b` 로 배포했으나, 서브에이전트를 쓰는 일부 경로가 모델을 **하드코딩**:
- `bastion/agent.py:1698` — `sub_model = "gemma3:4b"` (w23 QA→실행가능 추출)
- `bastion/agent.py:3136` — `sub_model = "gemma3:4b"`
- `bastion/kg_context.py:83` — `ctx = b.build(message, model="gemma3:4b")` (token budget용, 실호출 아닐 수 있음)

## 영향
- 해당 경로는 지정한 qwen3.5:9b 가 아니라 gemma3:4b 를 호출 → 모델 성능테스트의 순정성 훼손.
- gemma3:4b 가 GPU에 없으면(현재 목록엔 있음) 그 경로 실패 가능.

## 수정안
- 하드코딩을 `os.getenv("LLM_SUBAGENT_MODEL", "gemma3:4b")` 로 교체(3곳). 기본값은 보존, env 우선.
- 수정 후 재배포(docker cp + restart) + 회귀 확인.
- (주의: F9 타임아웃 수정과 함께 배포하면 재시작 1회로 통합 가능.)
