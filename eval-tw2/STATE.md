# STATE.md — Bastion tw2/el34 teach-until-pass 루프 (durable state spine)

> loop-engineering 의 상태 척추. 대화와 무관하게 여기가 단일 진실. 매 작업 단위 후 갱신.
> 마지막 갱신: 2026-07-10 · heartbeat #1 · 담당: Claude Code (checker/teacher)

## 0. 이 작업이 뭔가
구 **CCC/6v6** 기반으로 만들어진 bastion 학습·실습·공방전 평가 장치를 **tw2/el34 + 신규 GPU** 로
포팅하고, **teach-until-pass 루프**로 bastion 성능을 테스트한다.
- bastion = **maker**(피시험 에이전트). CC = **checker/teacher/loop-engineer**.
- 루프: 과제(공부/실습/공방전) → bastion 이 힌트 없이 수행 → CC 채점(Assessor+증거) →
  실패 시 CC 가 **E.G(experience/graph)·harness(페르소나/스킬/플레이북)** 개선(정답 비주입) → 임계까지 재작업.

## 1. 검증된 환경 (단일 진실 — 코드/문서는 여기 기준)
| 항목 | 값 | 상태 |
|---|---|---|
| GPU/Ollama | `http://211.170.162.109:11434` | ✅ 도달(.211→GPU 확인) |
| 매니저 모델 | `gpt-oss:120b` | ✅ /api/chat 'READY' (~90s/call, 콜드 133s) |
| 서브에이전트 모델 | `qwen3.5:9b` | ✅ /api/chat 'READY' (~16s/call, thinking 동반) |
| attack(unsafe) 모델 | `gurubot/gpt-oss-derestricted:120b` | ✅ 헬스 노출 |
| el34 타깃 호스트 | `192.168.0.211` (ssh ccc/1) | ✅ el34-* 41컨테이너 가동 |
| 웹 엔트리 | `192.168.0.161:80` | ✅ (.161:9100 은 dockerd 점유 → publish 금지) |
| Assessor(결정론 채점) | `http://192.168.0.211:9201` (X-API-Key: ccc-api-key-2026) | ✅ OPEN |
| 외부 공격자 VM | `192.168.0.113` (ssh ccc/1) | ✅ RED 배틀용 |

## 2. bastion 배포 상태
- 위치: el34-bastion **컨테이너**(호스트 .211), `/opt/ccc-src` 의 풀 bastion(`apps.bastion.api:app` :9100).
  docker.sock 마운트로 형제 `el34-*` 컨테이너를 `docker exec` 제어.
- 런타임 설정 = **`/home/ccc/el34/.env`** (LLM 3값 tw2 반영, 백업 `.env.bak-tw2-20260710`).
- 재생성: `cd /home/ccc/el34 && sudo docker compose -f docker-compose.yaml up -d bastion` (포트 publish 안 함).
- 구동/헬스 접근: `sudo docker exec el34-bastion curl -s localhost:9100/<path>` (호스트 publish 없음).
- 헬스 실측: skills=33, **KG graph_nodes=364 / history_anchors=180**(시드된 E.G 존재), harness 팀 8종, 페르소나 12종,
  discovery 역할맵 el34-* 정상. **playbooks=0**(경로 미설정 의심 — finding F3).

## 3. 연속성 (이전 작업 위치)
- 구 6v6 베이스: `/home/ccc/ccc` (repo `mrgrit/ccc`) — `bastion_test_progress.json`(3090 커리큘럼),
  `scripts/eg/`, `bastion_watchdog.py`, `docs/bastion-autopilot/`(사이클 리포트 cadence).
- bastion repo: `mrgrit/bastion` — `Bastion_Ch4_Eval_Runbook.md`, `harness/`, `state/ledger.json`, `reports/`(Ch4).
- 이번 포팅 작업물: 브랜치 **`eval-tw2`**, 작업 클론 `/home/ccc/bastion`(이 호스트).

## 4. Findings (누적)
- **F1** qwen3.5:9b·gpt-oss:120b 둘 다 **reasoning/thinking 모델** → 서브에이전트 tier 가 이제 "생각"함(구 qwen3:8b/gemma3:4b 는 non-thinking). content 정상이나 지연·토큰↑.
- **F2** 단일 ollama 백엔드 **모델 스왑 직렬화** → 매니저(90s)↔서브(16s) 교대 시 harness 1회가 수분~십수분. 루프 cadence 반영 필요.
- **F3** 배포 bastion `playbooks=0` — `BASTION_PLAYBOOKS_DIR` 미설정/미마운트 의심. 정적 playbook 경로가 teach-until-pass 튜닝 대상이므로 조사 예정.
- **F4** compose 가 published 포트를 `.161`(웹엔트리)에 바인딩 → 9100 충돌(dockerd 점유). publish 회피(docker exec 구동)로 해소.

## 5. 결정 (사용자 지시/기본값)
- 소통 **한국어**. **순차 실행만**(병렬/백그라운드/배치 러너 금지, 오래 걸리면 먼저 물어봄).
- bastion=el34 .211 컨테이너 / 보고=`mrgrit/bastion` **eval-tw2** 브랜치 / 세션범위=포팅+배포+1회 보정루프.
- 사용자 지정 모델(gpt-oss:120b / qwen3.5:9b) 유지 — 지연 과도해도 임의 교체 금지, 보고만.

## 6. 현재 위치 / 다음
- ✅ 포팅·배포·검증 완료. ⏭ 루프 스크립트(scripts/eval) 구축 → **1회 보정 루프**(과제 1개 무힌트 → 채점 → 필요시 튜닝) → 재작업 임계 실측.
- ⚠ 보안: 노출 PAT `ghp_…C2oVxJN` 은 이번 실행 후 **회전 필요**(.eval-secrets 에만 보관, 커밋 0건 확인).
