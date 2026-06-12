# Bastion Ch4 평가 — 진행 보고서 (REPORT.md)

> 단일 출처. 매 작업 단위 후 ledger 에서 재생성. 마지막 갱신: 2026-06-11 UTC · heartbeat #4

## 전체 진행률: **Phase 1 완료(plumbing 버그 수정 + 유효 ablation 실측) → Phase 2 베이스라인 대기** · heartbeat #4

> 🔴 **핵심**: 배포 api.py 구버전이 `eg_mode` 를 버려 **이전 모든 ablation 이 사실상 full 단일조건**이었음을
> 발견·수정. eg_mode 토글 실증 + frozen-KG 격리 후 유효 재측정. det-sqli 4×5 → **detection saturation**
> (off 가 No-EG 로 5/5). 상세: `reports/findings/ablation_egmode_plumbing_fix.md`.

| Phase | 상태 |
|-------|------|
| 0 Bootstrap/Preflight | ✅ DONE (preflight PASS — §2.3 D방식 `eval_reset.sh` ROUNDTRIP_PASS) |
| 1 하니스&계측 | ✅ DONE (run_eval.py: eg_mode 토글 실증 + frozen-KG 격리 + 멀티센서오라클 + run_id 감사; auditd=BLOCKED) |
| 2 베이스라인 7종 | PENDING (미구현 — 최대 리스크) |
| 3 데이터셋 | PARTIAL (스펙 YAML 존재, runnable 미검증) |
| 4 측정·채점 | PENDING |
| 5 스모크 | PENDING |
| 6 사전학습 | PENDING |
| 7 평가(RQ1–4) | PENDING |
| 8 분석 | PENDING |

## 상태 (§2/§7)
- ✅ preflight PASS — §2.3 클린리셋 D방식 구현·검증(`harness/eval_reset.sh`).
- ⏭️ Phase 1/2(7조건 하니스, 6 베이스라인, auditd 독립오라클 배선) **미구현** = 다음 빌드 대상(수 주). 무결성상 반쪽 빌드 위장 안 함.
- 상세: `reports/preflight.md`.

## 조건 × RQ 매트릭스 (현재)
| RQ | 조건 | 상태 |
|----|------|------|
| RQ1 (E.G) — 탐지축 | off/playbook/experience/full | ✅ 유효 ablation(det-sqli·recon 4×5): off=만점 → **detection saturation**, EG 탐지이득 측정불가(통합 SIEM 86601). |
| RQ1 (E.G) — 응답축 | off/playbook/experience/full | ✅ remediation 4×5 (fw IP차단, 객관오라클): **off=0/5 vs EG조건=2/5** (탐지 saturation 과 대조=방향성 EG 이득). experience/full=recipe 검색 5/5(KG-2 Reuse retrieval), 단 적용 stochastic(retrieval≠application). 상세 `reports/findings/rq1_response_remediation.md` |
| RQ2 (커리큘럼) | empty vs 축적 E.G | ❌ 하니스 미구현 |
| RQ3 (SIEM 감사) | 변조탐지·완전성 | ❌ 독립오라클 배선 미구현 (auditd 바이너리는 존재) |
| RQ4 (6v6 타당성) | CTF↔6v6, 규모곡선 | △ 부분(secu_agent_benchmark: 적합화 225/323, 모델 120/20/8 가용) |
| 안전성(4.7) | 3지표 | ❌ 미수집(하니스 의존) |

## 이미 실측된 인접 결과 (참고, 본 Runbook 산출물 아님 — secu_agent_benchmark)
- 공격축(bastion이 외부벤치 푸는지): **29/174 (16%)** — cybench 가짜합격 12 감사·정정 후.
- 방어축(bastion이 공격 탐지): **웹71 모델비교** 120b 47/71(66%) / 20b 0/71 / gemma4:31b 0/71.

## 다음 (유지관리자 결정 대기)
1. **RQ1 측정 대상 전환**: 탐지(saturate 확인됨) → **응답/remediation·held-out 환경특이 task**.
   탐지축은 통합 SIEM+강한 base 로 EG 변별 불가가 실증됨. EG 가치=KG-2 Reuse(P24 266/266 기실증).
2. Phase2 베이스라인 6종(Reflexion/ExpeL/AWM/A-MEM/RAG/vanilla) 충실 이식 + sanity.
3. **노출 PAT revoke + 새 토큰** (push 경로 의존).
4. §9 온라인(상용 모델·외부 CTF) in-scope 여부.

git SHA: (commit 시 갱신) · heartbeat: 4
