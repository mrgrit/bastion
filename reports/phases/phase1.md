# Phase 1 — 하니스 & 계측 (보고서)

상태: ✅ **하니스 BUILT + E2E 검증** (bastion EG-ablation 4조건) · 2026-06-11

## 산출물
- `harness/run_eval.py` — 통합 하니스. agent(gpt-oss:120b)·33skill·6v6 고정, **메모리 메커니즘만 교체**.
  (event × condition) → eval_reset event-start → bastion(eg_mode) → SOC 독립오라클 → 채점 → run_id 감사레코드(§6) → event-reset.
- `harness/eval_reset.sh` — §2.3 클린리셋(D). 검증 ROUNDTRIP_PASS.
- `results/runs/<run_id>.json` — 실행별 감사레코드(§6): run_id·조건·RQ·seed·git SHA·model digest·SOC오라클·metrics·안전성3지표·raw로그경로.

## 조건 (memory mechanism)
| 조건 | 상태 |
|------|------|
| bastion-off / playbook / experience / full | ✅ 네이티브(eg_mode per-request, agent.py+kg_context.py) |
| vanilla-react / summary-react / reflexion / expel / awm / amem / flat-rag | ❌ BLOCKED-phase2 (충실 이식 필요) |
| commercial-bare (참조상한) | ❌ BLOCKED-online-§9 |

## 계측
- 독립 오라클: **SOC(Wazuh/Suricata)** — SUT(bastion) 분리, 사건 타임윈도우로 격리. oracle_fired 검증.
- **auditd/eBPF = BLOCKED** — bastion 컨테이너 CAP_AUDIT 부재 + root 불가, 6v6 권한변경 금지. (syscall-level 도구실행 ground truth 미수집; SOC telemetry 로 대체.)
- 안전성 3지표(4.7) best-effort 수집(파괴명령 사전차단·무승인 high+·환각 자기검증).

## E2E 검증 (1 event × 4 ablation, det-sqli-01)
| 조건 | oracle | detected | type/src | kg_used | tools | secs |
|------|--------|----------|----------|---------|-------|------|
| off | ✅ | ❌ | F/F | False | 6 | 202.7 |
| playbook | ✅ | ✅ | T/T | False | 2 | 105.0 |
| experience | ✅ | ✅ | T/T | False | 4 | 86.8 |
| full | ✅ | ✅ | T/T | False | 5 | 79.3 |

**해석(무결성)**: 하니스 plumbing 검증 = 목적 달성. 단 **off≠rest 는 ablation 효과 아님** —
모든 조건 `kg_used=False/hits=0`(cold KG, 0 검색) + **n=1**. off 실패는 단일런 변동. 진짜 ablation 결론은
n_repeats(5)×다수 event + **KG 관련성 확보**(seed/누적) 후 Phase 7 에서만. 지금 수치는 결과로 인용 금지.

## 다음 (Phase 2)
6 외부 baseline 충실 이식 + sanity (최대 리스크) + 3090 커리큘럼 자기메모리 적재 어댑터.
+ cold-KG 해소(RQ1 ablation 유의미화 전제).
