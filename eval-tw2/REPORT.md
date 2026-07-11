# Bastion tw2/el34 — 진행 보고서 (heartbeat #6)

> 단일 출처. STATE.md/ledger 에서 재생성. 갱신: 2026-07-11 · 담당 CC(checker) · 브랜치 eval-tw2

## 진행률: **자동 루프 안정화 완료 — bastion BLUE 점검 유효과제 100%, 채점기 견고화(LLM-judge)**

## bastion 성능 (F9·F6 수정 후, 견고한 채점 기준)
| task | pass-rate | 스킬 |
|---|---|---|
| t-web-waf (WAF+Apache) | **2/2** | check_modsecurity(+Apache) |
| t-siem-wazuh | **2/2** | check_wazuh |
| t-ips-suricata | **2/2** | check_suricata |
- **유효 BLUE 점검 6/6 (100%)**. bastion 은 전용 읽기전용 스킬이 있는 점검을 안정적으로 수행.

## 개선 여정 (지시하신 "반복실패→원인→개선"의 연속)
1. **러너 페이로드 버그**(JSON 미포장→422) → 수정+오프라인 재현.
2. **F9**(콜드로드 타임아웃): gpt-oss:120b cold 133s > react 180s → 첫 과제 skills=[]. → 모델 keep_alive 예열 + loop warmup preflight. (gemma4:31b evict 부수해결)
3. **F6**(Apache 읽기전용 shell 게이트): check_modsecurity 가 Apache 프로세스+포트80 읽기전용 확인도 반환 → web PASS.
4. **채점기 취약성**: regex mustnot 이 긴 답변의 하위요소("일부 데몬 중단") 언급을 오탐 → **LLM-judge(qwen3.5:9b, think:false)** 도입 + regex 완화. 저장 run 재채점으로 검증(LLM=regex 전건 일치).

## 정정/종결
- 직전 "5/7" 의 2 실패는 **bastion 아님**: siem_r2=채점 오탐(교정됨), t-juice-up=Assessor 가 juiceshop 미매핑(불가과제, 제거).
- **F8**(서브 gemma3:4b) → **오탐, CLOSED**(실제 qwen3.5:9b 사용, gemma3:4b 는 예외폴백/docstring).

## 남은 개선 여지 (관측)
- **F6 일반화**: 전용 스킬 없는 대상(예: 취약앱)은 여전히 shell(denied) 로 빠짐 → read-only shell 허용 또는 범용 read-only 서비스체크 스킬이 근본해결.
- **F7**(비결정성)은 상당부분 F9 발현이었음 — 예열 후 편차 축소 확인.

## 다음 (계속)
1. **난이도/폭 확장**: 탐지(로그·공격흔적)·응답 과제 → 성능 프로파일.
2. **battle(RED/BLUE)**: 공격자 .113 → BLUE 대응, Assessor 결정론 채점.
3. 필요시 F6 일반화(read-only shell) 재배포.

heartbeat: 6
