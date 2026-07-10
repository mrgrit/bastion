#!/usr/bin/env python3
"""tw2/el34 teach-until-pass 순차 루프 러너.
한 번에 한 과제(순차) 발제→채점(Assessor 그라운드트루스 + 답변 정규식)→ledger→REPORT push.
멈추지 않고 큐를 끝까지 처리. 병렬 없음.

사용:
  loop.py                      # tasks.json 큐 순차 실행
  loop.py --grade-test <ndjson> <task_id>   # 오프라인 채점 검증(GPU 불필요)
"""
import base64, json, os, re, subprocess, sys, time, pathlib, urllib.request

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]                      # /home/ccc/bastion
EVAL = ROOT / "eval-tw2"
RUNS = EVAL / "runs"; RUNS.mkdir(parents=True, exist_ok=True)
TASKS = json.loads((HERE / "tasks.json").read_text())
LEDGER = EVAL / "runner_ledger.json"

def secrets():
    d = {}
    for ln in (ROOT / ".eval-secrets").read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1); d[k] = v.strip()
    return d
S = secrets()

def assess(checks):
    """Assessor 그라운드트루스: 모든 check passed 면 (True, evidence)."""
    if not checks: return True, "no-checks"
    body = json.dumps({"checks": checks}).encode()
    req = urllib.request.Request(S["ASSESSOR_URL"] + "/assess", data=body,
        headers={"X-API-Key": S["ASSESSOR_API_KEY"], "Content-Type": "application/json"})
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=25).read())
    except Exception as e:
        return None, f"assessor-error: {e}"
    res = r.get("results", [])
    allp = all(x.get("passed") is True for x in res)
    return allp, "; ".join(f"{x['id']}={x.get('passed')}" for x in res)

def extract_answer(ndjson):
    """스트림에서 최종 답변 텍스트 재구성."""
    toks = []
    for ln in ndjson.splitlines():
        ln = ln.strip()
        if not ln.startswith("{"): continue
        try: e = json.loads(ln)
        except Exception: continue
        if e.get("event") == "stream_token": toks.append(e.get("token", ""))
        elif e.get("event") in ("final", "answer", "analysis"): toks.append(e.get("text", "") or e.get("content", ""))
    return "".join(toks)

def grade(answer, asserts):
    """각 assert: must(정규식) 매치 필수 + mustnot 매치 시 실패. 전부 만족해야 PASS."""
    detail = []
    ok = True
    for a in asserts:
        must = re.search(a["must"], answer, re.I | re.S) if a.get("must") else True
        notm = re.search(a["mustnot"], answer, re.I | re.S) if a.get("mustnot") else None
        good = bool(must) and not bool(notm)
        ok = ok and good
        detail.append(f"{a['fact']}={'OK' if good else 'X'}")
    return ("PASS" if ok else "FAIL"), ", ".join(detail)

def skills_of(ndjson):
    used, denied = [], []
    for ln in ndjson.splitlines():
        try: e = json.loads(ln)
        except Exception: continue
        if e.get("event") == "skill_start": used.append(e.get("skill"))
        elif e.get("event") == "skill_skip": denied.append(e.get("skill"))
    return used, denied

def run_one(task, rep):
    rid = f"{task['id']}_r{rep}"
    msg = task["message"]
    b64 = base64.b64encode(msg.encode()).decode()
    print(f"  ▶ {rid} 발제…", flush=True)
    try:
        p = subprocess.run(["bash", str(HERE / "run_task.sh"), rid, b64, "34"],
                           capture_output=True, text=True, timeout=2100)
        ndjson = p.stdout
    except subprocess.TimeoutExpired:
        return {"rep": rep, "verdict": "TIMEOUT", "detail": "run_task timeout"}
    (RUNS / f"{rid}.ndjson").write_text(ndjson)
    answer = extract_answer(ndjson)
    gt_ok, gt_ev = assess(task.get("ground_truth_checks", []))
    verdict, detail = grade(answer, task["asserts"])
    used, denied = skills_of(ndjson)
    print(f"    {rid}: {verdict} ({detail}) | gt={gt_ok} | skills={used} denied={denied}", flush=True)
    return {"rep": rep, "verdict": verdict, "detail": detail, "gt": gt_ok, "gt_ev": gt_ev,
            "skills_used": used, "skills_denied": denied, "answer_tail": answer[-300:]}

def load_ledger():
    if LEDGER.exists(): return json.loads(LEDGER.read_text())
    return {"loop": "teach-until-pass-runner", "heartbeat": 3, "tasks": {}}

def write_report(led):
    lines = ["# Bastion tw2/el34 — 러너 진행 (자동생성)", "",
             f"> loop.py 자동 갱신 · heartbeat #{led.get('heartbeat')}", ""]
    lines.append("| task | attempts | pass-rate | 최근 verdict |")
    lines.append("|---|---|---|---|")
    for tid, t in led["tasks"].items():
        att = t.get("attempts", [])
        p = sum(1 for a in att if a.get("verdict") == "PASS")
        rate = f"{p}/{len(att)}" if att else "-"
        last = att[-1]["verdict"] if att else "-"
        lines.append(f"| {tid} | {len(att)} | {rate} | {last} |")
    (EVAL / "REPORT-runner.md").write_text("\n".join(lines) + "\n")

def git_push(msg):
    subprocess.run(["git", "-C", str(ROOT), "add", "eval-tw2/"], check=False)
    subprocess.run(["git", "-C", str(ROOT), "-c", "user.name=mrgrit",
                    "-c", "user.email=mrgrit@ync.ac.kr", "commit", "-q", "-m", msg], check=False)
    helper = f'!f(){{ echo username=x-access-token; echo "password={S["GH_TOKEN"]}"; }};f'
    subprocess.run(["git", "-C", str(ROOT), "-c", f"credential.helper={helper}",
                    "push", "origin", S.get("GH_BRANCH", "eval-tw2")],
                   check=False, capture_output=True, text=True)

def main():
    if len(sys.argv) >= 4 and sys.argv[1] == "--grade-test":
        nd = pathlib.Path(sys.argv[2]).read_text()
        task = next(t for t in TASKS if t["id"] == sys.argv[3])
        ans = extract_answer(nd)
        print("verdict:", grade(ans, task["asserts"]))
        print("answer_tail:", repr(ans[-200:]))
        return
    led = load_ledger()
    for task in TASKS:
        tid = task["id"]; n = task.get("n_repeats", 1)
        rec = led["tasks"].setdefault(tid, {"prompt": task["message"][:80], "attempts": []})
        done = len(rec["attempts"])
        if done >= n:
            print(f"= {tid} 이미 {done}회 완료, skip"); continue
        for rep in range(done + 1, n + 1):
            rec["attempts"].append(run_one(task, rep))
            led["heartbeat"] = led.get("heartbeat", 3) + 1
            LEDGER.write_text(json.dumps(led, ensure_ascii=False, indent=2))
            write_report(led)
            git_push(f"eval(tw2): runner {tid} r{rep} = {rec['attempts'][-1]['verdict']} (heartbeat #{led['heartbeat']})")
    print("== 큐 완료 ==")

if __name__ == "__main__":
    main()
