# F9 — 매니저 LLM 지연 > bastion 타임아웃 = 모든 flakiness 의 근본원인 (환경)

- 발견: t-web-waf_r1 (러너, 2026-07-10) 스트림 진단
- 심각도: **높음** (F2·F7·web 반복실패를 전부 설명)
- 상태: 수정 진행 — ①모델 warm ②loop warmup preflight ③(옵션)타임아웃 상향

## 증상
t-web-waf(큐 첫 과제) 스트림:
```
lookup: new | LLM 호출 실패: timed out
error {stage: react, error: timed out}   ← 3회(재시도마다)
step_retry: skill 호출 자체가 없었음 (planning 단계에서 종료)
답변 len=0  → FAIL (waf_on=X, apache_up=X), skills=[]
```
반면 t-siem/t-ips 는 같은 큐에서 PASS(check_wazuh/check_suricata 실행).

## 근본 원인
- 매니저 **gpt-oss:120b 지연**: warm ~90s/call, **cold 133s**(실측).
- bastion LLM 타임아웃(agent.py): `_chat_react` **180s**, `_select_skills_multi` 20s, `_generate_dynamic` 15s, `_select_playbook` 10s.
- **큐 첫 과제 = gpt-oss:120b 콜드로드(133s) + 추론 > react 180s → 타임아웃 → planning 종료 → skills=[]**.
- 후속 과제(siem/ips)는 모델이 warm → 180s 안에 fit → PASS. ⇒ **"첫 과제만 실패"는 콜드로드 아티팩트**.
- 즉 F7(FAIL↔PASS 변동)·web 반복실패는 EG/하네스/프롬프트 문제가 **아니라 지연 vs 타임아웃**.

## 수정 (다중 레버)
- **환경**: gpt-oss:120b·qwen3.5:9b `keep_alive=60m` 예열 → 콜드로드 제거.
- **loop-engineering**: `loop.py` 에 warmup preflight 추가(큐 전 예열) → 첫 과제 콜드스타트 방지.
- **config(옵션)**: react 180→300s, planning 10/15/20→45/60s 상향(복잡 태스크 headroom). agent.py 편집+재배포.
- **부수(F8)**: 서브에이전트 경로 일부가 gemma3:4b 하드코딩 → qwen3.5:9b 미적용. 별도 수정.

## 검증 계획
warm 상태에서 t-web-waf 재실행 → PASS 전환 확인(콜드로드가 유일 원인이면 통과). 여전히 실패면 타임아웃 상향.
