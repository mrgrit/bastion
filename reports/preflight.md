# Preflight 보고서 (Runbook §2)

실행: 2026-06-11 UTC · 평가 repo: mrgrit/bastion · 논문: contents/papers/experience-graph (ccc)

## 판정 요약: ⛔ **HARD-STOP** — preflight 미통과 (§2.3 실패 + 핵심 컴포넌트 미구현)

| # | 항목 | 상태 | 근거 |
|---|------|------|------|
| 2.1 | Git egress (remote+push) | ✅ PASS | mrgrit/bastion push 가능. **⚠️ 보안: remote URL 에 GitHub PAT 평문 노출 — 즉시 revoke/회전 필요** |
| 2.2 | 모델 서빙 120/20/8 | ✅ PASS | 0.109(GB10, ollama 0.30) 에 gpt-oss:120b·20b, qwen3:8b·ministral-3:8b 가용. 4c 규모곡선 가능 |
| 2.3 | 6v6 스냅샷/롤백 | ❌ **FAIL** | 6v6.sh = up/down/destroy/setup 뿐, **snapshot/rollback/restore 명령 부재**. 사건당 클린리셋 IaC 없음(destroy+recreate 는 수백 사건엔 비현실적). → §2 규칙상 HARD-STOP |
| 2.4 | 도구 | △ PARTIAL | auditd ✅, Wazuh ✅(analysisd up), python ✅, git ✅ / **bpftrace(eBPF) MISSING** / secret-scan 미구성 |
| 2.5 | 비밀정보 경로 | ⚠️ | .gitignore 신규작성. **PAT 노출(2.1)** + push-전 secret-scan 미구성 |

## 핵심 컴포넌트 가용성 (실행 가능 여부)
| 컴포넌트 | 상태 | 비고 |
|----------|------|------|
| 논문 4장 정의(RQ1–4, 4.7) | ✅ 존재 | ccc/contents/papers/experience-graph/{05-evaluation-protocol,07-evaluation-harness,09-test-plan}.md |
| 7조건 공용 하니스(메모리 교체형) | ❌ 미구현 | Phase 1 |
| Phase 2 베이스라인 7종 (Reflexion/ExpeL/AWM/A-MEM/RAG …) | ❌ **미구현** | 논문 .md 설명만, 코드 없음 — RQ1 핵심 비교 불가 |
| ablation 토글(off/playbook/experience/full + 구성요소제거) | ❌ 미구현 | Phase 1 |
| 독립 오라클 배선(auditd→ground truth, SUT 분리) | ❌ 미구현 | auditd 바이너리는 존재 |
| 3090 커리큘럼 runnable 랩 | △ 부분 | standalone 248 yaml + holdout-462/holdout-6v6 = **스펙 YAML**. 7조건 runnable 미검증 → §3 BLOCKED |
| 외부 CTF 3종(Cybench/NYU/InterCode) | △ | bench_data 에 데이터 있음(secu_agent_benchmark), 비격리 경로 필요(§9) |
| bastion full(ablation `full` 1조건) | ✅ 부분 측정됨 | 별도 작업에서 방어탐지 웹71(120b 66%) + 공격축 225/323 실측 — RQ4/RQ1-full 일부에 해당 |

## 결론
논문 4장 **전체 자동 실행은 현 환경에서 불가**. 빌드 필요(수 주, 다회 세션):
1. 6v6 스냅샷/롤백 IaC (§2.3) — 사건당 클린리셋 전제
2. 7조건 메모리-교체형 공용 하니스 + ablation 토글 (Phase 1)
3. 베이스라인 6종 충실 이식 + sanity (Phase 2, 최대 리스크)
4. auditd 독립 오라클 배선 (Phase 1)
5. 3090 커리큘럼 + L1/L2 + 6v6 60-suite runnable화 (Phase 3)

과학적 무결성 원칙(§1)상 미구현 컴포넌트를 반쪽 빌드로 "완료" 표시하지 않는다. 본 보고서 push 후 HARD-STOP.
유지관리자 결정 필요: (a) 빌드 우선순위·일정 (b) PAT revoke + 새 토큰 (c) §9 온라인 항목 in-scope 여부.
