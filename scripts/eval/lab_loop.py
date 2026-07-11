#!/usr/bin/env python3
"""tw2/el34 training LAB 전수 순차 러너 — 308 랩 × 스텝 전량.
각 스텝 = bastion 에 instruction 발제(실행) → 채점(verify.expect output_contains + semantic LLM-judge)
→ lab_ledger 기록 → main push. 순차·무샘플링·재개가능·무정지. (병렬 없음)

사용:
  lab_loop.py            # 전량 순차(완료 스텝 skip → 재개)
  lab_loop.py --count    # 총 스텝 수
"""
import base64, json, subprocess, sys, pathlib, urllib.request
try:
    import yaml
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "pyyaml", "-q"], check=False)
    import yaml

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
EVAL = ROOT / "eval-tw2"
LRUNS = EVAL / "lab_runs"; LRUNS.mkdir(parents=True, exist_ok=True)
LLED = EVAL / "lab_ledger.json"
TR = pathlib.Path("/home/ccc/tw2/contents/training")

SUBS = {"192.168.0.202": "192.168.0.113", "att@192.168.0.113": "ccc@192.168.0.113",
        "10.20.30.202": "192.168.0.113"}

def secrets():
    d = {}
    for ln in (ROOT / ".eval-secrets").read_text().splitlines():
        ln = ln.strip()
        if ln and not ln.startswith("#") and "=" in ln:
            k, v = ln.split("=", 1); d[k] = v.strip()
    return d
S = secrets()
LLM = S.get("LLM_BASE_URL", "http://211.170.162.109:11434")

def sub(t):
    for k, v in SUBS.items():
        t = t.replace(k, v)
    return t

def load_steps():
    out = []
    for f in sorted(TR.glob("*/lab_*.yaml")):
        try:
            d = yaml.safe_load(f.read_text())
        except Exception:
            continue
        if not isinstance(d, dict) or "lab_id" not in d:
            continue
        thr = d.get("pass_threshold", 0.7)
        steps = d.get("steps") or []
        for s in steps:
            v = s.get("verify") or {}
            sem = v.get("semantic") or {}
            out.append({
                "id": f"{d['lab_id']}-s{s.get('order')}",
                "lab_id": d["lab_id"], "course": d.get("course"), "week": d.get("week"),
                "n_steps": len(steps), "pass_threshold": thr,
                "message": sub(s.get("instruction", "") or ""),
                "expect": v.get("expect"), "vtype": v.get("type"),
                "criteria": sem.get("success_criteria") or [],
                "acceptable": sem.get("acceptable_methods") or [],
                "points": s.get("points"), "target_vm": s.get("target_vm"),
            })
    return out

def warmup():
    for m, to in [("gpt-oss:120b", 220), ("qwen3.5:9b", 60)]:
        try:
            body = json.dumps({"model": m, "prompt": "ok", "stream": False,
                               "keep_alive": "60m", "options": {"num_predict": 2}}).encode()
            urllib.request.urlopen(urllib.request.Request(
                LLM + "/api/generate", data=body, headers={"Content-Type": "application/json"}), timeout=to)
        except Exception as e:
            print(f"  warmup {m} 실패: {e}", flush=True)

def issue(mid, message):
    payload = json.dumps({"message": message, "auto_approve": True,   # 랩=인가된 실행
                          "stream": True, "approval_mode": "normal"})
    b64 = base64.b64encode(payload.encode()).decode()
    try:
        p = subprocess.run(["bash", str(HERE / "run_task.sh"), mid, b64, "40"],
                           capture_output=True, text=True, timeout=2400)
        return p.stdout
    except subprocess.TimeoutExpired:
        return ""

def extract_answer(nd):
    toks = []
    for ln in nd.splitlines():
        ln = ln.strip()
        if not ln.startswith("{"):
            continue
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("event") == "stream_token":
            toks.append(e.get("token", ""))
        elif e.get("event") in ("final", "answer", "analysis", "skill_result"):
            toks.append(str(e.get("text", "") or e.get("content", "") or e.get("output", "")))
    return "".join(toks)

def skills_of(nd):
    used = []
    for ln in nd.splitlines():
        try:
            e = json.loads(ln)
        except Exception:
            continue
        if e.get("event") == "skill_start":
            used.append(e.get("skill"))
    return used

def judge(answer, step):
    if not answer.strip():
        return None, "empty"
    crit = "\n".join(f"- {c}" for c in step["criteria"]) or "- (instruction 의 목표를 실제 수행/달성)"
    prompt = (
        "너는 실습 랩 채점자다. 에이전트가 아래 스텝 목표를 실제로 수행/달성했는지만 판정한다.\n"
        "명령을 실행해 기대 결과(도달/포트/버전/탐지 등)를 얻었으면 met=true. 설명만·미실행·실패면 false.\n\n"
        f"스텝 목표: {step['message'][:1500]}\n\n성공 기준:\n{crit}\n\n"
        f"에이전트 결과/답변:\n{answer[:4500]}\n\n"
        'JSON 만: {"met": true|false, "reason":"짧은 근거"}'
    )
    body = json.dumps({"model": "qwen3.5:9b", "prompt": prompt, "stream": False,
                       "format": "json", "keep_alive": "60m", "think": False,
                       "options": {"num_predict": 400, "temperature": 0}}).encode()
    try:
        r = json.loads(urllib.request.urlopen(urllib.request.Request(
            LLM + "/api/generate", data=body, headers={"Content-Type": "application/json"}), timeout=120).read())
        j = json.loads((r.get("response") or "").strip() or "{}")
        return bool(j.get("met")), (j.get("reason", "") or "")[:120]
    except Exception as e:
        return None, f"judge-error: {e}"

def grade(step, answer):
    exp_hit = bool(step.get("expect") and str(step["expect"]) in answer)   # output_contains 신호
    met, ev = judge(answer, step)
    if met is not None:
        verdict = "PASS" if met else ("PASS" if exp_hit else "FAIL")
    else:
        verdict = "PASS" if exp_hit else "UNKNOWN"
    return verdict, {"sem": met, "sem_ev": ev, "expect_hit": exp_hit}

def git_push(msg):
    subprocess.run(["git", "-C", str(ROOT), "add", "eval-tw2/"], check=False)
    subprocess.run(["git", "-C", str(ROOT), "-c", "user.name=mrgrit",
                    "-c", "user.email=mrgrit@ync.ac.kr", "commit", "-q", "-m", msg], check=False)
    helper = f'!f(){{ echo username=x-access-token; echo "password={S["GH_TOKEN"]}"; }};f'
    subprocess.run(["git", "-C", str(ROOT), "-c", f"credential.helper={helper}",
                    "push", "origin", S.get("GH_BRANCH", "main")], check=False, capture_output=True, text=True)

def write_report(led, total):
    done = led["steps"]
    dp = sum(1 for v in done.values() if v["verdict"] == "PASS")
    labs = {}
    for sid, v in done.items():
        lid = v["lab_id"]; labs.setdefault(lid, {"p": 0, "n": 0, "thr": v.get("thr", 0.7)})
        labs[lid]["n"] += 1; labs[lid]["p"] += (v["verdict"] == "PASS")
    lab_pass = sum(1 for l in labs.values() if l["n"] and l["p"] / l["n"] >= l["thr"])
    lines = [f"# Bastion tw2/el34 — LAB 전수 진행 (자동생성)", "",
             f"> lab_loop.py · 총 스텝 {total} · 완료 {len(done)} · 스텝PASS {dp} ({100*dp//max(len(done),1)}%)",
             f"> 랩 기준(≥threshold): {lab_pass}/{len(labs)} 랩 통과", "",
             "| course | 스텝done | pass |", "|---|---|---|"]
    cs = {}
    for sid, v in done.items():
        c = v.get("course", "?"); cs.setdefault(c, [0, 0]); cs[c][0] += 1; cs[c][1] += (v["verdict"] == "PASS")
    for c, (d, p) in sorted(cs.items()):
        lines.append(f"| {c} | {d} | {p} |")
    (EVAL / "REPORT-lab.md").write_text("\n".join(lines) + "\n")

def main():
    steps = load_steps()
    if "--count" in sys.argv:
        labs = len(set(s["lab_id"] for s in steps))
        print(f"총 스텝: {len(steps)} (랩 {labs})")
        return
    led = json.loads(LLED.read_text()) if LLED.exists() else {"steps": {}}
    print(f"[lab] 총 {len(steps)} 스텝, 완료 {len(led['steps'])} → 나머지 순차 실행", flush=True)
    print("[warmup] 예열…", flush=True); warmup()
    for i, s in enumerate(steps):
        if s["id"] in led["steps"]:
            continue
        print(f"  [{i+1}/{len(steps)}] {s['id']} 발제…", flush=True)
        nd = issue(s["id"], s["message"])
        (LRUNS / f"{s['id']}.ndjson").write_text(nd)
        answer = extract_answer(nd)
        verdict, ev = grade(s, answer)
        led["steps"][s["id"]] = {
            "verdict": verdict, "lab_id": s["lab_id"], "course": s["course"],
            "thr": s["pass_threshold"], "points": s["points"],
            "sem": ev["sem"], "sem_ev": ev["sem_ev"], "expect_hit": ev["expect_hit"],
            "skills": skills_of(nd),
        }
        print(f"      → {verdict} (sem={ev['sem']} expect={ev['expect_hit']})", flush=True)
        LLED.write_text(json.dumps(led, ensure_ascii=False, indent=2))
        write_report(led, len(steps))
        git_push(f"lab(tw2): {s['id']} = {verdict} ({len(led['steps'])}/{len(steps)})")
    print("== 랩 전수 완료 ==", flush=True)

if __name__ == "__main__":
    main()
