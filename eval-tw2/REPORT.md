# Bastion tw2/el34 — 진행 보고서 (heartbeat #2)

> 단일 출처. STATE.md/ledger 에서 재생성. 갱신: 2026-07-10 05:16 UTC · 담당 CC(checker) · 브랜치 eval-tw2

## 진행률: **포팅+배포 완료 · 루프 배관 E2E 검증(첫 보정 datapoint 확보) → F6 튜닝/재작업 진행**

| 단계 | 상태 |
|---|---|
| 0 정찰·연속성 | ✅ |
| 1 환경 검증 | ✅ |
| 2 클론+PAT 격리 | ✅ (커밋 토큰 0건) |
| 3 포팅(LLM 3값) | ✅ |
| 4 bastion 배포+검증 | ✅ (풀 bastion, skills=33, KG 364, harness 8·페르소나 12) |
| 5 CC teach-until-pass 루프 | ✅ 스파인(STATE/LOOP/ledger) + E2E 1사이클 실증 |
| 6 1회 보정 + 임계 실측 | 🔧 attempt#1 완료(FAIL) → attempt#2(F6 튜닝) 대기 |

## 성공률 (첫 datapoint)
- **calib001**(BLUE 읽기전용: el34-web WAF/Apache 점검): **attempt#1 = FAIL (1/2)**.
  - WAF: `check_modsecurity` 정확(SecRuleEngine On) ✓ / Apache: `shell` 5회 denied → 판단불가 ✗.
  - 소요 ~19분(매니저 gpt-oss:120b 지연 지배적). run: `eval-tw2/runs/calib001.ndjson`.
- 누적 통과율: 0/1 (1 OPEN). 임계 THRESHOLD 초기 3 — attempt#2 결과로 조정.

## Findings
- **F1** 서브 qwen3.5:9b·매니저 gpt-oss:120b 둘 다 thinking 모델(지연·토큰↑, content 정상).
- **F2** 단일 ollama 모델스왑 직렬화 → 매니저 ~90s/호출. harness 1회 = 수분~십수분. (calib001 ~19분 실측)
- **F3** 배포 bastion playbooks=0 (정적 playbook 미배선). F6 튜닝과 함께 해소 후보.
- **F5** Assessor `process_running@web pattern=apache` 증거표기 quirk(채점 무영향, port_listening 로 대체).
- **F6**(신규·중) 읽기전용 점검이 `shell` 승인게이트에 막혀 미완 → 완수율 저해. `eval-tw2/findings/F6-*`. **bastion 개선점**.

## 개선 방향 / 다음
1. **attempt#2 — F6 튜닝**: 읽기전용 서비스 점검을 shell 대신 read-only recon(scan_ports/probe)로 라우팅(하네스/E.G) 또는
   read-only shell 게이트 허용(코드). 정답 비주입. → 재발제 후 통과 여부로 THRESHOLD 실측.
2. 루프 러너 스크립트(`scripts/eval/`) 코드화 — 이번 실측 흐름을 재사용화.
3. ⚠ 노출 PAT 회전(실행 후).

git SHA: (commit 시 갱신) · heartbeat: 2
