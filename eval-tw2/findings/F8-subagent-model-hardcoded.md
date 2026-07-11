# F8 — (정정: 오탐) 서브에이전트 gemma3:4b 는 예외 폴백일 뿐, qwen3.5:9b 정상 사용

- 발견: gemma4:31b 조사 중 (2026-07-10) → **재검증 후 하향 정정 (2026-07-11)**
- 심각도: ~~중~~ → **낮음(버그 아님)**
- 상태: **CLOSED (수정 불필요)**

## 정정 (실제 코드 재확인)
초기엔 `sub_model = "gemma3:4b"` 만 grep 으로 보고 하드코딩으로 판단했으나, 문맥 확인 결과:
- `agent.py:1696-1698`, `3134-3136`: `try: sub_model = LLM_SUBAGENT_MODEL` / `except: sub_model = "gemma3:4b"`
  → **정상 경로는 LLM_SUBAGENT_MODEL(=qwen3.5:9b)**. gemma3:4b 는 전역 미정의 시 방어 폴백(실제론 안 탐).
- `kg_context.py:83`: **docstring 예시**(실행 코드 아님).
→ 결론: **qwen3.5:9b 가 실제로 사용됨. 테스트 순정성 훼손 없음. 수정/재배포 불필요.**
(교훈: grep 매치만으로 버그 단정 금지 — 문맥 확인 후 판정. 원래 F8 severity 오판.)

## (이전 오판 기록)

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
