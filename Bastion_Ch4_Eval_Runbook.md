# Bastion 4장(평가) 자동 실행 Runbook — Claude Code 지시서

> 저장소 루트의 권위 있는 운영 명세. 논문 4장(Experience Graph 평가)을 실험 설계의 단일 출처로 삼는다.
> 실행: "Read and execute `Bastion_Ch4_Eval_Runbook.md` to completion. Follow it literally."

## 0. 역할과 목표
Claude Code는 Bastion 평가 호스트에서 동작한다. 목표는 논문 4장을 끝까지 자율 실행하고, 진행 상황을
사람이 기계에 접속하지 않고도 GitHub에서 실시간 확인하도록 보고서를 지속 push 하는 것이다.
논문 4장 + `bastion_Readme`, `6v6_Readme`를 먼저 읽고 RQ1–RQ4 + 안전성(4.7) 정의를 그대로 따른다.
Runbook과 논문이 충돌하면 논문 우선, 그 사실을 보고서에 기록.

## 1. 운영 원칙
- 자율성: 확인 요청 없이 진행. 결정은 기본값 채택 + 로그. 사람 호출은 §7 HARD-STOP 뿐.
- 과학적 무결성(절대): 결과를 지어내거나 추정 금지. 모든 수치는 커밋된 산출물로 추적 가능. 실패/미완은
  FAILED/PARTIAL 로 오류와 함께 보고 — 조용히 건너뛰거나 값 생성 금지.
- 재개 가능성: `state/ledger.json` 유지. 모든 작업 단위 idempotent·체크포인트. 재시작 시 미완부터.
- 재현성: 시드 고정, 설정 스냅샷, 환경(모델 버전·이미지 digest·git SHA) 매 실행 기록.
- 폭발 반경: 공격적 행위는 격리 6v6 내부에서만. C_destr 자동 재사용 배제.
- 안전장치 불가침: 위험도평가·승인정책·C_destr 끄지 않는다. 꺼야만 되는 작업은 HARD-STOP.
- 독립 오라클 분리: 기록 완전성 계측(auditd/eBPF)은 SUT 와 별개 프로세스.

## 2. Preflight (누락 시 HARD-STOP)
1. Git egress: remote + push 권한, 시작 heartbeat push 검증.
2. 모델 서빙: 120B 도달. 20B/8B 선택(없으면 4c-scale PARTIAL).
3. 6v6 레인지: IaC + 클린 스냅샷 생성 + 롤백 왕복 1회 검증.
4. 도구: 에이전트 런타임, auditd/eBPF, SIEM(Wazuh), 채점기, python, git, secret-scan.
5. 비밀정보 경로: .gitignore + push 전 secret-scan.

## 3. 파라미터 (config/params.yaml override)
N_long_session=30, n_repeats=5, k_tamper=50, events L1=40/L2=30, suite_6v6=60,
categories=[관제_트리아지,취약점_점검,로그분석_침해대응,보안시스템_운영,컴플라이언스],
model_scales=[120B,20B,8B], stats=wilcoxon/bootstrap95/cliffs_delta/holm,
reset_store_each_condition=true, seed=20260607.

## 4. 단계
- Phase 0 Bootstrap: 레이아웃, 논문 파싱, params 확정, ledger 초기화, preflight.
- Phase 1 하니스&계측: 7조건 공용 하니스(120B·33Skill·6v6 고정, 메모리만 교체), ablation 토글
  (off/playbook-only/experience-only/full + 구성요소 개별제거), 독립 오라클(auditd/eBPF), IaC 스냅샷/롤백.
- Phase 2 베이스라인: ①vanilla ReAct ②요약압축 ③Reflexion ④ExpeL ⑤AWM ⑥A-MEM ⑦평면 RAG (충실 이식+sanity),
  3090 커리큘럼 자기메모리 적재 어댑터, 참조상한(상용 클라우드 bare ReAct).
- Phase 3 데이터셋: 3090 커리큘럼 runnable, L1/L2 사건, 6v6 마스터 suite(5범주×난이도, 4요소+루브릭),
  외부 CTF 3종(Cybench/NYU/InterCode), 인출/재사용 동일 인터페이스.
- Phase 4 측정·채점: PC(식8), 학습곡선, 재사용률, 결정성, 해시체인+변조탐지(식7), SIEM 일치율,
  텔레메트리(지연/토큰/GPU), CTF↔6v6 상관, 채점신뢰도, 안전성 3지표(4.7).
- Phase 5 스모크(게이트): N=2,n=1,범주당1,k=3 전조건 E2E 1회. 배관만 검증.
- Phase 6 사전학습: 3090 커리큘럼 메모리조건 적재(idempotent).
- Phase 7 평가: RQ1(1a/1b/1c/ablation) RQ2(2a/2b/2c/L2) RQ3(3a/3b/3c/3d) RQ4(4a/4b/4c) + 안전성.
- Phase 8 분석: 집계→통계→그림/표→최종보고서→릴리스. REPORT.md 100%.

## 5. GitHub 보고 — REPORT.md 단일 출처. 매 단계/RQ블록/실패/30분 heartbeat push.
## 6. 실행별 감사 레코드 /results/runs/<run_id>.json — 모든 표는 이것으로만 계산.
## 7. HARD-STOP: preflight 누락 / 복구불가 인프라 / 안전장치 OFF 요구 / 무효화 모호성.
## 8. DoD: RQ1–4 + 안전성 각각 (완료 실행) or (정당화된 FAILED/SKIPPED/BLOCKED), 보고서 컴파일, REPORT 100%.
## 9. 폐쇄망 vs 온라인: 참조상한(상용)·외부 CTF 는 비격리 별도 경로. 불가시 BLOCKED 명시.
## 10. 유지관리자 입력: REPO_URL+push 자격, bastion/6v6 IaC/모델 경로, params 검토, §9 온라인 가용.
