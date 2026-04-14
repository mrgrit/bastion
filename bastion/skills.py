"""Bastion Skill 레지스트리 — 구조화된 보안 작업 단위

각 skill은 이름, 설명, 파라미터, target_vm, 실행 스크립트로 정의.
LLM이 자연어에서 skill을 선택하고 파라미터를 채운다.
실제 실행은 SubAgent A2A 프로토콜로.
"""
from __future__ import annotations
from typing import Any

from bastion import run_command, health_check, INTERNAL_IPS


# ── Skill 정의 ─────────────────────────────────

SKILLS: dict[str, dict] = {
    "probe_host": {
        "description": "호스트 상태 점검 — uptime, 디스크, 메모리, 실패 서비스 확인",
        "params": {"target": {"type": "string", "description": "대상 VM role (attacker/secu/web/siem/manager) 또는 IP", "required": True}},
        "target_vm": "auto",
    },
    "scan_ports": {
        "description": "nmap 포트 스캔 — 대상의 열린 포트와 서비스 버전 확인",
        "params": {
            "target": {"type": "string", "description": "스캔 대상 IP 또는 role", "required": True},
            "ports": {"type": "string", "description": "포트 범위 (기본: --top-ports 100)", "required": False},
        },
        "target_vm": "attacker",
    },
    "check_suricata": {
        "description": "Suricata IDS 상태 확인 + 최근 알림 조회",
        "params": {"lines": {"type": "integer", "description": "표시할 알림 수 (기본: 10)", "required": False}},
        "target_vm": "secu",
    },
    "check_wazuh": {
        "description": "Wazuh SIEM 매니저 상태 + 에이전트 목록 + 최근 알림",
        "params": {},
        "target_vm": "siem",
    },
    "check_modsecurity": {
        "description": "ModSecurity WAF 상태 + 최근 차단 로그",
        "params": {"lines": {"type": "integer", "description": "표시할 로그 수 (기본: 10)", "required": False}},
        "target_vm": "web",
    },
    "configure_nftables": {
        "description": "nftables 방화벽 룰 조회/추가/삭제",
        "params": {
            "action": {"type": "string", "enum": ["list", "add", "delete"], "description": "동작", "required": True},
            "rule": {"type": "string", "description": "추가/삭제할 룰 (예: ip saddr 1.2.3.4 drop)", "required": False},
        },
        "target_vm": "secu",
        "requires_approval": True,
    },
    "analyze_logs": {
        "description": "로그 파일을 수집하고 LLM으로 분석 — 이상 징후, 패턴, 요약",
        "params": {
            "log_source": {"type": "string", "description": "로그 경로 (예: /var/log/suricata/eve.json)", "required": True},
            "query": {"type": "string", "description": "분석 질문 (예: 최근 1시간 의심 활동 요약)", "required": True},
            "target": {"type": "string", "description": "대상 VM role", "required": True},
        },
        "target_vm": "auto",
        "uses_llm": True,
    },
    "deploy_rule": {
        "description": "Suricata 또는 Wazuh 탐지 룰 배포",
        "params": {
            "rule_type": {"type": "string", "enum": ["suricata", "wazuh"], "required": True},
            "rule_content": {"type": "string", "description": "룰 내용", "required": True},
        },
        "target_vm": "auto",
        "requires_approval": True,
    },
    "web_scan": {
        "description": "웹 취약점 스캔 — nikto 또는 curl 기반 헤더/디렉토리 점검",
        "params": {"url": {"type": "string", "description": "대상 URL", "required": True}},
        "target_vm": "attacker",
    },
    "shell": {
        "description": "임의 셸 명령 실행 — 다른 skill로 불가능한 작업 시 사용",
        "params": {
            "command": {"type": "string", "description": "실행할 명령어", "required": True},
            "target": {"type": "string", "description": "대상 VM role", "required": True},
        },
        "target_vm": "auto",
        "requires_approval": True,
    },
    "probe_all": {
        "description": "전체 인프라 상태 일괄 점검 — 모든 VM의 SubAgent 상태, 서비스, 네트워크",
        "params": {},
        "target_vm": "local",
    },
    "enroll_wazuh_agent": {
        "description": "대상 VM에 wazuh-agent를 Wazuh Manager(siem)에 등록 — 미등록 에이전트 자동 연결",
        "params": {
            "target": {"type": "string", "description": "등록할 VM role (secu/web/attacker/manager)", "required": True},
        },
        "target_vm": "siem",
        "requires_approval": True,
    },
}


# ── Skill → Ollama tools 형식 변환 ─────────────

def skills_to_ollama_tools() -> list[dict]:
    """SKILLS를 Ollama /api/chat의 tools 파라미터 형식으로 변환"""
    tools = []
    for name, skill in SKILLS.items():
        properties = {}
        required = []
        for pname, pdef in skill.get("params", {}).items():
            prop = {"type": pdef.get("type", "string")}
            if "description" in pdef:
                prop["description"] = pdef["description"]
            if "enum" in pdef:
                prop["enum"] = pdef["enum"]
            properties[pname] = prop
            if pdef.get("required"):
                required.append(pname)

        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": skill["description"],
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        })
    return tools


# ── Skill 실행 ─────────────────────────────────

def _resolve_vm_ip(target: str, vm_ips: dict[str, str]) -> str:
    """role 이름 또는 IP를 실제 IP로 변환"""
    if target in vm_ips:
        return vm_ips[target]
    # IP 형태면 그대로
    if "." in target:
        return target
    # INTERNAL_IPS에서 찾기
    return INTERNAL_IPS.get(target, target)


def preview_skill(name: str, params: dict[str, Any], vm_ips: dict[str, str]) -> dict:
    """Skill 실행 미리보기 — dry_run용. 실제 명령·대상·위험도만 반환."""
    skill = SKILLS.get(name, {})
    target_vm = skill.get("target_vm", "auto")

    # 대상 IP 결정
    target_role = ""
    target_ip = ""
    if target_vm == "local":
        target_role = "local"
        target_ip = "localhost"
    elif target_vm == "auto":
        target_role = params.get("target", "")
        target_ip = _resolve_vm_ip(target_role, vm_ips)
    else:
        target_role = target_vm
        target_ip = vm_ips.get(target_vm, INTERNAL_IPS.get(target_vm, ""))

    # Skill별 실행 커맨드 미리보기
    cmd_preview = ""
    if name == "probe_host":
        cmd_preview = "uptime && df -h / && free -h && systemctl list-units --failed"
    elif name == "scan_ports":
        ports = params.get("ports", "--top-ports 100")
        cmd_preview = f"nmap -sV {target_ip} {ports}"
    elif name == "check_suricata":
        cmd_preview = "systemctl is-active suricata && tail -N /var/log/suricata/eve.json"
    elif name == "check_wazuh":
        cmd_preview = "systemctl is-active wazuh-manager && /var/ossec/bin/agent_control -l"
    elif name == "check_modsecurity":
        cmd_preview = "grep 'ModSecurity' /var/log/apache2/error.log | tail -N"
    elif name == "configure_nftables":
        action = params.get("action", "list")
        rule = params.get("rule", "")
        cmd_preview = f"nft {action} rule inet filter input {rule}".strip()
    elif name == "analyze_logs":
        log_source = params.get("log_source", "/var/log/syslog")
        cmd_preview = f"tail -50 {log_source} → LLM 분석"
    elif name == "deploy_rule":
        rule_type = params.get("rule_type", "suricata")
        cmd_preview = f"룰 추가 → {rule_type} reload"
    elif name == "web_scan":
        url = params.get("url", "")
        cmd_preview = f"curl -sI {url} && nikto -h {url}"
    elif name == "shell":
        cmd_preview = params.get("command", "")
    elif name == "probe_all":
        cmd_preview = "uptime (전체 VM)"

    risk = "HIGH" if skill.get("requires_approval") or name in {"configure_nftables", "deploy_rule", "shell"} \
        else "MEDIUM" if name in {"scan_ports", "web_scan"} else "LOW"

    return {
        "skill": name,
        "description": skill.get("description", ""),
        "target_role": target_role,
        "target_ip": target_ip,
        "command": cmd_preview,
        "params": params,
        "risk": risk,
    }


def execute_skill(name: str, params: dict[str, Any], vm_ips: dict[str, str],
                  ollama_url: str = "", model: str = "") -> dict:
    """Skill 실행 — SubAgent A2A로 명령 전달"""
    skill = SKILLS.get(name)
    if not skill:
        return {"success": False, "error": f"Unknown skill: {name}"}

    target_vm = skill.get("target_vm", "auto")

    if name == "probe_host":
        target = params.get("target", "attacker")
        ip = _resolve_vm_ip(target, vm_ips)
        h = health_check(ip)
        if h.get("status") != "healthy":
            return {"success": False, "output": f"SubAgent unreachable: {ip}", "health": h}
        r = run_command(ip,
            "echo '=== UPTIME ===' && uptime && "
            "echo '=== CPU ===' && top -bn1 2>/dev/null | grep 'Cpu(s)' | head -1 && "
            "echo '=== DISK ===' && df -h / && "
            "echo '=== MEMORY ===' && free -h && "
            "echo '=== FAILED SERVICES ===' && systemctl list-units --failed --no-pager | head -5",
            timeout=20)
        return {"success": r.get("exit_code") == 0, "output": r.get("stdout", ""), "target": target, "ip": ip}

    elif name == "probe_all":
        results = {}
        for role, ip in vm_ips.items():
            h = health_check(ip)
            if h.get("status") == "healthy":
                r = run_command(ip, "uptime | awk '{print $3,$4}' | tr -d ','", timeout=10)
                results[role] = {"status": "online", "ip": ip, "uptime": r.get("stdout", "").strip()}
            else:
                results[role] = {"status": "offline", "ip": ip}
        return {"success": True, "output": results}

    elif name == "scan_ports":
        target = params.get("target", "10.20.30.80")
        ip = _resolve_vm_ip(target, vm_ips)
        ports = params.get("ports", "--top-ports 100")
        attacker_ip = vm_ips.get("attacker", "")
        # greppable output (-oG) for reliable parsing, plus normal output
        r = run_command(attacker_ip,
            f"nmap -sV {ip} {ports} --max-retries 1 -T4 --host-timeout 30s -oG - 2>/dev/null | grep 'Ports:' || "
            f"nmap -sV {ip} {ports} --max-retries 1 -T4 --host-timeout 30s 2>/dev/null | grep -E '^[0-9]+/tcp'",
            timeout=45)
        raw = r.get("stdout", "")
        # extract open ports summary
        open_ports = []
        for line in raw.splitlines():
            if "/open/" in line:  # greppable format
                import re
                for m in re.finditer(r'(\d+)/open/tcp//([^/]*)//', line):
                    open_ports.append(f"{m.group(1)}/tcp {m.group(2)}")
            elif "/tcp" in line and "open" in line:  # normal format
                open_ports.append(line.strip())
        summary = f"Open ports on {ip}: {len(open_ports)} found\n" + "\n".join(open_ports) if open_ports else f"No open ports found on {ip}"
        return {"success": r.get("exit_code") == 0, "output": summary, "target": ip, "open_count": len(open_ports)}

    elif name == "check_suricata":
        lines = params.get("lines", 10)
        ip = vm_ips.get("secu", "")
        r = run_command(ip, f"echo '=== Suricata Status ===' && systemctl is-active suricata && echo '=== Recent Alerts ===' && tail -{lines} /var/log/suricata/eve.json 2>/dev/null | python3 -c \"import sys,json; [print(f'[{{e.get(\\\"timestamp\\\",\\\"\\\")[:19]}}] {{e.get(\\\"alert\\\",{{}}).get(\\\"signature\\\",\\\"?\\\")}} src={{e.get(\\\"src_ip\\\",\\\"?\\\")}}') for l in sys.stdin for e in [json.loads(l)] if e.get('event_type')=='alert']\" 2>/dev/null || tail -{lines} /var/log/suricata/eve.json 2>/dev/null | grep alert | tail -5", timeout=15)
        return {"success": True, "output": r.get("stdout", "")}

    elif name == "check_wazuh":
        ip = vm_ips.get("siem", "")
        r = run_command(ip, "echo '=== Wazuh Manager ===' && systemctl is-active wazuh-manager && echo '=== Agents ===' && /var/ossec/bin/agent_control -l 2>/dev/null && echo '=== Recent Alerts ===' && tail -5 /var/ossec/logs/alerts/alerts.json 2>/dev/null | head -5", timeout=15)
        return {"success": True, "output": r.get("stdout", "")}

    elif name == "enroll_wazuh_agent":
        target_role = params.get("target", "secu")
        target_ip = _resolve_vm_ip(target_role, vm_ips)
        siem_ip = vm_ips.get("siem", "10.20.30.100")
        steps = []

        # 1. wazuh-agent 설치 여부 확인
        check = run_command(target_ip, "dpkg -l wazuh-agent 2>/dev/null | grep -q '^ii' && echo installed || echo not_installed", timeout=10)
        installed = check.get("stdout", "").strip() == "installed"
        steps.append(f"installed={installed}")

        if not installed:
            # Wazuh Manager 버전과 일치하는 버전 설치 (4.10.3)
            install_cmd = (
                "curl -s https://packages.wazuh.com/key/GPG-KEY-WAZUH | sudo gpg --dearmor -o /usr/share/keyrings/wazuh.gpg 2>&1 | tail -1 && "
                "echo 'deb [signed-by=/usr/share/keyrings/wazuh.gpg] https://packages.wazuh.com/4.x/apt/ stable main' | "
                "sudo tee /etc/apt/sources.list.d/wazuh.list > /dev/null && "
                "sudo apt-get update -qq 2>&1 | tail -2 && "
                "sudo DEBIAN_FRONTEND=noninteractive apt-get install -y wazuh-agent=4.10.3-1 2>&1 | tail -5"
            )
            r = run_command(target_ip, install_cmd, timeout=180)
            steps.append(f"install: {r.get('stdout','')[-200:]}")

        # 2. Manager IP 설정 (placeholder 포함 모든 address 교체)
        cfg_cmd = (
            f"sudo sed -i 's|<address>[^<]*</address>|<address>{siem_ip}</address>|g' /var/ossec/etc/ossec.conf && "
            f"grep '<address>' /var/ossec/etc/ossec.conf"
        )
        r = run_command(target_ip, cfg_cmd, timeout=15)
        steps.append(f"config: {r.get('stdout','').strip()}")

        # 3. 에이전트 등록 (authd)
        auth_cmd = f"sudo /var/ossec/bin/agent-auth -m {siem_ip} -A {target_role} 2>&1"
        r = run_command(target_ip, auth_cmd, timeout=30)
        auth_out = r.get("stdout", "")
        steps.append(f"auth: {auth_out[:200]}")

        # 4. 서비스 시작
        r = run_command(target_ip,
            "sudo systemctl daemon-reload && sudo systemctl enable wazuh-agent && "
            "sudo systemctl restart wazuh-agent && sleep 3 && sudo systemctl is-active wazuh-agent",
            timeout=20)
        steps.append(f"service: {r.get('stdout','').strip()}")

        # 5. siem에서 등록 확인
        verify = run_command(siem_ip,
            f"/var/ossec/bin/agent_control -l 2>/dev/null | grep -i {target_role}",
            timeout=10)
        enrolled = bool(verify.get("stdout", "").strip())
        steps.append(f"enrolled_on_siem: {enrolled} → {verify.get('stdout','').strip()}")

        return {
            "success": enrolled,
            "output": "\n".join(steps),
            "target": target_role,
            "enrolled": enrolled,
        }

    elif name == "check_modsecurity":
        lines = params.get("lines", 10)
        ip = vm_ips.get("web", "")
        r = run_command(ip, f"echo '=== ModSecurity Status ===' && apachectl -M 2>/dev/null | grep security && echo '=== Recent Blocks ===' && grep 'ModSecurity' /var/log/apache2/error.log 2>/dev/null | tail -{lines}", timeout=15)
        return {"success": True, "output": r.get("stdout", "")}

    elif name == "configure_nftables":
        action = params.get("action", "list")
        ip = vm_ips.get("secu", "")
        if action == "list":
            r = run_command(ip, "nft list ruleset", timeout=10)
        elif action == "add":
            rule = params.get("rule", "")
            r = run_command(ip, f"nft add rule inet filter input {rule}", timeout=10)
        elif action == "delete":
            rule = params.get("rule", "")
            r = run_command(ip, f"nft delete rule inet filter input {rule}", timeout=10)
        else:
            return {"success": False, "error": f"Unknown action: {action}"}
        return {"success": r.get("exit_code") == 0, "output": r.get("stdout", ""), "stderr": r.get("stderr", "")}

    elif name == "analyze_logs":
        target = params.get("target", "siem")
        ip = _resolve_vm_ip(target, vm_ips)
        log_source = params.get("log_source", "/var/log/syslog")
        query = params.get("query", "최근 이상 징후 요약")
        # 로그 수집
        r = run_command(ip, f"tail -50 {log_source} 2>/dev/null", timeout=15)
        log_data = r.get("stdout", "")[:3000]
        if not log_data:
            return {"success": False, "output": f"No data from {log_source} on {target}"}
        # LLM 분석
        if ollama_url and model:
            import httpx
            try:
                resp = httpx.post(f"{ollama_url}/api/chat", json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": "너는 보안 로그 분석 전문가다. 로그를 분석하고 간결하게 한국어로 답변해."},
                        {"role": "user", "content": f"질문: {query}\n\n로그 데이터:\n{log_data}"},
                    ],
                    "stream": False, "options": {"num_predict": 500, "temperature": 0.3},
                }, timeout=60.0)
                analysis = resp.json().get("message", {}).get("content", "분석 실패")
            except Exception as e:
                analysis = f"LLM 연결 실패: {e}"
        else:
            analysis = f"LLM 미설정. 원본 로그:\n{log_data[:500]}"
        return {"success": True, "output": analysis, "raw_log": log_data[:500]}

    elif name == "deploy_rule":
        import base64
        rule_type = params.get("rule_type", "suricata")
        rule_content = params.get("rule_content", "")
        # base64 인코딩으로 인용부호 문제 방지
        b64 = base64.b64encode(rule_content.encode()).decode()
        if rule_type == "suricata":
            ip = vm_ips.get("secu", "")
            rules_path = "/var/lib/suricata/rules/local.rules"
            # sid 중복 방지: 해당 sid가 없을 때만 추가
            sid = ""
            import re as _re
            sid_m = _re.search(r'sid:(\d+)', rule_content)
            if sid_m:
                sid = sid_m.group(1)
            dedup_check = f"grep -q 'sid:{sid}' {rules_path} 2>/dev/null && echo DUPLICATE || echo NEW" if sid else "echo NEW"
            r_check = run_command(ip, dedup_check, timeout=5)
            if "DUPLICATE" in r_check.get("stdout", ""):
                return {"success": True, "output": f"Rule sid:{sid} already exists in {rules_path}"}
            r = run_command(ip,
                f"echo '{b64}' | base64 -d | sudo tee -a {rules_path} > /dev/null && "
                f"echo -n 'Rule added. Reloading... ' && "
                f"sudo kill -HUP $(pidof suricata) 2>/dev/null && echo 'OK' || echo 'reload failed'",
                timeout=15)
        elif rule_type == "wazuh":
            ip = vm_ips.get("siem", "")
            rules_path = "/var/ossec/etc/rules/local_rules.xml"
            r = run_command(ip,
                f"echo '{b64}' | base64 -d | sudo tee -a {rules_path} > /dev/null && "
                f"echo 'Rule added' && sudo /var/ossec/bin/wazuh-control restart 2>/dev/null | tail -3",
                timeout=30)
        else:
            return {"success": False, "error": f"Unknown rule_type: {rule_type}"}
        return {"success": r.get("exit_code") == 0, "output": r.get("stdout", ""), "stderr": r.get("stderr", "")}

    elif name == "web_scan":
        url = params.get("url", "http://10.20.30.80")
        attacker_ip = vm_ips.get("attacker", "")
        r = run_command(attacker_ip, f"echo '=== Headers ===' && curl -sI {url} | head -15 && echo '=== Nikto ===' && nikto -h {url} -maxtime 30 2>/dev/null | head -25", timeout=45)
        return {"success": True, "output": r.get("stdout", "")}

    elif name == "shell":
        command = params.get("command", "echo ok")
        target = params.get("target", "attacker")
        ip = _resolve_vm_ip(target, vm_ips)
        r = run_command(ip, command, timeout=30)
        return {"success": r.get("exit_code") == 0, "output": r.get("stdout", ""), "stderr": r.get("stderr", "")}

    return {"success": False, "error": f"Skill '{name}' not implemented"}
