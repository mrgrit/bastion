# Bastion — CCC 보안 운영 에이전트

> 자연어로 사이버보안 인프라를 운영하는 AI 에이전트

학생이 자기 인프라(secu/web/siem/attacker)에서 자연어로 보안 작업을 수행.
LLM(gpt-oss:120b)이 Skill/Playbook을 선택하고 SubAgent A2A로 실행.

## Quick Start

```bash
git clone https://github.com/mrgrit/bastion.git /opt/bastion
cd /opt/bastion
bash setup.sh
vi .env  # LLM 서버 + VM IP 설정
./bastion.sh
```

## 구조

```
bastion/          — 에이전트 코어
  agent.py        — LLM + Skill 디스패치
  skills.py       — 11개 Skill 레지스트리
  playbook.py     — YAML Playbook 엔진
  prompt.py       — 시스템 프롬프트
  __init__.py     — SSH, A2A, 온보딩
main.py           — Rich TUI
contents/playbooks/ — YAML Playbook
```

## Skills

probe_host, probe_all, scan_ports, check_suricata, check_wazuh,
check_modsecurity, configure_nftables, analyze_logs, deploy_rule,
web_scan, shell

## TUI 명령어

/skills, /playbooks, /evidence, /quit
