# Bastion tw2/el34 — 진행 보고서 (heartbeat #3)

> 단일 출처. STATE.md/ledger 에서 재생성. 갱신: 2026-07-10 07:21 UTC · 담당 CC(checker) · 브랜치 eval-tw2

## 진행률: **포팅+배포+루프 완전 실증(발제→채점→튜닝→재작업 2사이클). 재작업 THRESHOLD 실측 완료**

| 단계 | 상태 |
|---|---|
| 0–4 정찰·환경·클론/PAT·포팅·배포 | ✅ (bastion 풀 가동: skills=33, KG 364, harness 8·페르소나 12) |
| 5 CC teach-until-pass 루프 | ✅ 스파인(LOOP/STATE/ledger) + 발제→채점→튜닝→재작업 E2E 2회 실증 |
| 6 1회 보정 + THRESHOLD 실측 | ✅ 2 attempt 완료(FAIL→PASS) — THRESHOLD 규칙 실측 개정 |

## 성공률
- **calib001**(BLUE 읽기전용): attempt#1 **FAIL(1/2)** → attempt#2 **PASS(2/2)** = `PASS_UNSTABLE`.
- 정직 귀속: attempt#2 PASS 는 **F6 튜닝 효과 아님**(스킬설명 튜닝은 라우팅 못 바꿈, 여전히 shell denied) — **LLM 추론변동(F7)** 때문.
- 소요: attempt당 ~19–21분(매니저 gpt-oss:120b 지연 지배).

## 재작업 THRESHOLD (실측 결론)
- 초기 "1회 통과=성공"은 **F7 비결정성으로 신뢰불가**. → **채점 = n_repeats(초기 3) 다수결 pass-rate**, 튜닝라운드 THRESHOLD=3.
- 튜닝 효과 귀속도 n_repeats 전후 비교 필수(단발 PASS 를 튜닝성공으로 오귀속 금지).

## Findings
- **F1** 매니저·서브 둘 다 thinking 모델(지연·토큰↑).
- **F2** 단일 ollama 모델스왑 직렬화 → 매니저 ~90s/호출, attempt 1회 ~19–21분 실측.
- **F3** playbooks=0 (정적 playbook 미배선) — 결정론 라우팅 튜닝의 상위 레버 후보.
- **F5** Assessor process_running@web 증거 quirk(채점 무영향).
- **F6** 읽기전용 점검이 shell 게이트에 막힘 → **스킬설명 튜닝은 라우팅 개선 실패**. playbook/harness 로 상향 필요.
- **F7**(중~높) 실행 비결정성: 동일 과제·설정이 FAIL→PASS → 단발 채점 불가, n_repeats 필요.

## 개선 방향 / 다음
1. 채점을 **n_repeats 다수결**로 전환(LOOP.md 반영 완료). calib001 을 n=3 재측정해 진짜 pass-rate 확정.
2. F6 결정론 라우팅: **playbook `web_health_check`**([check_modsecurity, scan_ports]) 배선(F3 동시해소) 또는 harness 팀 경로.
3. 루프 러너 스크립트(`scripts/eval/`) 코드화(이번 흐름 재사용) — 다음 세션.
4. ⚠ 노출 PAT **회전**(실행 후).

git SHA: (commit 시 갱신) · heartbeat: 3
