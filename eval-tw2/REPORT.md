# Bastion tw2/el34 — 진행 보고서 (heartbeat #1)

> 단일 출처. STATE.md/ledger 에서 재생성. 갱신: 2026-07-10 UTC · 담당 CC(checker) · 브랜치 eval-tw2

## 진행률: **포팅+배포 완료 → 루프 구축/1회 보정 대기**

| 단계 | 상태 |
|---|---|
| 0 정찰·연속성 파악 | ✅ DONE (구 6v6 `/home/ccc/ccc` + bastion repo 장치 분석) |
| 1 환경 검증(GPU/el34/Assessor) | ✅ DONE |
| 2 작업 클론 + PAT 격리 | ✅ DONE (커밋 내 토큰 0건, .eval-secrets 600) |
| 3 포팅(6v6→tw2/el34, LLM 3값) | ✅ DONE (`/home/ccc/el34/.env`, 백업 보존) |
| 4 bastion 배포+헬스검증 | ✅ DONE (풀 bastion, skills=33, KG 364노드, harness 8·페르소나 12) |
| 5 CC teach-until-pass 루프 구축 | 🔧 진행 중 (LOOP/STATE 작성 완료, scripts/eval 예정) |
| 6 1회 보정 루프 + 임계 실측 | ⏭ 대기 |

## 성공률
- 아직 과제 미실행 → N/A. (구 6v6 참고치: 3090 스텝 중 pass 2493 / fail 558, 이식성은 재검증 대상.)

## Findings
- **F1** 서브에이전트 qwen3.5:9b 및 매니저 gpt-oss:120b **둘 다 thinking 모델** — 구 non-thinking tier 대비 지연·출력형식 변화. content 정상.
- **F2** 단일 ollama **모델 스왑 직렬화** → 매니저 ~90s/호출·서브 ~16s/호출. multi-persona harness 1회 = 수분~십수분. 루프 시간 예산에 반영.
- **F3** 배포 bastion **playbooks=0** — 정적 playbook 경로 미배선 의심(teach-until-pass 튜닝면). 조사 예정.
- **F4** compose published 포트가 `.161`(웹엔트리)에 바인딩돼 9100 충돌 → publish 회피(docker exec 구동)로 해소.

## 개선 방향 / 다음
1. `scripts/eval/` 루프 러너(발제→채점→튜닝→재발제) + `ledger.json` 재개 스파인 구축.
2. **1회 보정 루프** 실행(과제 1개 무힌트) → 재작업 임계 실측(초기 3회).
3. F3(playbooks) 조사 — bastion 개선점이면 진행 중 수정.
4. ⚠ 노출 PAT **회전**(실행 후).

git SHA: (commit 시 갱신) · heartbeat: 1
