#!/usr/bin/env python3
"""bastion — CCC Bastion 보안 운영 에이전트 TUI

자연어로 보안 작업을 지시하면 Skill/Playbook 기반으로 실행.
학생은 manager VM에서, 관리자는 CCC 서버에서 사용.

Usage:
    python -m apps.bastion.main
    ./dev.sh bastion
"""
import os
import sys
import json

CCC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, CCC_DIR)

# .env 로드
ENV_PATH = os.path.join(CCC_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_vm_ips() -> dict[str, str]:
    """DB 또는 환경변수에서 VM IP 가져오기"""
    # 환경변수에서 직접 지정 가능
    vm_ips = {}
    for role in ["attacker", "secu", "web", "siem", "manager"]:
        env_key = f"VM_{role.upper()}_IP"
        ip = os.getenv(env_key, "")
        if ip:
            vm_ips[role] = ip

    if vm_ips:
        return vm_ips

    # DB에서 가져오기
    try:
        import psycopg2
        conn = psycopg2.connect(os.getenv("DATABASE_URL", "postgresql://ccc:ccc@127.0.0.1:5434/ccc"))
        cur = conn.cursor()
        cur.execute("SELECT ip, vm_config FROM student_infras LIMIT 10")
        for row in cur.fetchall():
            cfg = row[1] if isinstance(row[1], dict) else json.loads(row[1]) if row[1] else {}
            role = cfg.get("role", "")
            if role:
                vm_ips[role] = row[0]
        conn.close()
    except Exception:
        pass

    # 기본값
    if not vm_ips:
        from bastion import INTERNAL_IPS
        vm_ips = dict(INTERNAL_IPS)

    return vm_ips


def main():
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        from rich.text import Text
    except ImportError:
        print("[bastion] rich 설치 중...")
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"], check=True)
        from rich.console import Console
        from rich.panel import Panel
        from rich.markdown import Markdown
        from rich.text import Text

    from bastion.agent import BastionAgent

    console = Console()
    vm_ips = get_vm_ips()
    ollama_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    model = os.getenv("LLM_MANAGER_MODEL", os.getenv("LLM_MODEL", "gpt-oss:120b"))

    agent = BastionAgent(vm_ips=vm_ips, ollama_url=ollama_url, model=model)

    # 헤더
    vm_status = ", ".join(f"{r}={ip}" for r, ip in vm_ips.items())
    console.print(Panel(
        f"[bold orange1]CCC Bastion Agent[/]\n"
        f"[dim]Model: {model} | LLM: {ollama_url}[/]\n"
        f"[dim]Infra: {vm_status}[/]\n"
        f"[dim]Skills: {len(agent.get_skills())} | Playbooks: {len(agent.get_playbooks())}[/]",
        border_style="orange1",
    ))
    console.print("[dim]명령어: /skills, /playbooks, /evidence, /search <키워드>, /stats, /quit[/]\n")

    def approval_callback(step_name: str, skill: str, params: dict) -> bool:
        """위험 작업 확인"""
        console.print(f"\n[yellow bold]  !! 확인 필요: {skill}[/]")
        console.print(f"  [dim]{json.dumps(params, ensure_ascii=False)[:100]}[/]")
        try:
            answer = console.input("  [yellow]실행? [Y/n]: [/]").strip().lower()
            return answer in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    while True:
        try:
            user_input = console.input("\n[bold green]> [/]").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/]")
            break

        if not user_input:
            continue

        # 내장 명령어
        if user_input in ("/quit", "/exit", "/q"):
            console.print("[dim]Bye![/]")
            break
        elif user_input == "/skills":
            for s in agent.get_skills():
                console.print(f"  [cyan]{s['name']:20}[/] {s['description']}")
            continue
        elif user_input == "/playbooks":
            for p in agent.get_playbooks():
                console.print(f"  [cyan]{p['playbook_id']:20}[/] {p['title']} ({p['steps']}단계)")
            continue
        elif user_input == "/evidence":
            evs = agent.get_evidence(10)
            if not evs:
                console.print("  [dim]No evidence yet[/]")
            else:
                for e in evs:
                    s = "ok" if e.get("success") else "fail"
                    console.print(f"  [{s}] {e.get('timestamp','')[:16]} {e.get('skill','')} — {e.get('analysis','')[:60]}")
            continue
        elif user_input.startswith("/search "):
            keyword = user_input[8:].strip()
            evs = agent.search_evidence(keyword)
            if not evs:
                console.print(f"  [dim]'{keyword}' 검색 결과 없음[/]")
            else:
                for e in evs:
                    console.print(f"  [{e.get('timestamp','')[:16]}] {e.get('skill','')} — {e.get('analysis','')[:60]}")
            continue
        elif user_input == "/stats":
            s = agent.evidence_db.stats()
            console.print(f"  Evidence: {s['total']} total, {s['success']} success, {s['fail']} fail")
            if agent.rag_index:
                rs = agent.rag_index.stats()
                console.print(f"  RAG: {rs['chunks']} chunks, {rs['keywords']} keywords")
            continue

        # 에이전트 대화
        with console.status("[orange1]Bastion thinking...[/]", spinner="dots"):
            events = list(agent.chat(user_input, approval_callback=approval_callback))

        for evt in events:
            if evt.get("event") == "skill_start":
                console.print(f"\n  [cyan]>> {evt['skill']}[/] 실행 중...", end="")
            elif evt.get("event") == "skill_result":
                status = "[green]ok[/]" if evt.get("success") else "[red]fail[/]"
                console.print(f" {status}")
                output = evt.get("output", "")
                if output:
                    # 딕셔너리면 정리해서 표시
                    if isinstance(output, str) and output.startswith("{"):
                        try:
                            d = json.loads(output.replace("'", '"'))
                            for k, v in d.items():
                                console.print(f"    [dim]{k}:[/] {v}")
                        except Exception:
                            for line in output.split("\n")[:15]:
                                console.print(f"    {line}")
                    else:
                        for line in str(output).split("\n")[:15]:
                            console.print(f"    {line}")
            elif evt.get("event") == "analysis":
                console.print(f"\n  [bold cyan]분석:[/] {evt['content']}")
            elif evt.get("event") == "risk_warning":
                console.print(f"\n  [yellow bold]  !! 위험도 {evt.get('risk','?')}: {evt.get('skill','')}[/]")
            elif evt.get("event") == "skill_skip":
                console.print(f"  [yellow]>> {evt.get('skill','')} 스킵됨 ({evt.get('reason','')})[/]")
            elif evt.get("event") == "message":
                console.print(f"\n  [bold]{evt['content']}[/]")
            elif evt.get("event") == "error":
                console.print(f"\n  [red]Error: {evt.get('content', evt.get('message',''))}[/]")
            elif evt.get("event") == "playbook_start":
                console.print(f"\n  [cyan bold]Playbook: {evt.get('title','')} ({evt.get('total_steps',0)}단계)[/]")
            elif evt.get("event") == "step_start":
                console.print(f"    [{evt.get('step',0)}] {evt.get('name','')}...", end="")
            elif evt.get("event") == "step_done":
                s = "[green]ok[/]" if evt.get("success") else "[red]fail[/]"
                console.print(f" {s}")
            elif evt.get("event") == "playbook_done":
                console.print(f"  [bold]Playbook 완료: {evt.get('passed',0)}/{evt.get('total',0)}[/]")


if __name__ == "__main__":
    main()
