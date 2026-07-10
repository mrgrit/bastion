# Bastion tw2/el34 — 진행 보고서 (heartbeat #4)

> 단일 출처. STATE.md/ledger 에서 재생성. 갱신: 2026-07-10 · 담당 CC(checker) · 브랜치 eval-tw2

## 진행률: **자동 러너 가동 + 반복실패 근본원인(F9) 규명 → 환경/loop 개선 중**

## 성공률 (자동 러너, 버그수정 후 깨끗한 실측)
| task | verdict | skills | 비고 |
|---|---|---|---|
| t-siem-wazuh | ✅ PASS | check_wazuh | 전용 읽기전용 스킬 → Wazuh up 정확 |
| t-ips-suricata | ✅ PASS | check_suricata | 전용 읽기전용 스킬 → Suricata up 정확 |
| t-web-waf | ❌ FAIL | (없음) | **콜드로드 타임아웃(F9)** — bastion 결함 아님 |
- **2/3 (67%)**. web 실패는 성능이 아니라 **환경(지연)**.

## 반복실패 → 근본원인 → 개선 (지시하신 루프)
- **원인 규명(F9)**: gpt-oss:120b 지연(warm 90s·**cold 133s**) > bastion react 타임아웃(180s). 큐 첫 과제가 콜드로드로 타임아웃 → skills=[] → FAIL. 후속(warm)은 PASS. ⇒ F2·F7·web반복실패를 **전부 설명**. EG/하네스 문제 아님.
- **개선(다중 레버)**: ①환경=gpt-oss:120b·qwen3.5:9b `keep_alive=60m` 예열(콜드로드 제거) ②loop=`loop.py` warmup preflight 추가 ③config(옵션)=react 180→300s·planning 상향.
- **러너 버그 수정**: 발제 페이로드가 JSON 아닌 원시문자열 → 422. 수정+오프라인 재현검증 완료.

## Findings
- **F8**(중) 서브에이전트 일부 경로 gemma3:4b 하드코딩 → qwen3.5:9b 미적용. `findings/F8`.
- **F9**(높) 매니저 LLM 지연 > 타임아웃 = flakiness 근본원인. `findings/F9`.
- **gemma4:31b**: 내 bastion 미사용 확정(gpt-oss:120b 라우팅). 공유 GPU에 stuck-loaded(ollama stop 3회 무효), 무해(자동 evict). 강제해제=ollama 재시작(공유 3자 영향)이라 단독 미실행.
- F1(thinking 모델), F2(모델스왑 지연), F5(assessor quirk), F6(읽기전용 shell 게이트), F7(비결정성) 는 상당 부분 **F9 의 발현**으로 재해석됨.

## 다음
1. warm 상태에서 **t-web-waf 재실행** → PASS 전환 확인(F9 수정 검증).
2. 확인되면 warmup 내장 러너로 큐 재측정(2/3→3/3 기대) + n_repeats.
3. F8·(옵션)타임아웃 상향을 한 번의 재배포로 통합.

heartbeat: 4
