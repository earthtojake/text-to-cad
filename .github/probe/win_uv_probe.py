"""TEMPORARY probe (never merged): run a built cadgen wheel the way users do on Windows --
uvx over a uv-managed CPython 3.13, builds through the daemon -- and record what a worker is."""

from __future__ import annotations

import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import textwrap
import threading
import time

wheel = glob.glob(os.path.join(sys.argv[1], "*.whl"))[0]
tmp = pathlib.Path(os.environ["RUNNER_TEMP"]) / "uvprobe"
proj = tmp / "proj"
proj.mkdir(parents=True, exist_ok=True)
env = {
    **os.environ,
    "CADGEN_STATE_DIR": str(tmp / "state"),
    "CADGEN_DAEMON_STATE_DIR": str(tmp / "daemon"),
    "CADGEN_TELEMETRY": "0",
    "PYTHONUNBUFFERED": "1",
}
env.pop("CADGEN_DAEMON", None)
LAUNCH = ["uvx", "--no-config", "--managed-python", "--python", "3.13", "--from", wheel]
failures: list[str] = []


def check(ok: bool, what: str) -> None:
    print(("PASS " if ok else "FAIL ") + what, flush=True)
    if not ok:
        failures.append(what)


def run(*argv: str, timeout: float = 1200) -> subprocess.CompletedProcess:
    print(f"\n$ uvx ... {' '.join(argv)}", flush=True)
    started = time.monotonic()
    result = subprocess.run([*LAUNCH, *argv], cwd=proj, env=env, capture_output=True, text=True, timeout=timeout)
    print(f"[exit {result.returncode} after {time.monotonic() - started:.1f}s]")
    print("--- stdout ---\n" + result.stdout)
    print("--- stderr ---\n" + result.stderr[-6000:], flush=True)
    return result


def processes() -> list[dict]:
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.Name -like 'python*' -or $_.Name -like 'uv*' "
              "-or $_.Name -like 'cadgen*' } | Select-Object ProcessId,ParentProcessId,Name,ExecutablePath,"
              "CommandLine | ConvertTo-Json -Depth 3")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True).stdout
    rows = json.loads(out or "[]")
    return rows if isinstance(rows, list) else [rows]


def last_json(text: str, marker: str) -> dict:
    for line in reversed(text.splitlines()):
        if line.startswith(marker):
            return json.loads(line[len(marker):])
    return {}


# 1. The environment uvx made: its python.exe, pyvenv.cfg, and what the interpreter reports.
INFO = textwrap.dedent('''
    import hashlib, json, os, sys
    exe = sys.executable
    base = getattr(sys, "_base_executable", None)
    data = open(exe, "rb").read()
    launcher = os.path.join(sys.base_prefix, "Lib", "venv", "scripts", "nt", "venvlauncher.exe")
    info = {
        "pid": os.getpid(), "executable": exe, "base_executable": base, "prefix": sys.prefix,
        "base_prefix": sys.base_prefix, "version": sys.version, "exe_size": len(data),
        "exe_sha256": hashlib.sha256(data).hexdigest(),
        "venvlauncher": launcher if os.path.isfile(launcher) else None,
        "venvlauncher_sha256": hashlib.sha256(open(launcher, "rb").read()).hexdigest() if os.path.isfile(launcher) else None,
        "base_python_sha256": hashlib.sha256(open(base, "rb").read()).hexdigest() if base and os.path.isfile(base) else None,
        "uv_markers": [m for m in ("uv-trampoline", "UVUV", "UVSC", "uv_trampoline") if m.encode() in data],
        "pyvenv_cfg": open(os.path.join(sys.prefix, "pyvenv.cfg")).read(),
    }
    print("INFO " + json.dumps(info))
''')
result = run("python", "-c", INFO)
info = last_json(result.stdout, "INFO ")
check(bool(info), "the uv environment's interpreter reported itself")
print(json.dumps(info, indent=2))
if info:
    print("python.exe is CPython's venvlauncher:", info["exe_sha256"] == info["venvlauncher_sha256"])
    print("python.exe is the base python.exe:", info["exe_sha256"] == info["base_python_sha256"])
    ver = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"(Get-Item '{info['executable']}').VersionInfo | Format-List | Out-String"],
                         capture_output=True, text=True).stdout
    print("python.exe VersionInfo:", ver)

# 2. What pool.interpreter() chooses there, started directly: cadgen is in the environment's
# site-packages only (the base is a bare uv-managed CPython), so importing it proves the path.
CHOICE = textwrap.dedent('''
    import json, os, subprocess, sys
    from cadgen.daemon import pool
    program, extra = pool.interpreter()
    print("CHOICE " + json.dumps({"program": program, "env": extra}))
    child = subprocess.run([program, "-P", "-c",
        "import json, os, sys, cadgen; print(json.dumps({'pid': os.getpid(), 'executable': sys.executable,"
        " 'prefix': sys.prefix, 'cadgen': cadgen.__file__}))"],
        env={**os.environ, **extra}, capture_output=True, text=True)
    print("CHILD " + (child.stdout.strip() or json.dumps({"rc": child.returncode, "err": child.stderr[-2000:]})))
''')
result = run("python", "-c", CHOICE)
choice, child = last_json(result.stdout, "CHOICE "), last_json(result.stdout, "CHILD ")
if info:
    check(os.path.normcase(choice.get("program", "")) == os.path.normcase(info["base_executable"] or ""),
          f"interpreter() starts the base interpreter: {choice}")
    check(os.path.normcase(child.get("prefix", "")) == os.path.normcase(info["prefix"]),
          f"the base interpreter told __PYVENV_LAUNCHER__ runs in the uv environment: {child}")
    check(os.path.normcase(child.get("cadgen", "")).startswith(os.path.normcase(info["prefix"])),
          "and imports cadgen from the environment's site-packages")

# 3. Builds through the daemon: a box, then a body that holds the GIL in native code past the
# 120 s silence window (sum over a range is one C loop that never yields the GIL).
# (str.replace below, not format: the model's own braces stay as they are.)
MODEL = textwrap.dedent('''
    import json, os, sys, time
    from cadgen import build123d as bd
    from cadgen import step

    def _report(tag):
        print(tag + " " + json.dumps({"pid": os.getpid(), "ppid": os.getppid(), "executable": sys.executable,
              "prefix": sys.prefix, "launcher": os.environ.get("__PYVENV_LAUNCHER__"),
              "daemon_child": os.environ.get("CADGEN_DAEMON_CHILD")}), flush=True)

    @step(out="{name}.step")
    def {name}():
        _report("WORKER")
        seconds = {seconds}
        if seconds:
            # A float start keeps sum() in its C fast path however large the total grows.
            start = time.perf_counter()
            sum(range(5_000_000), 0.0)
            rate = 5_000_000 / max(time.perf_counter() - start, 1e-6)
            sum(range(int(rate * seconds)), 0.0)
        return bd.Box(10, 10, 10)

    if __name__ == "__main__":
        _report("CLIENT")
        {name}()
''')
(proj / "box.py").write_text(MODEL.replace("{name}", "box").replace("{seconds}", "0"), encoding="utf-8")
(proj / "busy.py").write_text(MODEL.replace("{name}", "busy").replace("{seconds}", "150"), encoding="utf-8")

result = run("python", "box.py")
check(result.returncode == 0 and (proj / "box.step").is_file(), "box.py built box.step through uvx")
box_worker, box_client = last_json(result.stdout, "WORKER "), last_json(result.stdout, "CLIENT ")
print("box worker:", box_worker, "\nbox client:", box_client)
status = last_json("STATUS " + run("cadgen", "daemon", "status", "--json").stdout.strip(), "STATUS ")
print(json.dumps(status, indent=2))
worker_pids = {w.get("pid") for w in status.get("workers") or []}
check(bool(status), "a daemon is running")
check(box_worker.get("pid") not in (None, box_client.get("pid")), "box built in another process than the client (warm)")
check(box_worker.get("pid") in worker_pids, "box built in a pool worker (its pid is an announced worker pid)")
if info:
    check(os.path.normcase(box_worker.get("prefix", "")) == os.path.normcase(info["prefix"]),
          "the box worker's sys.prefix is the uv environment")

snapshot: dict = {}


def sample() -> None:
    time.sleep(60)
    snapshot["processes"] = processes()
    snapshot["status"] = subprocess.run([*LAUNCH, "cadgen", "daemon", "status", "--json"], cwd=proj, env=env,
                                        capture_output=True, text=True, timeout=300).stdout


sampler = threading.Thread(target=sample)
sampler.start()
started = time.monotonic()
result = run("python", "busy.py")
elapsed = time.monotonic() - started
sampler.join()
busy_worker = last_json(result.stdout, "WORKER ")
check(result.returncode == 0 and (proj / "busy.step").is_file(), f"busy.py built busy.step after {elapsed:.0f}s")
check(elapsed > 125, "the busy build ran past the 120 s silence window")
print("processes mid-build:\n" + json.dumps(snapshot.get("processes"), indent=2))
print("status mid-build:", snapshot.get("status"))
rows = {row["ProcessId"]: row for row in snapshot.get("processes") or []}
mid = json.loads(snapshot.get("status") or "{}")
busy_pid = busy_worker.get("pid")
row = rows.get(busy_pid)
check(row is not None, f"the busy worker {busy_pid} was running mid-build")
if row and info:
    check(os.path.normcase(row.get("ExecutablePath") or "") == os.path.normcase(info["base_executable"]),
          f"the worker process is the base interpreter itself: {row.get('ExecutablePath')}")
    check(row.get("ParentProcessId") == mid.get("pid"),
          f"the worker's parent is the daemon ({row.get('ParentProcessId')} vs daemon {mid.get('pid')}): one process")
    children = [r for r in rows.values() if r.get("ParentProcessId") == busy_pid]
    check(not children, f"the worker has no child interpreter: {children}")

final = json.loads(run("cadgen", "daemon", "status", "--json").stdout.strip() or "{}")
print(json.dumps(final, indent=2))
check(final.get("crashes", 0) == 0, f"the daemon counted no crash: {final.get('crashes')}")

for log in pathlib.Path(env["CADGEN_DAEMON_STATE_DIR"]).glob("*.log"):
    text = log.read_text(encoding="utf-8", errors="replace")
    print(f"\n--- {log} ---\n{text[-8000:]}")
    check("WorkerDied" not in text and "WorkerGone" not in text, f"{log.name} reports no dead worker")

if final.get("pid"):
    subprocess.run(["taskkill", "/PID", str(final["pid"]), "/T", "/F"])
print("\nFAILURES:", failures or "none")
sys.exit(1 if failures else 0)
