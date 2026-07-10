# F7 — 실행 비결정성: 동일 과제·설정이 FAIL→PASS (단발 채점 신뢰불가)

- 발견: calib001 attempt#1 vs #2 (2026-07-10)
- 심각도: **중~높음** (채점·THRESHOLD·재현성의 근간)
- 상태: 방법론 반영(채점을 n_repeats pass-rate 로)

## 증상
동일 무힌트 과제("el34-web WAF/Apache 점검"), 동일 설정(auto_approve=false), **동일 스킬 사용**
(`check_modsecurity` 1 + `shell` 5회 denied) 인데:
- attempt#1 → Apache "판단 불가" → **FAIL(1/2)**
- attempt#2 → Apache "정상 동작 중"(modsec 로그의 `Apache/2.4.52 403` 에서 추론) → **PASS(2/2)**

차이는 오직 **최종 합성(validating) 단계의 LLM 추론 방식**. 매니저 gpt-oss:120b(thinking, F1)의
run-to-run 변동. bastion 이 억측 없이 증거기반 추론한 것 자체는 정상.

## 함의
- **단발 pass/fail 채점은 신뢰 불가** — 우연 통과/실패 가능.
- 채점은 **n_repeats 다수결 pass-rate** 로(논문 Ch4 n_repeats=5 와 정합). 초기 n_repeats=3 채택.
- 재작업 THRESHOLD 은 "1회 통과"가 아니라 "pass-rate 개선"으로 정의.
- 튜닝 효과 귀속(attribution)도 n_repeats 전후 비교 필요 — 단발 PASS 를 "튜닝 성공"으로 오귀속 금지(F6 사례).

## 조치
- LOOP.md 채점 규칙 갱신: grade = n_repeats(기본 3) 다수결 + 결정론 Assessor 우선.
- 온도/시드 고정 검토(가능하면 planning/validating LLM temperature=0) → 변동 축소.
