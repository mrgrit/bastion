# Preflight 보고서 (Runbook §2)

실행: 2026-06-11 UTC · 평가 repo: mrgrit/bastion · 논문: contents/papers/experience-graph (ccc)

## 판정 요약: ✅ **preflight PASS (caveats)** — §2.3 D방식으로 해소. 다음 = Phase 1/2 빌드(미구현).

| # | 항목 | 상태 | 근거 |
|---|------|------|------|
| 2.1 | Git egress (remote+push) | ✅ PASS | mrgrit/bastion push 가능(heartbeat 검증). **⚠️ 보안: remote URL 에 GitHub PAT 평문 노출 — 즉시 revoke/회전 필요** |
| 2.2 | 모델 서빙 120/20/8 | ✅ PASS | 0.109(GB10, ollama 0.30) 에 gpt-oss:120b·20b, qwen3:8b·ministral-3:8b 가용. 4c 규모곡선 가능 |
| 2.3 | el34 클린리셋(롤백) | ✅ **PASS (D방식, 편차 문서화)** | full VM/LVM snapshot 대신 **타깃 상태-리셋**(`harness/eval_reset.sh`): 타깃 ephemeral(--rm) + SIEM 타임윈도우 + M3 차단룰은 fw `inet eval_reset` 전용테이블→리셋시 삭제(production NAT 무손상) + E.G seed reset. **왕복검증 ROUNDTRIP_PASS**(added=1→reset=0, nat 보존, attacker→web 200 유지). literal snapshot 아님(Runbook §0 편차 기록). host LVM·거대볼륨 미접촉(리스크 회피) |
| 2.4 | 도구 | △ PARTIAL | auditd ✅(독립오라클 가능), Wazuh ✅(analysisd up), python ✅, git ✅ / **bpftrace(eBPF) MISSING**(auditd로 대체) / secret-scan = push-전 ghp_ 패턴 grep 적용중 |
| 2.5 | 비밀정보 경로 | △ | .gitignore 작성(시크릿 패턴). push-전 secret-scan(ghp_) 적용. **⚠️ PAT 노출(2.1) revoke 필요** |

## 핵심 컴포넌트 가용성 (실행 가능 여부)
| 컴포넌트 | 상태 | 비고 |
|----------|------|------|
| 논문 4장 정의(RQ1–4, 4.7) | ✅ 존재 | ccc/contents/papers/experience-graph/{05-evaluation-protocol,07-evaluation-harness,09-test-plan}.md |
| 7조건 공용 하니스(메모리 교체형) | ❌ 미구현 | Phase 1 |
| Phase 2 베이스라인 7종 (Reflexion/ExpeL/AWM/A-MEM/RAG …) | ❌ **미구현** | 논문 .md 설명만, 코드 없음 — RQ1 핵심 비교 불가 |
| ablation 토글(off/playbook/experience/full + 구성요소제거) | ❌ 미구현 | Phase 1 |
| 독립 오라클 배선(auditd→ground truth, SUT 분리) | ❌ 미구현 | auditd 바이너리는 존재 |
| 3090 커리큘럼 runnable 랩 | △ 부분 | standalone 248 yaml + holdout-462/holdout-el34 = **스펙 YAML**. 7조건 runnable 미검증 → §3 BLOCKED |
| 외부 CTF 3종(Cybench/NYU/InterCode) | △ | bench_data 에 데이터 있음(secu_agent_benchmark), 비격리 경로 필요(§9) |
| bastion full(ablation `full` 1조건) | ✅ 부분 측정됨 | 별도 작업에서 방어탐지 웹71(120b 66%) + 공격축 225/323 실측 — RQ4/RQ1-full 일부에 해당 |

## 결론
**preflight 게이트 통과** (§2.3 D방식 해소, 2026-06-11). 그러나 논문 4장 **전체 실행은 여전히 미구현 컴포넌트 빌드 필요**(수 주, 다회 세션) — preflight 항목이 아니라 Phase 1/2/3 구현:
1. ✅ ~~el34 클린리셋~~ → D방식 완료(`harness/eval_reset.sh`)
2. ❌ 7조건 메모리-교체형 공용 하니스 + ablation 토글 (Phase 1)
3. ❌ 베이스라인 6종 충실 이식 + sanity (Phase 2, 최대 리스크)
4. ❌ auditd 독립 오라클 배선 (Phase 1) — auditd 바이너리는 존재
5. △ 3090 커리큘럼 + L1/L2 + el34 60-suite runnable화 (Phase 3) — 스펙 YAML 존재

과학적 무결성(§1)상 미구현을 반쪽 빌드로 "완료" 위장하지 않는다. preflight PASS 이므로 HARD-STOP 해제,
**Phase 1 빌드 진입 가능**. 유지관리자 결정: (a) 빌드 우선순위(Phase1 하니스 → Phase2 베이스라인 1종씩)
(b) PAT revoke + 새 토큰 (c) §9 온라인(상용·외부CTF) in-scope 여부.
