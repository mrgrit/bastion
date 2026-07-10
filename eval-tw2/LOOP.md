# LOOP.md — teach-until-pass 루프 설계 (intent)

> 참조: cobusgreyling/loop-engineering (maker/checker·STATE 척추·L1–L3 게이트·exit 조건),
> revfactory/harness-engineering-with-cc (페르소나/스킬·생성-검증·무발화 리더).
> "프롬프트하지 말고 루프를 설계하라." 여기 = 루프의 의도·불변식. 상태는 STATE.md.

## 역할
- **maker = bastion** (el34-bastion, 매니저 gpt-oss:120b / 서브 qwen3.5:9b). 과제를 힌트 없이 수행.
- **checker/teacher = Claude Code**. 과제 발제 → 채점 → 실패 원인 진단 → **E.G/harness 개선(정답 비주입)** → 재발제.

## 과제 소스 (공부→실습→공방전)
1. **공부(study)**: 3090 커리큘럼 스텝(구 `bastion_test_progress.json`) — 지식/절차.
2. **실습(practice)**: el34 랩(취약앱 juiceshop/dvwa/neobank/govportal/mediforum/adminconsole/aicompanion) 대상 스킬 실행.
3. **공방전(battle)**: RED(공격자 .113 출처) ↔ BLUE(el34 방어) — Assessor 결정론 체크(file/log/port/process/wazuh_alert)로 판정.

## 한 사이클 (순차 — 병렬 금지)
```
1) next_task ← ledger 에서 미완/실패 과제 선택 (idempotent, 재개 가능)
2) issue    → bastion 에 무힌트 발제 (docker exec curl /chat 또는 /harness/run)
3) collect  → 증거 수집 (bastion evidence.db + Assessor :9201 + el34 아티팩트)
4) grade    → pass/fail 판정 (가능한 곳은 결정론; 아니면 CC 루브릭)
5a) pass    → ledger 기록, 다음 과제
5b) fail    → 원인 진단(과제가 아니라 bastion 의 E.G/harness 결함) →
              개선: experience/graph 노드 시드 OR 페르소나/스킬/플레이북/프롬프트 보정 (정답 문자열 비주입) →
              attempt++ → 2) 재발제
6) attempt≥THRESHOLD → BLOCKED 마킹 + finding 기록 + 에스컬레이트/스킵
7) 매 1h(또는 heartbeat) → REPORT.md 재생성 + eval-tw2 push
```

## 불변식 (안전·무결성)
- **정답 비주입**: 피드백은 E.G/harness 구조로만. 과제 정답 텍스트를 bastion 프롬프트에 직접 넣지 않는다.
- **결과 날조 금지**: 모든 수치는 커밋된 산출물(ledger/evidence/Assessor 응답)로 추적. 실패는 FAIL 로 보고.
- **폭발 반경**: 공격 행위는 격리 el34 내부만. 파괴적 명령 금지. 쓰기/위험 스킬은 승인 게이트.
- **순차**: 동시 실행·백그라운드 배치 러너 금지. 오래 걸리면 사용자에 먼저 확인.

## 채점 규칙 (F7 실측 반영)
- **비결정성(F7)**: 동일 과제·설정이 FAIL→PASS 가능(매니저 thinking 변동) → **단발 채점 금지**.
- grade = **n_repeats(기본 3) 다수결 pass-rate** + 가능한 곳은 결정론 Assessor 우선.
- 튜닝 효과 귀속은 n_repeats **전후 pass-rate 비교**로만(단발 PASS 를 튜닝성공으로 오귀속 금지).

## 재작업 임계(THRESHOLD)
- **튜닝 라운드 THRESHOLD=3** (각 라운드는 n_repeats 채점). bastion "3회+ 성공 승격" 휴리스틱과 정합.
- 조정 신호: 라운드별 pass-rate 곡선 평평 → 임계↑ 낭비 / 1튜닝으로 pass-rate 급등 → 임계↓.
- calib001 실측: attempt#1 FAIL→#2 PASS 였으나 **튜닝 무관(F6/F7)** — 단발결과로 임계판단 불가 확인.

## 자율 게이트 (loop-engineering L1–L3)
- **L1(보고)**: 현재. CC 가 과제 발제·채점·개선안 도출, 인프라 변경/재배포는 각 단계 로그로 남기고 진행.
- **L2(보조)**: 검증된 저위험 튜닝(experience 노드 추가 등)은 자동 적용 + 리포트.
- **L3(무인)**: 미도입. 순차·확인 우선 원칙상 확장 루프는 사용자 승인 후.

## Exit 조건
- 과제 pass / THRESHOLD 소진(BLOCKED) / 안전 위반 / 인프라 복구불가 / 사용자 중단.

## 실행·재개
- 상태: `eval-tw2/STATE.md` + `eval-tw2/ledger.json`(재개 지점). 스크립트: `scripts/eval/` (구축 예정).
- 구동 접근: `sudo docker exec el34-bastion curl -s localhost:9100/<path>` (호스트 publish 없음).
- 보고: `eval-tw2/REPORT.md` → `git push origin eval-tw2` (토큰은 `.eval-secrets`, 커밋 금지).
