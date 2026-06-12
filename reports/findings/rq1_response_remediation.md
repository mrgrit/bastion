# Finding — RQ1 응답/remediation 측정 (탐지 saturation 회피)

작성: 2026-06-12 · 평가 repo: mrgrit/bastion · 대상: bastion @ 6v6(0.105)

## 0. 동기

탐지축은 saturate(통합 SIEM + 강한 base)라 EG 변별 불가([[ablation_egmode_plumbing_fix]]).
RQ1(EG 가 bastion 성능을 올리나)을 **응답/remediation** 으로 측정 — 환경특이 절차·과거경험이 필요해
EG 가치(KG-2 Reuse)가 드러날 여지가 큰 축.

## 1. 설계 — 객관 상태변화 오라클 (에이전트 주장과 독립)

**Task `resp-block-ip-01`**: SQLi 공격(출처 .202)을 SOC 가 기록 → 에이전트가 (1) 출처 IP 식별
(2) fw 에서 차단 (3) 실제 트래픽으로 차단 검증.

**오라클 = 상태변화 (말이 아닌 사실)**:
- `pre_reach` (차단 전 공격자→web HTTP) = 302(도달) — precondition.
- `post_reach` (에이전트 작업 후) = 000/timeout 이면 실효 차단.
- `ctrl_post` (control=bastion→web) = 302 유지 → 무차별 차단 아님(collateral 없음).
- **remediated = (post 차단) AND (control 무피해)**. 룰을 "놓았다"는 보상 안 함 — 트래픽이 실제 끊겨야 인정.

**안전 리셋(검증됨, roundtrip)**: production 외 nft 테이블 제거 + `inet six_filter` 체인의 공격IP 룰
handle 삭제 + conntrack flush → 공격자 도달성 복구로 검증(`net_reset_restored`). production
(`ip nat`/`inet six_filter`/`ip six_nat`) 무손상. 전 런 `net_reset_restored=True` 확인.

**6v6 차단점(실측 규명)**: web 은 **haproxy 가 fw 의 10.20.30.1:80 에서 종단** → 공격자→.1 은 fw 의
`inet six_filter input` 으로 들어옴. ∴ 실효 차단 = `nft add rule inet six_filter input ip saddr <IP> drop`.
`forward`/`daddr` 는 무효(haproxy 가 새 백엔드 연결을 맺으므로 .202→web 단일 패킷이 forward 에 없음; 실측 counter=0).

## 2. 발견한 bastion 버그 수정 (confound 제거)

`configure_nftables` 스킬이 **6v6 에서 작동 불능** — `vm_ips["secu"]` 호스트에서 `sudo nft` 실행 →
"nft: command not found"(6v6 방화벽은 6v6-fw **컨테이너 내부**에 nft 보유). `scan_ports` 처럼
**bastion 의 docker 로 `docker exec 6v6-fw nft …`** 실행하도록 수정. (ccc+bastion 양 repo, 컨테이너 배포.)
→ 에이전트 실패가 "깨진 도구"가 아니라 **지식/적용** 을 반영하게 됨.

## 3. 결과

### 3.1 기본 frozen KG (recipe 미보유) — pilot
off/full 모두 **REMEDIATED=False**. off 는 `six_filter forward` 에 차단(무효), full 은
`saddr .202 daddr .32.80`(haproxy 구조상 존재 않는 패킷) — 둘 다 haproxy-input 지식 부재로 floor.
→ 이 trained KG 에는 정확한 차단 recipe 가 없음. **base/cold-EG 는 이 6v6 특이 remediation 을 못 함.**

### 3.2 recipe 를 EG 에 encode 후 (KG-2 Reuse 검정)

KG-1 Encode: 검증된 차단 절차를 anchor 로 기록(실제 `/history/anchors` API) — "과거 동일 incident 를
이 방법으로 해결" 시뮬레이션. label=`task:`+미션[:80] 로 retrieval 매칭. frozen 재스냅샷(204, recipe 포함).
**검색 검증**: experience-mode build 가 recipe anchor 검색 성공(서버 경로, kg_used=True hits=1).
(주의: `-u ccc` standalone python 은 readonly-db 로 HistoryLayer init 실패 → 검증은 서버 경로로.)

**4조건 × 5rep (frozen=204 w/recipe)**:

| 조건 | remediated(실효차단) | 룰배치 | recipe검색(kg_used) | 성공 시 체인 |
|------|---------------------|--------|---------------------|--------------|
| **bastion-off (No-EG)** | **0/5** | 3/5 | 0/5 | — (전부 forward=무효) |
| bastion-playbook | 2/5 | 4/5 | 0/5 | six_filter **input** |
| bastion-experience | 2/5 | 5/5 | **5/5** | six_filter **input** |
| bastion-full | 2/5 | 5/5 | **5/5** | six_filter **input** |

oracle_fired(공격 ground truth) 20/20 · 실효차단 6/20(전부 `inet six_filter input`) · 안전리셋 20/20.

**해석**:
- **off=0/5 vs EG 조건=2/5** — 탐지축(off=만점 saturation)과 **대조적으로 응답축은 방향성 있는 EG 이득**.
  No-EG 는 5회 모두 forward(무효 체인)에 차단 → 한 번도 실효 못 냄. EG 조건은 일부 reps 에서 정답
  체인(input)을 찾아 실효 차단.
- **retrieval ≠ application**: experience/full 은 recipe anchor 를 **매번 검색(kg_used 5/5 = KG-2 Reuse
  retrieval 성립)** 했으나 remediated 는 2/5 로 recipe 미보유 playbook(0/5 검색)과 동률. 즉 정밀 recipe
  검색이 성공률을 추가로 끌어올리지 못함 — 병목은 검색이 아니라 **검색된 절차의 충실한 적용**(에이전트가
  forward prior 로 input 지침을 덮어씀, §3.2 pilot 로그에서 직접 확인).
- **n=5 한계**: off=0 vs EG=2 는 방향성은 명확하나 통계적 강도는 약함 — 다회 reps 로 강화 필요.

**pilot(×1) 관찰**: off/playbook `kg_used=False`(recipe 미검색). **experience/full `kg_used=True hits=1`
(recipe 검색 성공 = KG-2 Reuse retrieval 작동)**. 그러나 full 은 recipe("forward 아니라 input")를
받고도 최종보고에 "입력 체인이 아닌 **forward 체인에**" 차단 — **검색된 경험을 충실히 적용하지 않음**.
→ remediated=False.

## 4. 핵심 통찰 — retrieval ≠ application

응답축의 병목은 **지식 검색이 아니라 충실한 적용**이다:
- EG retrieval 은 작동(experience/full 이 정확한 recipe anchor 를 검색). = KG-2 Reuse 의 검색 단계 성립.
- 그러나 에이전트는 검색된 절차를 **LLM prior 가 덮어써** 무효 지점(forward)에 적용 → 객관 오라클상 실패.
- 객관 상태변화 오라클이 이를 정확히 포착(룰 존재해도 트래픽 안 끊기면 불합격) = 측정 무결성 확보.

**함의**: RQ1 응답축에서 EG 의 retrieval 기여는 실증되나, end-to-end 성공은 **적용 충실도**(검색 경험을
prior 보다 우선해 실행)에 의해 제약된다. 개선 방향: (a) configure_nftables 가 6v6 표준 차단점(input)을
기본값으로, (b) 에이전트 prompt 가 "검색된 검증 절차가 있으면 그대로 실행 후 트래픽 검증" 강제,
(c) 적용 실패→자가수정(KG-3 Adapt) 루프.

## 5. 산출물
- `harness/run_eval.py` — kind=response flow, 객관 오라클(reach 토글), 안전 surgical reset, grade_response.
- `bastion/skills.py`(ccc+bastion) — configure_nftables → docker exec 6v6-fw 수정.
- `results/runs/<id>.json` — 런별 감사(precondition_reach/post/ctrl/nft_present/net_reset_restored).
- recipe anchor(anc-…) — KG-1 Encode 실증.
