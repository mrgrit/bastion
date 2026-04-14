# Bastion AI 에이전트 프롬프트 작성 가이드

> Bastion은 자연어 프롬프트 하나로 보안 운영 작업을 자동 수행하는 AI 에이전트입니다.
> 이 가이드는 Bastion이 올바르게 작업을 수행하도록 프롬프트를 작성하는 원칙을 설명합니다.

---

## 1. 핵심 원칙

### 원칙 1: "실행해줘"로 끝내라
Bastion은 **실행 에이전트**입니다. "설명해줘", "알려줘" 같은 표현을 쓰면 직접 답변(Q&A)으로 빠집니다.

| 잘못된 프롬프트 | 올바른 프롬프트 |
|---------------|---------------|
| "nftables 규칙 설명해줘" | "secu VM에서 nftables 규칙을 확인해줘" |
| "SQL Injection 구현 방법을 보여줘" | "attacker에서 curl로 SQL Injection을 테스트해줘" |
| "감사 정책 예시를 알려줘" | "secu VM에서 auditd 감사 규칙을 추가해줘" |

### 원칙 2: 대상 VM을 명시하라
Bastion은 여러 VM에 명령을 보낼 수 있습니다. 대상이 불명확하면 잘못된 VM으로 라우팅됩니다.

| VM | 역할 | 프롬프트 예시 |
|----|------|-------------|
| **attacker** | 공격 도구 실행 | "attacker에서 nmap으로 스캔해줘" |
| **secu** | 방화벽/IDS | "secu VM에서 Suricata 상태 확인해줘" |
| **web** | 웹 서버 | "web VM에서 Docker 컨테이너 확인해줘" |
| **siem** | SIEM/로그 | "siem VM에서 Wazuh 알림 조회해줘" |
| **manager** | AI/관리 | "manager VM에서 python3 스크립트 실행해줘" |

### 원칙 3: 구체적인 도구/명령을 언급하라
추상적인 요청보다 도구명을 포함하면 Bastion이 정확한 스킬을 선택합니다.

| 추상적 (낮은 성공률) | 구체적 (높은 성공률) |
|---------------------|---------------------|
| "포트 확인해줘" | "nmap으로 10.20.30.80 포트 스캔해줘" |
| "웹 취약점 찾아줘" | "nikto로 10.20.30.80:3000 스캔해줘" |
| "비밀번호 정책 설정해줘" | "secu에서 chage -M 90 user1 명령으로 비밀번호 만료 설정해줘" |

### 원칙 4: 한 번에 하나의 작업을 요청하라
복잡한 작업은 단계별로 나누어 요청합니다. 다만, 관련 작업 3~5개는 번호 매기기로 묶을 수 있습니다.

**단일 작업:**
```
attacker에서 nmap -sV 10.20.30.80 실행해줘
```

**복합 작업 (3~5개):**
```
다음 작업들을 순서대로 수행해줘:
1) attacker에서 ping -c 3 10.20.30.80 실행
2) nmap으로 포트 스캔
3) curl로 HTTP 헤더 확인
```

---

## 2. Bastion의 작동 방식

Bastion은 3단계로 작업합니다:

```
프롬프트 입력
  → [Planning] 어떤 스킬/Playbook을 사용할지 결정
  → [Executing] SubAgent를 통해 대상 VM에서 명령 실행
  → [Validating] LLM으로 결과를 분석하고 보고
```

### 사용 가능한 스킬

| 스킬 | 기능 | 트리거 키워드 |
|------|------|-------------|
| `probe_host` | VM 상태 확인 | "상태", "uptime", "디스크" |
| `scan_ports` | nmap 포트 스캔 | "nmap", "포트 스캔", "스캔" |
| `check_suricata` | IDS 알림 확인 | "suricata", "IDS", "알림" |
| `check_wazuh` | SIEM 상태 | "wazuh", "SIEM", "에이전트" |
| `check_modsecurity` | WAF 상태 | "modsecurity", "WAF", "차단" |
| `configure_nftables` | 방화벽 규칙 | "nftables", "방화벽", "룰" |
| `analyze_logs` | 로그 분석 | "로그", "분석", "auth.log" |
| `deploy_rule` | 규칙 배포 | "규칙 배포", "룰 추가" |
| `web_scan` | 웹 스캔 | "nikto", "웹 스캔", "취약점" |
| `shell` | 임의 명령 실행 | 위에 해당 안 되는 구체적 명령 |
| `probe_all` | 전체 점검 | "전체", "인프라", "종합" |

### Planning 우선순위

1. **Playbook 매칭**: 등록된 Playbook과 일치하면 Playbook 실행
2. **스킬 매칭**: 키워드/도구명으로 적절한 스킬 선택
3. **Dynamic Playbook**: 스킬 조합으로 동적 계획 생성
4. **Q&A 폴백**: 어떤 스킬에도 매칭 안 되면 텍스트 답변 (이것을 피해야 함!)

---

## 3. 도메인별 프롬프트 패턴

### 공격 (Offensive)
```
attacker에서 nmap -sV -p 1-1000 10.20.30.80 실행해줘
attacker에서 hydra -l admin -P /tmp/pass.txt ssh://10.20.30.80 실행해줘
attacker에서 curl -s 'http://10.20.30.80:3000/rest/products/search?q=%27' 실행해줘
```

### 방어 (Defensive)
```
secu VM에서 nftables 규칙 조회해줘
secu VM에서 Suricata 최근 알림 확인해줘
web VM에서 ModSecurity 차단 로그 확인해줘
```

### SIEM/SOC
```
siem VM에서 Wazuh 에이전트 목록 확인해줘
siem VM에서 최근 알림 상위 10개 조회해줘
siem VM에서 grep으로 alerts.log에서 Failed password 검색해줘
```

### 컨테이너 보안
```
web VM에서 docker ps로 실행 중인 컨테이너 확인해줘
web VM에서 docker inspect juiceshop의 보안 설정 확인해줘
```

### AI 보안
```
manager VM에서 python3으로 Ollama API에 프롬프트 인젝션 테스트해줘
manager VM에서 curl로 http://10.20.30.200:11434/api/chat 에 요청 보내줘
manager VM에서 python3으로 PII 탐지 스크립트 실행해줘
```

---

## 4. 자주 하는 실수

### 실수 1: "설명해줘" / "알려줘"
Bastion은 설명 봇이 아닙니다. 실행을 요청하세요.
```
✗ "SQL Injection이 뭔지 설명해줘"
✓ "attacker에서 curl로 JuiceShop에 SQL Injection 테스트해줘"
```

### 실수 2: 대상 VM 미지정
```
✗ "포트 스캔해줘"
✓ "attacker에서 10.20.30.80 포트 스캔해줘"
```

### 실수 3: 너무 추상적
```
✗ "보안 설정해줘"
✓ "secu VM에서 SSH PermitRootLogin을 no로 설정해줘"
```

### 실수 4: 보고서/코드 작성 요청
```
✗ "보고서를 작성해줘"
✓ "attacker에서 수집한 정보를 /tmp/report.txt에 저장해줘"
```

---

## 5. 성공률을 높이는 팁

1. **IP 주소를 명시하라**: `10.20.30.80` 대신 `web(10.20.30.80)`으로 역할도 함께
2. **타임아웃 고려**: nmap 전체 스캔은 시간이 오래 걸림 → `-F`(빠른 스캔) 옵션 추가
3. **sudo 필요 시 명시**: "sudo nmap -sS" → Bastion이 SubAgent에 sudo 전달
4. **결과 저장**: "결과를 /tmp/xxx.txt에 저장해줘" → 후속 분석에 활용 가능
5. **복합 작업은 5개 이하**: 너무 많으면 Bastion이 일부를 건너뛸 수 있음
