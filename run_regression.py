"""Janus-gateable regression run for the Astral Sorcery port: logic + rendering in one verdict.

Ties together the two halves of a correct mod-test strategy:
  * LOGIC  — the port's OWN headless in-engine tests (Forge GameTestServer). Deterministic, no
             external bot, no FML-handshake problem; runs inside the mod so it sees block entities,
             starlight networks, multiblock assembly, recipes. Exit code = failed tests.
  * RENDER — vfx_qa.py: a LOCAL vision model audits screenshots for AS's render-port failure modes
             (missing textures, shader corruption, beam/constellation/particle glitches).

Emits ONE machine report (regression-*.json) with an overall pass/fail that Janus / the WPAI
blackboard can gate on. This script only READS the workload and invokes its gradle task — it does not
mutate the registered `astral-sorcery-port` workload (that stays a Janus-receipt path).

    python run_regression.py --port "C:/WPAI/Gaming/Minecraft/Mods-1.20.1-Forge/Astral_Sorcery_Port" \
                             --frames "C:/Users/<you>/.minecraft/screenshots" --scenario beam
    python run_regression.py --port <...> --skip-render      # logic only
    python run_regression.py --frames <...> --skip-logic     # render only (fast)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass

HERE = os.path.dirname(os.path.abspath(__file__))


def run_gametests(port: str, timeout: int) -> dict:
    """Invoke Forge's headless GameTestServer via the port's gradle wrapper."""
    gradlew = os.path.join(port, "gradlew.bat" if os.name == "nt" else "gradlew")
    if not os.path.isfile(gradlew):
        return {"stage": "logic", "status": "ERROR", "detail": f"gradlew not found in {port}"}
    # ForgeGradle exposes the `gameTestServer` run config as the `runGameTestServer` task.
    cmd = [gradlew, "runGameTestServer", "--console=plain", "-q"]
    print(f"  [logic] running headless GameTestServer  ({' '.join(cmd[1:])})  — this compiles the mod...")
    t0 = time.time()
    try:
        p = subprocess.run(cmd, cwd=port, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"stage": "logic", "status": "ERROR", "detail": f"timed out after {timeout}s"}
    secs = round(time.time() - t0, 1)
    tail = "\n".join((p.stdout or "").splitlines()[-25:])
    ok = p.returncode == 0   # GameTestServer exit code == number of failed required tests
    return {"stage": "logic", "status": "PASS" if ok else "FAIL",
            "exit_code": p.returncode, "secs": secs, "log_tail": tail}


def run_render(frames: str, model: str, scenario: str) -> dict:
    if not os.path.isdir(frames):
        return {"stage": "render", "status": "ERROR", "detail": f"frames dir not found: {frames}"}
    out = os.path.join(HERE, f"vfx-report-{time.strftime('%Y%m%d-%H%M%S')}.json")
    cmd = [sys.executable, os.path.join(HERE, "vfx_qa.py"), "--dir", frames,
           "--model", model, "--scenario", scenario, "--out", out]
    print(f"  [render] auditing frames in {frames} with {model} (local)...")
    p = subprocess.run(cmd, text=True)
    detail = {}
    if os.path.isfile(out):
        with open(out, encoding="utf-8") as f:
            detail = json.load(f)
    return {"stage": "render", "status": "PASS" if p.returncode == 0 else "FAIL",
            "fail_count": p.returncode, "report": out,
            "summary": {"pass": detail.get("pass"), "fail": detail.get("fail")}}


def main() -> None:
    ap = argparse.ArgumentParser(description="AS port regression: logic (GameTest) + render (local VLM)")
    ap.add_argument("--port", default="C:/WPAI/Gaming/Minecraft/Mods-1.20.1-Forge/Astral_Sorcery_Port")
    ap.add_argument("--frames", default=None, help="screenshot folder for render QA")
    ap.add_argument("--model", default=os.environ.get("VFX_VLM_MODEL", "qwen2.5vl:7b"))
    ap.add_argument("--scenario", default="general")
    ap.add_argument("--skip-logic", action="store_true")
    ap.add_argument("--skip-render", action="store_true")
    ap.add_argument("--logic-timeout", type=int, default=1800)
    args = ap.parse_args()

    print(f"AS PORT REGRESSION  {time.strftime('%Y-%m-%d %H:%M:%S')}")
    stages = []
    if not args.skip_logic:
        stages.append(run_gametests(args.port, args.logic_timeout))
    if not args.skip_render:
        if not args.frames:
            print("  [render] skipped — no --frames given")
        else:
            stages.append(run_render(args.frames, args.model, args.scenario))

    overall = "PASS" if stages and all(s["status"] == "PASS" for s in stages) else \
              ("ERROR" if any(s["status"] == "ERROR" for s in stages) else "FAIL")
    report = {"overall": overall, "stages": stages, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
              "workload": "astral-sorcery-port"}
    out = os.path.join(HERE, f"regression-{time.strftime('%Y%m%d-%H%M%S')}.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print("\n────────── REGRESSION ──────────")
    for s in stages:
        print(f"  {s['stage']:<7} {s['status']}"
              + (f"  (exit {s.get('exit_code')}, {s.get('secs')}s)" if s["stage"] == "logic" else "")
              + (f"  ({s['summary']['pass']} pass / {s['summary']['fail']} fail)"
                 if s["stage"] == "render" and s.get("summary", {}).get("pass") is not None else ""))
    print(f"  OVERALL: {overall}   -> {out}")
    # nonzero exit for any non-PASS so a Janus/CI gate can consume it directly
    sys.exit(0 if overall == "PASS" else 1)


if __name__ == "__main__":
    main()
