"""Time the same parts built three ways: B-rep only (build123d through @step/@glb),
SDF only (an implicit part meshed to GLB) and combined (the implicit part with its
STEP exported). Every cold run is a fresh process with a fresh cadgen store.

    ./.venv/bin/python scripts/bench/implicit-vs-brep/run.py            # 3 runs each
    BENCH_RUNS=5 ./.venv/bin/python scripts/bench/implicit-vs-brep/run.py

Outputs, logs and the results JSON go to tmp/bench-implicit/ (ignored). The part
scripts in parts/ are copied there first, so their relative outputs land beside
the copy and the checkout stays clean.
"""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
PY = sys.executable
PARTS = ("housing", "enclosure", "knob")
METHODS = ("brep", "sdf", "hybrid")
RUNS = int(os.environ.get("BENCH_RUNS", "3"))
WORK = ROOT / "tmp" / "bench-implicit"


def run(script: Path, cache: Path, extra=()) -> tuple[float, str, str]:
    env = dict(os.environ, PYTHONPATH=str(ROOT / "packages" / "cadgen" / "src"), CADGEN_DAEMON="0", CADGEN_CACHE_DIR=str(cache))
    started = time.perf_counter()
    done = subprocess.run([PY, str(script), *extra], cwd=script.parent.parent, env=env, capture_output=True, text=True)
    return time.perf_counter() - started, done.stdout, done.stderr


def size(path: Path) -> int:
    return path.stat().st_size if path.exists() else 0


def main() -> None:
    shutil.rmtree(WORK, ignore_errors=True)
    (WORK / "src").mkdir(parents=True)
    (WORK / "out").mkdir()
    for script in (HERE / "parts").glob("*.py"):
        shutil.copy(script, WORK / "src" / script.name)
    results: dict = {"runs": RUNS, "parts": {}, "kernel_import_s": None, "scaling": []}
    started = time.perf_counter()
    subprocess.run([PY, "-c", "from cadgen import build123d as bd; bd.Box(1, 1, 1)"], env=dict(os.environ, PYTHONPATH=str(ROOT / "packages/cadgen/src")), capture_output=True)
    results["kernel_import_s"] = time.perf_counter() - started
    for part in PARTS:
        results["parts"][part] = {}
        for method in METHODS:
            script = WORK / "src" / f"{part}_{method}.py"
            cold, warm, notes = [], [], set()
            for _ in range(RUNS):
                cache = Path(tempfile.mkdtemp(prefix="bench-cache-"))
                for stale in (WORK / "out").glob(f"{part}_{method}.*"):
                    stale.unlink()
                seconds, _, err = run(script, cache)
                if "Traceback" in err:
                    notes.add(err.strip().splitlines()[-1][:160])
                if "shell failed" in err:
                    notes.add("B-rep shell failed in OCC; part built solid")
                if "left sharp" in err or "refused every fillet" in err:
                    notes.add("OCC refused the blend fillet; STEP has that join sharp")
                if "no STEP" in err:
                    notes.add("no STEP: " + err.split("no STEP", 1)[1].strip().splitlines()[0][:120])
                cold.append(seconds)
                warm.append(run(script, cache)[0])
                shutil.rmtree(cache, ignore_errors=True)
            glb, step = WORK / "out" / f"{part}_{method}.glb", WORK / "out" / f"{part}_{method}.step"
            results["parts"][part][method] = {
                "cold_s": statistics.median(cold), "cold_runs": cold, "warm_s": statistics.median(warm), "warm_runs": warm,
                "glb_bytes": size(glb), "step_bytes": size(step), "notes": sorted(notes),
            }
            print(f"{part:10s} {method:7s} cold {statistics.median(cold):6.2f}s warm {statistics.median(warm):6.2f}s "
                  f"glb {size(glb) // 1024:6d} KB step {size(step) // 1024:5d} KB {'; '.join(sorted(notes))}", flush=True)
    for resolution in (1.0, 0.5, 0.35, 0.25, 0.18):
        cache = Path(tempfile.mkdtemp(prefix="bench-cache-"))
        seconds, out, _ = run(WORK / "src" / "housing_sdf.py", cache, ("--resolution", str(resolution), "--json"))
        triangles = json.loads(out.strip().splitlines()[-1]).get("triangles") if out.strip() else None
        results["scaling"].append({"resolution": resolution, "seconds": seconds, "triangles": triangles})
        print(f"housing sdf at {resolution}: {seconds:.2f}s, {triangles} triangles", flush=True)
        shutil.rmtree(cache, ignore_errors=True)
    (WORK / "results.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
    print("wrote", WORK / "results.json")


if __name__ == "__main__":
    main()
