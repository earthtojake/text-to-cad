"""Where the core's time goes, and what a cheaper variant changes. Builds with -DVC_PROFILE export vc_profile.

    python tools/profile.py run [--native LIB.so | --wasm MODULE.wasm] [--runs 2] OUT.json FILE.xbf [...]
    python tools/profile.py diff BASE_DIR VARIANT_DIR [MODEL ...]
    python tools/profile.py table OUT.json [...]

`run` opens each document, then per stage asks every distinct key in turn (a bundle's order: mesh, elements, measure;
then groups alone and the picks of a page, each on a fresh document) and records the stage's wall time and the
profile's seconds per category (each category its own time: they add up to the stage). `diff` says, field by field,
how a variant's answers (tools/smoke.py's folder) differ from the default's: values that differ, the largest
difference, keys missing or added. `table` prints each category's seconds and share per stage, the runs' median.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from smoke import HERE, Core, NativeCore  # noqa: E402

STAGES = ("mesh", "elements", "measure")


def profile(core) -> dict:
    data = core.result("vc_profile")
    return json.loads(data)


def run(core, path: Path, picks: int) -> dict:
    data = path.read_bytes()
    doc = core.open(data)
    structure = json.loads(core.result("vc_structure", doc))
    keys: dict[str, int] = {}
    for prototype in structure["prototypes"]:
        keys.setdefault(prototype["key"], prototype["index"])
    parts = list(keys.values())
    found = {"open": profile(core)}
    stages, sizes = {}, {}
    for stage in STAGES:
        bodies = {}
        t = time.perf_counter()
        for index in parts:
            bodies[index] = core.result(f"vc_{stage}", doc, index)
        stages[stage] = time.perf_counter() - t
        found[stage] = profile(core)
        if stage == "elements":
            for index, body in bodies.items():
                table = json.loads(body)
                sizes[index] = [len(table[kind]) for kind in ("faces", "edges", "vertices")]
    core.call("vc_close", doc)
    # groups alone, as a page asks them, on a document of its own (nothing kept from the stages above)
    doc = core.open(data)
    profile(core)
    t = time.perf_counter()
    for index in parts:
        core.result("vc_groups", doc, index)
    stages["groups"] = time.perf_counter() - t
    found["groups"] = profile(core)
    core.call("vc_close", doc)
    # a page's picks on a fresh document: random elements of random parts, a part's first pick reading its topology
    doc = core.open(data)
    profile(core)
    rng = random.Random(1)
    cold, warm, seen = [], [], set()
    t = time.perf_counter()
    for _ in range(picks):
        index = rng.choice(parts)
        kind = rng.choice([k for k in range(3) if sizes[index][k]])
        ordinal = rng.randint(1, sizes[index][kind])
        t0 = time.perf_counter()
        core.result("vc_fact", doc, index, kind, ordinal)
        (warm if index in seen else cold).append(time.perf_counter() - t0)
        seen.add(index)
    stages["picks"] = time.perf_counter() - t
    found["picks"] = profile(core)
    core.call("vc_close", doc)
    switches = found["elements"].get("switches", [])
    for value in found.values():
        value.pop("switches", None)
    return {"file": path.name, "switches": switches, "stages": stages, "profile": found,
            "pick_cold_median_s": statistics.median(cold) if cold else None,
            "pick_warm_median_s": statistics.median(warm) if warm else None}


def diff_values(a, b, path: str, out: dict) -> None:
    name = "/".join(part for part in path.split("/") if part and not part.isdigit())
    if isinstance(a, dict) and isinstance(b, dict):
        for k in a.keys() - b.keys():
            out[f"{name}/{k}"]["missing"] += 1
        for k in b.keys() - a.keys():
            out[f"{name}/{k}"]["added"] += 1
        for k in a.keys() & b.keys():
            diff_values(a[k], b[k], f"{path}/{k}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out[name]["length"] += 1
        for x, y in zip(a, b):
            diff_values(x, y, path, out)
    else:
        entry = out[name]
        entry["values"] += 1
        if a != b:
            entry["differ"] += 1
            if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                d = abs(a - b)
                entry["max_abs"] = max(entry.get("max_abs", 0.0), d)
                entry["max_rel"] = max(entry.get("max_rel", 0.0), d / max(abs(a), abs(b), 1e-300))
            elif len(entry.setdefault("examples", [])) < 3:
                entry["examples"].append([a, b])


def diff(base: Path, variant: Path, models: list[str]) -> dict:
    report = {}
    for model in models:
        for name in ("elements.json", "groups.json", "measure.json"):
            fields: dict = defaultdict(lambda: defaultdict(int))
            for part in (base / model / "parts").iterdir():
                a = json.loads((part / name).read_bytes())
                b = json.loads((variant / model / "parts" / part.name / name).read_bytes())
                diff_values(a, b, "", fields)
            for field, entry in fields.items():
                total = report.setdefault(f"{name}:{field}", defaultdict(float))
                for k, v in entry.items():
                    if k == "examples":
                        total.setdefault("examples", v)
                    elif k.startswith("max"):
                        total[k] = max(total[k], v)
                    else:
                        total[k] += v
        mesh_same = all((part / "mesh.xbm").read_bytes() == (variant / model / "parts" / part.name / "mesh.xbm").read_bytes()
                        for part in (base / model / "parts").iterdir())
        report.setdefault("mesh.xbm identical in", []).append(model) if mesh_same else None
    return {k: dict(v) if isinstance(v, dict) else v for k, v in report.items()
            if not isinstance(v, dict) or v.get("differ") or v.get("missing") or v.get("added") or v.get("length")}


def table(results: list[dict]) -> None:
    by = defaultdict(list)
    for r in results:
        by[(r["file"], tuple(r["switches"]), r.get("host", "?"))].append(r)
    for (file, switches, host), runs in by.items():
        print(f"\n== {file} {host} {' '.join(switches) or 'default'} ({len(runs)} runs)")
        for stage in ("open",) + STAGES + ("groups", "picks"):
            wall = [r["stages"].get(stage) for r in runs if stage in r["stages"]]
            cats = defaultdict(list)
            for r in runs:
                for name, (seconds, count) in r["profile"].get(stage, {}).items():
                    cats[name].append(seconds)
            total = sum(statistics.median(v) for v in cats.values())
            head = f"  {stage}: wall {statistics.median(wall):.3f}s" if wall else f"  {stage}:"
            print(f"{head}  profiled {total:.3f}s")
            for name, values in sorted(cats.items(), key=lambda item: -statistics.median(item[1])):
                m = statistics.median(values)
                if total and m / total >= 0.002:
                    print(f"    {name:22s} {m:8.3f}s {100 * m / total:5.1f}%   runs {' '.join(f'{v:.3f}' for v in values)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--native", type=Path)
    r.add_argument("--wasm", type=Path, default=HERE / "dist" / "viewcore-profile.wasm")
    r.add_argument("--runs", type=int, default=2)
    r.add_argument("--picks", type=int, default=100)
    r.add_argument("out", type=Path)
    r.add_argument("files", type=Path, nargs="+")
    d = sub.add_parser("diff")
    d.add_argument("base", type=Path)
    d.add_argument("variant", type=Path)
    d.add_argument("models", nargs="*")
    t = sub.add_parser("table")
    t.add_argument("results", type=Path, nargs="+")
    args = parser.parse_args()
    if args.command == "run":
        results = json.loads(args.out.read_text()) if args.out.exists() else []
        for _ in range(args.runs):
            for name in args.files:
                core = NativeCore(args.native) if args.native else Core(args.wasm)
                found = run(core, name.resolve(), args.picks)
                found["host"] = f"native:{args.native.name}" if args.native else f"wasm:{args.wasm.name}"
                results.append(found)
                print(json.dumps({"file": found["file"], "host": found["host"], "switches": found["switches"],
                                  **{k: round(v, 4) for k, v in found["stages"].items()}}), flush=True)
                args.out.write_text(json.dumps(results))
    elif args.command == "diff":
        models = args.models or sorted(p.name for p in args.base.iterdir() if (p / "parts").exists())
        print(json.dumps(diff(args.base, args.variant, models), indent=1))
    else:
        table([r for path in args.results for r in json.loads(path.read_text())])
