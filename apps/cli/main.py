"""bastion CLI — 실무 운영/보안 에이전트 CLI"""
import argparse
import json
import os
import sys
import httpx

API_URL = os.getenv("BASTION_API_URL", "http://localhost:9000")
API_KEY = os.getenv("BASTION_API_KEY", "bastion-api-key-2026")

def _headers():
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}

def cmd_assets(args):
    r = httpx.get(f"{API_URL}/assets", headers=_headers())
    data = r.json()
    assets = data.get("assets", [])
    if not assets:
        print("등록된 자산 없음")
        return
    print(f"{'ID':<10} {'Name':<15} {'IP':<18} {'Status':<12} {'Role'}")
    print("-" * 70)
    for a in assets:
        print(f"{a['id']:<10} {a['name']:<15} {a['ip']:<18} {a['status']:<12} {a.get('role','')}")

def cmd_add(args):
    body = {"name": args.name, "ip": args.ip, "os_type": args.os or "linux", "role": args.role or ""}
    r = httpx.post(f"{API_URL}/assets", json=body, headers=_headers())
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

def cmd_onboard(args):
    body = {"auto_bootstrap": True}
    if args.password:
        body["ssh_password"] = args.password
    r = httpx.post(f"{API_URL}/assets/{args.asset_id}/onboard", json=body, headers=_headers())
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

def cmd_health(args):
    r = httpx.get(f"{API_URL}/assets/{args.asset_id}/health", headers=_headers())
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

def cmd_dashboard(args):
    r = httpx.get(f"{API_URL}/dashboard/summary", headers=_headers())
    data = r.json()
    print(f"Assets: {data['assets']['total']} (by status: {data['assets']['by_status']})")
    print(f"Operations: {data['operations']['total']}")
    print(f"Blockchain blocks: {data['blockchain']['blocks']}")

def cmd_blocks(args):
    params = {}
    if args.agent_id:
        params["agent_id"] = args.agent_id
    r = httpx.get(f"{API_URL}/blockchain/blocks", params=params, headers=_headers())
    blocks = r.json().get("blocks", [])
    for b in blocks[:20]:
        print(f"[{b['block_index']}] {b['block_hash'][:16]}... agent={b['agent_id']} reward={b['reward_amount']}")

def cmd_task(args):
    body = {"instruction": args.instruction, "risk_level": args.risk or "low"}
    r = httpx.post(f"{API_URL}/agent/task", json=body, headers=_headers())
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

def cmd_analyze(args):
    body = {"instruction": args.query}
    r = httpx.post(f"{API_URL}/agent/analyze", json=body, headers=_headers())
    print(json.dumps(r.json(), indent=2, ensure_ascii=False))

def main():
    parser = argparse.ArgumentParser(prog="bastion", description="Bastion — 실무 운영/보안 AI 에이전트")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("assets", help="자산 목록")
    p_add = sub.add_parser("add", help="자산 등록")
    p_add.add_argument("name"); p_add.add_argument("ip")
    p_add.add_argument("--os", default="linux"); p_add.add_argument("--role", default="")

    p_onboard = sub.add_parser("onboard", help="자산 온보딩")
    p_onboard.add_argument("asset_id"); p_onboard.add_argument("--password")

    p_health = sub.add_parser("health", help="자산 헬스체크")
    p_health.add_argument("asset_id")

    sub.add_parser("dashboard", help="대시보드")

    p_blocks = sub.add_parser("blocks", help="블록체인")
    p_blocks.add_argument("--agent-id")

    p_task = sub.add_parser("task", help="AI 작업 요청")
    p_task.add_argument("instruction"); p_task.add_argument("--risk", default="low")

    p_analyze = sub.add_parser("analyze", help="시스템 분석")
    p_analyze.add_argument("query")

    args = parser.parse_args()
    if not args.cmd:
        parser.print_help()
        return

    cmds = {
        "assets": cmd_assets, "add": cmd_add, "onboard": cmd_onboard,
        "health": cmd_health, "dashboard": cmd_dashboard, "blocks": cmd_blocks,
        "task": cmd_task, "analyze": cmd_analyze,
    }
    cmds[args.cmd](args)

if __name__ == "__main__":
    main()
