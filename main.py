#!/usr/bin/env python3
"""bastion — CCC Bastion 보안 운영 에이전트 TUI

자연어로 보안 작업을 지시하면 Playbook/Skill 기반으로 실행.
학생은 manager VM에서, 관리자는 CCC 서버에서 사용.

Usage:
    python -m apps.bastion.main
    ./dev.sh bastion
"""
import io
import json
import os
import sys

BASTION_DIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, BASTION_DIR)

# 한글 IME 잔류 바이트 방지 — stdin을 UTF-8 errors=ignore 로 재설정
if hasattr(sys.stdin, "buffer"):
    sys.stdin = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8", errors="ignore")

# .env 로드
ENV_PATH = os.path.join(BASTION_DIR, ".env")
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


def get_vm_ips() -> dict[str, str]:
    """DB 또는 환경변수에서 VM IP 가져오기"""
    vm_ips = {}
    for role in ["attacker", "secu", "web", "siem", "manager"]:
        ip = os.getenv(f"VM_{role.upper()}_IP", "")
        if ip:
            vm_ips[role] = ip

    if vm_ips:
        return vm_ips

    if not vm_ips:
        from bastion import INTERNAL_IPS
        vm_ips = dict(INTERNAL_IPS)

    return vm_ips


BANNER = r"""
  ██████╗  █████╗ ███████╗████████╗██╗ ██████╗ ███╗   ██╗
  ██╔══██╗██╔══██╗██╔════╝╚══██╔══╝██║██╔═══██╗████╗  ██║
  ██████╔╝███████║███████╗   ██║   ██║██║   ██║██╔██╗ ██║
  ██╔══██╗██╔══██║╚════██║   ██║   ██║██║   ██║██║╚██╗██║
  ██████╔╝██║  ██║███████║   ██║   ██║╚██████╔╝██║ ╚████║
  ╚═════╝ ╚═╝  ╚═╝╚══════╝   ╚═╝   ╚═╝ ╚═════╝ ╚═╝  ╚═══╝
"""

COMMANDS = {
    "/skills":         "등록된 Skill 목록",
    "/playbooks":      "등록된 Playbook 목록",
    "/evidence":       "최근 실행 기록 (10건)",
    "/search <키워드>": "Evidence 검색",
    "/stats":          "통계 (evidence, RAG)",
    "/clear":          "대화 기록 초기화",
    "/quit":           "종료",
}


def main():
    try:
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich import box
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "rich", "-q"], check=True)
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text
        from rich import box

    from bastion.agent import BastionAgent, sanitize_text

    console = Console()
    vm_ips = get_vm_ips()
    ollama_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    model = os.getenv("LLM_MANAGER_MODEL", os.getenv("LLM_MODEL", "gpt-oss:120b"))

    agent = BastionAgent(vm_ips=vm_ips, ollama_url=ollama_url, model=model)

    # ── 배너 ──────────────────────────────────────────────────────────────
    console.print(Text(BANNER, style="bold orange1"))

    infra_table = Table(box=box.SIMPLE, show_header=True, header_style="bold dim",
                        border_style="dim", padding=(0, 1))
    infra_table.add_column("Role", style="cyan", width=10)
    infra_table.add_column("IP", style="white", width=18)
    infra_table.add_column("Internal", style="dim", width=16)

    from bastion import INTERNAL_IPS
    for role, ip in vm_ips.items():
        internal = INTERNAL_IPS.get(role, "—")
        infra_table.add_row(role, ip, internal)

    skills_count = len(agent.get_skills())
    playbooks_count = len(agent.get_playbooks())
    rag_info = ""
    if agent.rag_index:
        rs = agent.rag_index.stats()
        rag_info = f"RAG {rs['chunks']} chunks"

    console.print(Panel(
        f"[bold white]Model:[/] [orange1]{model}[/]   "
        f"[bold white]LLM:[/] [dim]{ollama_url}[/]\n"
        f"[bold white]Skills:[/] [cyan]{skills_count}[/]   "
        f"[bold white]Playbooks:[/] [cyan]{playbooks_count}[/]"
        + (f"   [bold white]{rag_info}[/]" if rag_info else ""),
        title="[bold orange1]Bastion Agent[/]",
        border_style="orange1",
        padding=(0, 2),
    ))
    console.print(infra_table)

    hints = "  ".join(f"[dim]{cmd}[/]" for cmd in COMMANDS)
    console.print(f"\n{hints}\n")

    # ── 승인 콜백 ──────────────────────────────────────────────────────────
    def approval_callback(step_name: str, skill: str, params: dict) -> bool:
        console.print(f"\n  [yellow bold]⚠ 확인 필요: {skill}[/]")
        console.print(f"  [dim]{json.dumps(params, ensure_ascii=False)[:120]}[/]")
        try:
            answer = sanitize_text(
                console.input("  [yellow]실행하시겠습니까? [Y/n]: [/]")
            ).strip().lower()
            return answer in ("", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    # ── 메인 루프 ──────────────────────────────────────────────────────────
    while True:
        try:
            raw = console.input("\n[bold green]▶ [/]")
        except UnicodeDecodeError:
            console.print("[red]입력 오류: 한글 재입력 바람[/]")
            continue
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye![/]")
            break

        user_input = sanitize_text(raw)
        if not user_input:
            continue

        # ── 내장 명령어 ────────────────────────────────────────────────────
        if user_input in ("/quit", "/exit", "/q"):
            console.print("[dim]Bye![/]")
            break

        elif user_input == "/skills":
            t = Table(box=box.SIMPLE, show_header=False, border_style="dim", padding=(0, 1))
            t.add_column("name", style="cyan", width=22)
            t.add_column("desc", style="white")
            t.add_column("flag", style="yellow", width=10)
            for s in agent.get_skills():
                flag = "⚠ 승인" if s["requires_approval"] else ""
                t.add_row(s["name"], s["description"], flag)
            console.print(t)
            continue

        elif user_input == "/playbooks":
            t = Table(box=box.SIMPLE, show_header=False, border_style="dim", padding=(0, 1))
            t.add_column("id", style="cyan", width=22)
            t.add_column("title", style="white")
            t.add_column("steps", style="dim", width=6)
            for p in agent.get_playbooks():
                t.add_row(p["playbook_id"], p["title"], f"{p['steps']}단계")
            console.print(t)
            continue

        elif user_input == "/evidence":
            evs = agent.get_evidence(10)
            if not evs:
                console.print("  [dim]No evidence yet[/]")
            else:
                t = Table(box=box.SIMPLE, show_header=True,
                          header_style="bold dim", border_style="dim", padding=(0, 1))
                t.add_column("시각", style="dim", width=16)
                t.add_column("작업", style="cyan", width=22)
                t.add_column("결과", width=6)
                t.add_column("분석", style="white")
                for e in evs:
                    label = e.get("playbook_id") or e.get("skill") or "?"
                    result = "[green]ok[/]" if e.get("success") else "[red]fail[/]"
                    t.add_row(
                        (e.get("timestamp") or "")[:16],
                        label,
                        result,
                        (e.get("analysis") or "")[:60],
                    )
                console.print(t)
            continue

        elif user_input.startswith("/search "):
            keyword = user_input[8:].strip()
            evs = agent.search_evidence(keyword)
            if not evs:
                console.print(f"  [dim]'{keyword}' 검색 결과 없음[/]")
            else:
                for e in evs:
                    label = e.get("playbook_id") or e.get("skill") or "?"
                    console.print(
                        f"  [{(e.get('timestamp') or '')[:16]}] "
                        f"[cyan]{label}[/] — {(e.get('analysis') or '')[:70]}"
                    )
            continue

        elif user_input == "/stats":
            s = agent.evidence_db.stats()
            console.print(
                f"  Evidence: [cyan]{s['total']}[/] total  "
                f"[green]{s['success']}[/] ok  [red]{s['fail']}[/] fail"
            )
            if agent.rag_index:
                rs = agent.rag_index.stats()
                console.print(f"  RAG: [cyan]{rs['chunks']}[/] chunks  {rs['keywords']} keywords")
            continue

        elif user_input == "/clear":
            agent.history.clear()
            console.print("  [dim]대화 기록 초기화됨[/]")
            continue

        # ── 에이전트 대화 (Streaming 지원) ────────────────────────────────
        stage_labels = {
            "planning":   "[dim]◈ PLANNING[/]",
            "executing":  "[dim]◈ EXECUTING[/]",
            "validating": "[dim]◈ VALIDATING[/]",
            "qa":         "[dim]◈ Q&A[/]",
        }

        # Planning 중에만 스피너 표시, 이후는 실시간 스트리밍
        status = console.status("[orange1]Bastion 분석 중...[/]", spinner="dots")
        status.start()
        spinner_active = True

        def stop_spinner():
            nonlocal spinner_active
            if spinner_active:
                status.stop()
                spinner_active = False

        try:
            for evt in agent.chat(user_input, approval_callback=approval_callback):
                etype = evt.get("event", "")

                # Executing/QA 단계 시작 시 스피너 종료
                if etype == "stage" and evt.get("stage") in ("executing", "qa"):
                    stop_spinner()
                elif etype in ("skill_start", "playbook_start", "stream_start"):
                    stop_spinner()

                # ── 스테이지 표시
                if etype == "stage":
                    stage = evt.get("stage", "")
                    label = stage_labels.get(stage, "")
                    if label:
                        console.print(f"\n{label}", end="")

                # ── Streaming 출력
                elif etype == "stream_start":
                    label = evt.get("label", "")
                    if label == "분석":
                        console.print(f"\n  [bold cyan]◆ 분석[/]  ", end="")
                    elif label == "답변":
                        console.print(f"\n  ", end="")

                elif etype == "stream_token":
                    console.print(evt["token"], end="", highlight=False)

                elif etype == "stream_end":
                    console.print()

                # ── Playbook 이벤트
                elif etype == "playbook_selected":
                    console.print(
                        f"\n  [cyan bold]▶ Playbook:[/] {evt.get('title', evt.get('playbook_id', ''))}"
                    )

                elif etype == "playbook_start":
                    console.print(
                        f"\n  [orange1 bold]Playbook:[/] {evt.get('title', '')} "
                        f"[dim]({evt.get('total_steps', 0)}단계)[/]"
                    )

                elif etype == "step_start":
                    console.print(
                        f"    [dim][{evt.get('step', 0)}][/] {evt.get('name', '')}...",
                        end="",
                    )

                elif etype == "step_done":
                    mark = "[green]✓[/]" if evt.get("success") else "[red]✗[/]"
                    console.print(f" {mark}")
                    output = evt.get("output", "")
                    if output and not evt.get("success"):
                        console.print(f"      [dim]{str(output)[:100]}[/]")

                elif etype == "playbook_done":
                    p, t = evt.get("passed", 0), evt.get("total", 0)
                    color = "green" if p == t else "yellow"
                    console.print(f"  [bold]완료:[/] [{color}]{p}/{t}[/]")

                # ── Skill 이벤트
                elif etype == "precheck_fail":
                    console.print(f"\n  [yellow]⚠ Pre-check: {evt.get('message', '')}[/]")

                elif etype == "skill_start":
                    console.print(
                        f"\n  [cyan]>> {evt['skill']}[/]"
                        f" [dim]{json.dumps(evt.get('params', {}), ensure_ascii=False)[:60]}[/]",
                        end="",
                    )

                elif etype == "skill_result":
                    mark = "[green]✓[/]" if evt.get("success") else "[red]✗[/]"
                    console.print(f"  {mark}")
                    output = evt.get("output", "")
                    if output:
                        if isinstance(output, str) and output.strip().startswith("{"):
                            try:
                                d = json.loads(output.replace("'", '"'))
                                for k, v in list(d.items())[:8]:
                                    console.print(f"    [dim]{k}:[/] {v}")
                            except Exception:
                                for line in str(output).split("\n")[:12]:
                                    console.print(f"    {line}")
                        else:
                            for line in str(output).split("\n")[:12]:
                                if line.strip():
                                    console.print(f"    {line}")

                elif etype == "risk_warning":
                    console.print(
                        f"\n  [yellow bold]⚠ 위험 작업:[/] {evt.get('skill', '')} "
                        f"[dim](risk={evt.get('risk', '?')})[/]"
                    )

                elif etype == "skill_skip":
                    console.print(
                        f"  [yellow]⊘ {evt.get('skill', '')} 스킵 "
                        f"({evt.get('reason', '')})[/]"
                    )

                elif etype == "message":
                    stop_spinner()
                    console.print(f"\n  {evt['content']}")

                elif etype == "error":
                    stop_spinner()
                    console.print(
                        f"\n  [red bold]✗ 오류:[/] {evt.get('content', evt.get('message', ''))}"
                    )

                elif etype == "playbook_abort":
                    console.print(
                        f"\n  [red bold]✗ Playbook 중단:[/] "
                        f"step {evt.get('step', '?')} — {evt.get('reason', '')}"
                    )

        except Exception as e:
            console.print(f"\n  [red bold]✗ 처리 오류:[/] {e}")
        finally:
            stop_spinner()


if __name__ == "__main__":
    main()
