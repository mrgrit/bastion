# F6 — 읽기전용 점검이 `shell` 승인게이트에 막혀 미완 (bastion 개선점)

- 발견: calib001 attempt#1 (2026-07-10)
- 심각도: **중** (읽기전용 실습/채점 과제의 완수율을 직접 저해)
- 상태: OPEN → attempt#2 에서 튜닝 시연 예정

## 증상
무힌트 과제 "el34-web WAF·Apache 상태 점검"에서 bastion 은:
- WAF: `check_modsecurity`(읽기전용) 실행 → `SecRuleEngine On` 정확 확인 ✓
- Apache: 상태 확인을 **`shell` 스킬로 5회 시도 → 전부 `skill_skip reason:denied`** (auto_approve=false).
- 결과: Apache 가동 여부 "판단 불가" 로 보고 → 과제 **FAIL(1/2)**.

## 근본 원인
- bastion 플래너가 순수 **읽기전용**(프로세스/포트/서비스 up) 확인을 원자 read-only 스킬이 아니라
  범용 **`shell`**(위험/`requires_approval` 분류)로 라우팅.
- `auto_approve=false`(읽기전용 모드)에서 승인게이트가 shell 을 일괄 차단 → 부작용 없는 조회까지 막힘.
- bastion 이 억측하지 않고 "판단불가"로 정직 보고한 것은 **정상**(BASTION.md "추정과 단정 구분"). 결함은 게이트/라우팅.

## 개선안 (teach-until-pass — 정답 비주입)
- **A. 라우팅 교정(하네스/E.G)**: "웹 서비스 가동 점검" → 읽기전용 recon 스킬(`scan_ports`/`probe_host`/`web_scan`)로
  유도(experience/playbook). shell 불필요 → auto_approve=false 에서도 완수. (F3 playbooks=0 도 함께 해소 가능)
- **B. 게이트 정교화(코드 개선)**: read-only shell(ss/pgrep/systemctl status 등 비변경 명령)은 `auto_approve=false`
  에서도 허용하도록 위험분류 세분화. 일반적 읽기전용 완수율 상승 = 근본적.

## 대조 정답 (Assessor)
- `port_listening web 80` = PASS (apache2 pid 687), `file_contains web modsecurity.conf "SecRuleEngine On"` = PASS.
- 즉 Apache 는 실제 가동중 → bastion 이 확인만 했으면 PASS 였음.
