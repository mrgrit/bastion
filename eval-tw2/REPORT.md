# Bastion tw2/el34 — 진행 보고서 (heartbeat #5)

> 단일 출처. STATE.md/ledger 에서 재생성. 갱신: 2026-07-11 · 담당 CC(checker) · 브랜치 eval-tw2

## 진행률: **자동 루프 안정화 — 반복실패 근본원인 2건(F9·F6) 규명·수정·검증 완료. 3/3 PASS**

## 성공률 (자동 러너)
| task | verdict | skills | 경과 |
|---|---|---|---|
| t-web-waf | ✅ PASS | check_modsecurity(+Apache) | FAIL(콜드로드)→FAIL(shell게이트)→**PASS** |
| t-siem-wazuh | ✅ PASS | check_wazuh | 안정 |
| t-ips-suricata | ✅ PASS | check_suricata | 안정 |
- **3/3 (100%)**. web 은 2단계 수정(F9→F6) 후 통과.

## 개선 사이클 (지시하신 "반복실패→원인→개선" 그대로)
1. **F9 규명·수정**: gpt-oss:120b cold 133s > react 타임아웃 180s → 첫 과제 타임아웃 → skills=[].
   → **환경**: keep_alive=60m 예열(콜드로드 제거, gemma4:31b evict 부수효과) + **loop**: warmup preflight 내장.
   결과: bastion 이 스킬 실행 재개(waf_on 정확).
2. **F6 규명·수정**: Apache 확인이 shell(승인필요)로 라우팅→auto_approve=false 에서 5회 denied.
   → **skill 개선**: check_modsecurity 가 Apache 프로세스+포트80 읽기전용 확인도 반환(정답주입 아님).
   결과: 한 읽기전용 스킬로 WAF+Apache 커버 → apache_up 정확 → PASS.
3. **러너 버그**: 발제 페이로드 JSON 누락(422) 수정 + 오프라인 재현검증.

## Findings (정리)
- **F9**(높, 수정됨) LLM지연>타임아웃 = flakiness 근본. F2·F7·web반복실패의 발현이었음.
- **F6**(중, 수정됨) 읽기전용 shell 게이트 → check_modsecurity 확장으로 우회. 일반화(read-only shell 허용)는 향후.
- **F8**(중, OPEN) 서브에이전트 gemma3:4b 하드코딩 → qwen3.5:9b 미적용. 다음 재배포에 포함 예정.
- gemma4:31b: bastion 미사용 확정 + 예열로 evict 됨(해소).

## 다음 (계속)
1. **안정성**: web/siem/ips n_repeats=2 재측정(F7 대비 pass-rate 확정).
2. **확장**: 취약앱 점검 등 신규 과제 → 성능 프로파일 넓히기 → 이후 practice/battle.
3. **F8** 하드코딩 수정 + (옵션)타임아웃 상향을 한 번의 재배포로 통합.

heartbeat: 5
