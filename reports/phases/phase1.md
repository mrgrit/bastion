# Phase 1 — 하니스 & 계측 (보고서)

상태: ✅ **하니스 BUILT + E2E 검증 + plumbing 버그 수정 + 유효 ablation 실측** · 2026-06-11
(eg_mode 토글 실증 / frozen-KG 격리 / det-sqli 4×5 → detection saturation 확인)

## 산출물
- `harness/run_eval.py` — 통합 하니스. agent(gpt-oss:120b)·33skill·el34 고정, **메모리 메커니즘만 교체**.
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
- **auditd/eBPF = BLOCKED** — bastion 컨테이너 CAP_AUDIT 부재 + root 불가, el34 권한변경 금지. (syscall-level 도구실행 ground truth 미수집; SOC telemetry 로 대체.)
- 안전성 3지표(4.7) best-effort 수집(파괴명령 사전차단·무승인 high+·환각 자기검증).

## ⚠️ 이전 E2E 표 무효 — plumbing 버그 (2026-06-11 정정)
초기 E2E 표(off ❌ / rest ✅, kg_used=False)는 **무효**다. 원인: 배포 `api.py` 가 구버전이라
요청 `eg_mode` 를 `agent._eg_mode` 로 전달하지 않아 **모든 조건이 default `full` 로 실행**됐고
당시 KG 도 cold 였다. off 실패는 ablation 효과가 아니라 단일런 변동.
상세·수정·재측정: **`reports/findings/ablation_egmode_plumbing_fix.md`**.

## 유효 E2E (수정 후, det-sqli-01 × 4조건 × 5rep, frozen KG)
| 조건 | 탐지 | 완전식별 | kg_used | hits | 기록 |
|------|------|----------|---------|------|------|
| off (No-EG) | 5/5 | 5/5 | 0/5 | 0.0 | 0/5 |
| playbook | 4/5 | 3/5 | 5/5 | 3.0 | 5/5 |
| experience | 5/5 | 5/5 | 5/5 | 5.0 | 5/5 |
| full | 5/5 | 5/5 | 5/5 | 8.0 | 5/5 |

독립오라클(Wazuh 100251) 20/20. **off 가 진짜 No-EG(kg_used 0/5)** 로 작동 = 하니스+ablation 메커니즘 검증 완료.
**해석**: det-sqli saturation(base 가 단독 5/5) → EG 탐지 이득 측정 불가. el34 Wazuh 가 Suricata 를 ingest(86601)
하는 **통합 SIEM** 이라 탐지축은 공격유형 무관 saturate. → RQ1 신호는 응답/held-out task 로 측정해야 함.

## 다음 (Phase 2)
6 외부 baseline 충실 이식 + sanity (최대 리스크) + 3090 커리큘럼 자기메모리 적재 어댑터.
+ **RQ1 측정 대상 전환**: 탐지(saturate) → **응답/remediation·held-out 환경특이 task**.
