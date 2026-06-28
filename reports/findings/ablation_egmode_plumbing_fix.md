# Finding — EG ablation plumbing 버그 + 유효 재측정 (RQ1 detection)

작성: 2026-06-11 · 평가 repo: mrgrit/bastion · 대상: bastion @ el34(0.105)

## 0. 요약 (TL;DR)

1. **치명적 plumbing 버그 발견·수정**: 배포 컨테이너의 `apps/bastion/api.py` 가 구버전이라
   요청의 `eg_mode` 를 파싱만 하고 `agent._eg_mode` 로 **전달하지 않았다**. → 모든 chat 이
   `_eg_mode` 기본값 `"full"` 로 실행. **그 이전의 모든 ablation(off/playbook/experience/full)
   은 사실상 전부 `full` 단일 조건이었다.** (이전 "cold-KG 해소·full hits=3 검증" 도 full=기본값이라
   trivially 통과했을 뿐 ablation 신호가 아님 — 무효.)
2. **수정**: 현 `api.py` 재배포(md5 일치) + restart → `eg_mode` 토글 **실증**:
   off=`kg_used=false/hits=0/skip=eg_mode_off`, full=`kg_used=true/hits=8`.
3. **격리 강화**: trained-KG 를 frozen 스냅샷으로 고정하고 **매 런 복원+restart** → 기록에 의한
   DB 성장·캐시 캐리오버 confound 제거(live anchors 20런 내내 203 유지).
4. **유효 det-sqli ablation(4조건×5rep)**: off(진짜 No-EG) **5/5 탐지** = **task saturation**.
   EG 가 탐지 이득을 주지 못함(base 120b 이 단독으로 해결). playbook-only 만 4/5 로 소폭 하락.
5. **아키텍처 결론**: el34 **Wazuh 가 Suricata eve.json 을 ingest**(rule 86601). 즉 Wazuh 가
   전 센서 상위집합 → check_wazuh 단일 호출로 ground truth 노출 → **탐지축은 공격유형 무관 saturate**,
   EG 탐지 이득 분리 불가. (EG 의 실증된 가치는 탐지가 아니라 **대응/remediation = KG-2 Reuse**, P24 266/266.)

## 1. 근본 원인 (왜 이전 ablation 이 전부 무효였나)

| 레이어 | 상태(수정 전) | 근거 |
|--------|--------------|------|
| `ChatRequest.eg_mode` (api.py) | ✅ 파싱됨 (default "full") | line 263 |
| `agent._eg_mode` 할당 | ❌ **배포본에 라인 부재** | 컨테이너 api.py grep=∅, md5 불일치 |
| `agent.py` off/playbook/experience 처리 | ✅ 존재(배포됨) | 1254, 2613, kg_context 213-216 |

agent.py·kg_context.py 는 eg_mode 를 처리할 준비가 돼 있었으나, **그것을 세팅해 줄 api.py 한 줄
(`agent._eg_mode = (req.eg_mode or "full").lower()`, line 1122) 이 배포본에 없어** 요청값이 버려졌다.
→ 항상 default `full`. 직전 무효 ablation 16런이 모두 `kg_used=true, hits=7~8` (off 포함) 로 나온 것이
스모킹건이었다.

**수정**: `apps/bastion/api.py` (eg_mode 배선 포함, 이미 CCC 본체에 commit 돼 있던 버전) 를
컨테이너에 docker cp + `docker restart` (recreate 아님 — docker cp 된 agent.py/kg_context.py 보존).
백업: 컨테이너 내 `api.py.bak_pre_egmode`.

### 실증 (수정 후 토글)
```
off : kg_used=false hits=0 skip_reason=eg_mode_off lookup=skipped_eg_mode record=false
full: kg_used=true  hits=8 skip_reason=""           lookup=new            record=true
```

## 2. 측정 무결성 장치 (harness §2.3 frozen-snapshot 충실 구현)

- **frozen trained-KG**: `bastion_graph.db`(graph+history 통합, 203 anchors) 를 0.105 호스트에
  스냅샷(`/tmp/frozen_graph.db`).
- **매 런 복원+restart**(`restore_restart()`): docker cp frozen→컨테이너 + `-wal/-shm` 제거(WAL 모드) +
  `docker restart` + `/health` polling. → 모든 (event×condition×rep) 가 **동일 frozen KG** 조회.
- **격리 증거**: 기록 조건(playbook/experience/full, kg_recorded=true)이 15런 돌았는데도
  live anchors 가 203 유지 = 자기참조 오염 0.
- **독립 오라클**: SUT(bastion)와 분리된 SOC. event 별 소스 지정 — wazuh(alerts.json 줄윈도우) /
  suricata(eve.json 바이트윈도우, 6GB+). auditd=BLOCKED(CAP_AUDIT 부재).

## 3. 유효 결과 — det-sqli-01 (RQ1 detection, 4조건×5rep, frozen)

| 조건 | 탐지 | 완전식별(유형+출처+센서근거) | kg_used | hits평균 | 기록 |
|------|------|------------------------------|---------|----------|------|
| **bastion-off (No-EG)** | **5/5** | **5/5** | 0/5 | 0.0 | 0/5 |
| bastion-playbook | 4/5 | 3/5 | 5/5 | 3.0 | 5/5 |
| bastion-experience | 5/5 | 5/5 | 5/5 | 5.0 | 5/5 |
| bastion-full | 5/5 | 5/5 | 5/5 | 8.0 | 5/5 |

- 독립 오라클(Wazuh 100251 web_attack) **20/20 발화** — 매 inject 가 실제 공격으로 기록됨.
- **해석**: off(메모리 0)가 이미 5/5 완전식별 → **task saturation**. base 120b 가 단일 Wazuh
  조회로 SQLi·출처·MITRE 를 정확히 보고. EG(playbook/experience/full)는 탐지율을 더 못 올림
  (천장). playbook-only 4/5(완전 3/5) 소폭 하락은 anchor(증거) 없는 playbook 단독 context 의
  경미한 distraction 또는 n=5 변동.
- ⚠️ **이전 phase1.md 의 E2E 표(off 실패/rest 성공)는 무효** — 그땐 전 조건이 full 이었고 cold-KG 였음.

## 4. 아키텍처 발견 — 왜 탐지축은 EG 변별이 안 되나

변별 가설: "Suricata 에만 잡히고 Wazuh 는 못 보는 공격(nmap recon) + 센서 미지정 mission →
base 는 Wazuh 만 보고 실패, EG(asset/playbook=Suricata 보라)만 성공" 으로 EG 이득을 분리하려 함.

실측으로 가설 **기각**:
- el34 토폴로지: Suricata(el34-ips)는 eth0=DMZ(10.20.32)/eth1=internal(10.20.31) 만 탭. ext↔fw 는 시야 밖.
  → nmap 은 **DMZ 호스트(.32.80) 대상**이어야 ips 경유해 발화(1000005, src .202 보존). ENTRY(.1) 는 미발화.
- **결정적**: 그 Suricata alert 가 **Wazuh 에 rule 86601("Suricata: Alert - EL34 nmap SYN scan")
  로 그대로 ingest** 됨. = Wazuh 가 native 룰 + Suricata alert 를 합치는 **상위집합 SIEM**.
- ∴ "Wazuh-blind" 공격이 사실상 없음. check_wazuh 단일 호출이 전 센서 ground truth 노출.
  강한 base 모델 + 통합 SIEM ⇒ **탐지축은 공격유형 무관 saturate. EG 탐지 이득은 분리 불가.**

### recon 실증 확인 (det-recon-suricata-01, 4조건×3rep, frozen)
inject = attacker(.202) → DMZ web(.32.80) nmap -sS (ips 경유, Suricata 1000005 발화, src .202 보존).
mission = **센서 미지정 open-ended**("어떤 센서를 봐야 하는지는 네가 판단하라").

| 조건 | 탐지 | 완전식별 | kg_used | hits |
|------|------|----------|---------|------|
| bastion-off (No-EG) | 3/3 | 3/3 | 0/3 | 0.0 |
| bastion-playbook | 3/3 | 3/3 | 0/3 | 0.0 |
| bastion-experience | 3/3 | 3/3 | 3/3 | 1.0 |
| bastion-full | 3/3 | 3/3 | 3/3 | 1.0 |

독립오라클(Suricata 1000005) **12/12 발화**. **전 조건 3/3 완전식별** — off(메모리 0, 센서 미지정)도
nmap recon 을 완벽 탐지 = check_wazuh 가 rule 86601(Suricata-passthrough)을 surface 하기 때문.
**가설("base 는 Wazuh 만 보고 실패") 기각** — 통합 SIEM 이라 base 가 단일 조회로 해결.
부수관찰: 이 trained-KG(203, 주로 web/ops 경험)에는 recon 관련 playbook 이 없어 playbook hits=0,
experience/full 도 hits=1 로 낮음 → **신규 task 유형엔 EG 검색이득 자체가 미미**.

⇒ 서로 다른 두 공격유형(web SQLi=Wazuh-native 100251 / network recon=Suricata→Wazuh 86601)
모두에서 off=만점 → **탐지축 saturation 은 공격유형 무관하게 견고**.

## 5. 결론 / 다음

- **RQ1(detection)**: el34 SOC(통합 Wazuh) + 강한 base 위에서 **EG 의 탐지 이득은 측정상 0**(saturation).
  이는 EG 무용이 아니라 **탐지가 EG 가치 지점이 아님**을 의미.
- **EG 가치 지점 = 대응/remediation(KG-2 Reuse)** — 환경특이 절차(어느 fw 컨테이너·nft 문법·차단룰)는
  base 가 모르고 playbook/anchor 가 필요. P24(266/266, KG-2 Reuse 10+회)에서 이미 실증.
- **다음 측정 설계**: RQ1 신호를 보려면 (a) **응답 task**(차단/격리/복구) ablation, (b) base 가 못 푸는
  **held-out·환경특이** task(holdout-462/el34-suite) 로 전환. 단순 탐지 saturation 회피.

## 6. 산출물
- `harness/run_eval.py` — eg_mode 토글(검증) + frozen 복원/restart + 멀티센서 오라클(wazuh|suricata).
- `results/runs/<run_id>.json` — 런별 감사레코드(seed/git/model digest/oracle/metrics/kg_used/frozen).
- 배포: 컨테이너 `apps/bastion/api.py` 갱신(eg_mode 배선), 백업 `api.py.bak_pre_egmode`.
