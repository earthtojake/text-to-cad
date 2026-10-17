#!/usr/bin/env python3
"""Compare cold builds, and optionally the moonwatch edit loop, between two commits, interleaved.

The 0.8.0 migration's stage gate (see "The 0.8.0 migration measurements" in
scripts/bench/README.md). Each commit gets a detached worktree of its own under the output
directory, with this checkout's built runtime (packages/cadgen/src/cadgen/_runtime, from
scripts/bundle/bundle.sh) copied in. Every run executes that worktree's own sources and models:
the active venv's Python with PYTHONPATH on the worktree's packages/cadgen/src, a fresh store,
no daemon. Runs alternate base and head, and the order flips every round, so drift on a shared
machine falls on both sides alike. The worktrees are removed when the harness exits.

usage: scripts/bench/compare_commits.py --base REV --head REV [--rounds N] [--models a,b,c]
                                        [--edits] [--out NAME] [--max-load L]
                                        [--edit-iterations N]

  --base REV         the commit the comparison starts from: any git revision (main, a tag, a sha)
  --head REV         the commit compared against it
  --rounds N         rounds of cold builds; each round builds every model once per side (default 2)
  --models a,b,c     the cold-build models: names from MODELS below, or a model script's path
                     relative to the checkout (default aft,nozzles,dial; moonwatch is the whole
                     watch, about ten minutes per cold build)
  --edits            also run the moonwatch edit loop (scripts/bench/cadgen-performance/
                     agent_edits.py) on each side, after the cold builds: about 25 minutes per
                     side on a four-core machine
  --out NAME         the output directory: a name under tmp/bench/, or a path (default compare)
  --max-load L       before each edit-loop run, wait for the one-minute load average to fall
                     below L (default: no waiting)
  --edit-iterations N  iterations of each edit scenario (default 2)

Output, under the output directory:
  runs.jsonl                  one line per cold build: round, side, model, status, wall, load and
                              the numbers its output gave: built, model_code, cadgen
  <side>-<model>-<round>.log  that build's --verbose output
  edits-<side>.json, .out,    the edit loop's report, output and per-run logs
  edits-<side>-logs/
  table.md                    the comparison, printed at the end as well

What table.md's numbers mean, all medians over the rounds: wall is the command from start to
exit; built is cadgen's own total for the root model: its "built ... in" line, else the
"generated <script> completed in" line, the one cadgen 0.7 prints; model code is the seconds
inside the model's own Python and cadgen is the rest of built (kernel, store, export), both from
the "built ... in" line alone, so a side that prints none shows a dash there and a footnote
names what it could not report; load is the one-minute load average when each run started;
failures counts runs that exited non-zero or printed neither line (read their logs).

With --edits, per scenario, from the root model's own events in the run's log (its children
report too, so only its file's events count): the seconds into its run at which its source was
ready (its preview is published then), at which it was done (or current: nothing to build) and
at which its STEP was saved, as the STEP saved event 0.7 prints before the done or the "STEP
saved <file> completed in" line 0.8.0 prints after it; a dash where no run of the scenario has
the mark (a run that writes no file saves none). Then the edit loop's own table, the median wall
per scenario (agent_edits.py --compare): a revert on 0.8.0 is a restore, outcome current.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "packages/cadgen/src/cadgen/_runtime"
MODELS = {
    "aft": "models/f14d/src/aft.py",
    "nozzles": "models/f14d/src/nozzles.py",
    "dial": "models/moonwatch/src/dial.py",
    "moonwatch": "models/moonwatch/src/moonwatch.py",
}
# The moonwatch edit loop: a leaf dimension, a parent placement literal and the root's label.
EDIT_LOOP = [
    "--leaf-from", "INDEX_RAISE = 0.18", "--leaf-to", "INDEX_RAISE = 0.19", "--leaf-to", "INDEX_RAISE = 0.2",
    "--parent-from", "MOVT_Z_OFFSET), (1", "--parent-to", "MOVT_Z_OFFSET + 0.01), (1",
    "--parent-to", "MOVT_Z_OFFSET + 0.02), (1",
    "--label-from", 'label="moonwatch")', "--label-to", 'label="watch")', "--label-to", 'label="moonwatch_2")',
]
# What a build says about the root model's total. cadgen 0.8.0 prints
# `built <STEP> in 13.4s: model code 7.2s, cadgen 6.2s` (all three numbers); every cadgen prints
# `generated <script> completed in 6.70s` (the total alone), and 0.7 prints nothing else.
BUILT = re.compile(r"built (\S+) in ([^:\n]+): model code ([^,\n]+), cadgen ([^,\n]+)")
GENERATED = re.compile(r"generated (\S+) completed in (.+)")
# When a file landed, as cadgen 0.8.0 says it with --verbose (0.7 has the event instead).
SAVED = re.compile(r"^\[cadgen\] STEP saved (\S+) completed in (.+)$", re.MULTILINE)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True).stdout.strip()


def venv_python() -> Path:
    """The active venv's interpreter: the activated one, this one when it is a venv's, else this
    checkout's .venv. The harness itself needs only the standard library; the builds need the
    kernel, which that interpreter must import."""
    candidates = []
    if os.environ.get("VIRTUAL_ENV"):
        candidates.append(Path(os.environ["VIRTUAL_ENV"]) / "bin" / "python")
    if sys.prefix != sys.base_prefix:
        candidates.append(Path(sys.executable))
    candidates.append(ROOT / ".venv" / "bin" / "python")
    python = next((path for path in candidates if path.is_file()), None)
    if python is None:
        sys.exit("no venv found: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt")
    probe = subprocess.run([str(python), "-c", "import importlib.util, sys; sys.exit(0 if importlib.util.find_spec('build123d') else 1)"])
    if probe.returncode != 0:
        sys.exit(f"{python} cannot import the CAD kernel: {python.parent}/pip install -r requirements-dev.txt")
    return python


def seconds(text: str) -> float:
    """'1m16s', '29.1s', '809ms', '1m 16.4s' -> seconds."""
    text = text.strip()
    if text.endswith("ms") and "m" not in text[:-2]:
        return float(text[:-2]) / 1000
    total = 0.0
    for value, unit in re.findall(r"([\d.]+)\s*(ms|m|s)", text):
        total += float(value) * {"ms": 0.001, "m": 60.0, "s": 1.0}[unit]
    return total


def remove_worktree(path: Path) -> None:
    if path.exists():
        removed = subprocess.run(["git", "-C", str(ROOT), "worktree", "remove", "--force", str(path)],
                                 capture_output=True, text=True)
        shutil.rmtree(path, ignore_errors=True)
        if path.exists():
            print(f"could not remove {path}: {removed.stderr.strip()}", file=sys.stderr)
    subprocess.run(["git", "-C", str(ROOT), "worktree", "prune"], capture_output=True)


def worktree(python: Path, sha: str, path: Path) -> Path:
    """A detached worktree of `sha` at `path`, with this checkout's built runtime copied in, whose
    cadgen is what `python` imports with PYTHONPATH on it (never the venv's installed one)."""
    remove_worktree(path)
    git("worktree", "add", "--detach", str(path), sha)
    shutil.copytree(RUNTIME, path / "packages/cadgen/src/cadgen/_runtime")
    probe = subprocess.run([str(python), "-c", "import cadgen; print(cadgen.__file__)"],
                           env={**os.environ, "PYTHONPATH": str(path / "packages/cadgen/src")},
                           capture_output=True, text=True)
    found = Path(probe.stdout.strip() or "/")
    if probe.returncode != 0 or not found.is_relative_to(path):
        sys.exit(f"{python} imports cadgen from {found if probe.returncode == 0 else probe.stderr.strip()}, "
                 f"not from {path}")
    return path


def reported(output: str, stem: str) -> dict:
    """The numbers a build's output gives for the root model `stem`: `built` from the `built ... in`
    line, with the `model_code` and `cadgen` only that line gives, else `built` from the
    `generated <script> completed in` line; empty when it prints neither."""
    lines = [m for m in BUILT.finditer(output) if Path(m.group(1)).stem == stem]
    if lines:
        return {"built": round(seconds(lines[-1].group(2)), 2), "model_code": round(seconds(lines[-1].group(3)), 2),
                "cadgen": round(seconds(lines[-1].group(4)), 2)}
    lines = [m for m in GENERATED.finditer(output) if Path(m.group(1).split("::")[0]).stem == stem]
    return {"built": round(seconds(lines[-1].group(2)), 2)} if lines else {}


def cold(python: Path, tree: Path, model: str, log: Path, store: Path) -> dict:
    """One cold build of `model` from `tree`'s sources: fresh store, no daemon, --verbose."""
    script = tree / MODELS.get(model, model)
    env = {**os.environ, "PYTHONPATH": str(tree / "packages/cadgen/src"), "CADGEN_CACHE_DIR": str(store),
           "CADGEN_DAEMON": "0", "CADGEN_TELEMETRY": "0", "CADGEN_UPDATE_CHECK": "0"}
    load = os.getloadavg()[0]
    start = time.perf_counter()
    proc = subprocess.run([str(python), script.name, "--verbose"], cwd=script.parent, env=env,
                          capture_output=True, text=True, errors="replace")
    wall = time.perf_counter() - start
    output = proc.stdout + proc.stderr
    log.write_text(output, encoding="utf-8")
    row = {"model": script.stem, "status": proc.returncode, "wall": round(wall, 2), "load": round(load, 2),
           **reported(output, script.stem)}
    if proc.returncode != 0 or "built" not in row:
        print(f"  {script.stem} from {tree.name}: status {proc.returncode}, "
              f"{'no built or generated line' if 'built' not in row else 'built'}; see {log}", file=sys.stderr)
    return row


def median(rows: list[dict], key: str) -> str:
    """The median of `key` over the rows that have it, one decimal; a dash when none does."""
    values = [r[key] for r in rows if key in r]
    return f"{statistics.median(values):.1f}" if values else "—"


def cold_table(rows: list[dict], models: list[str]) -> list[str]:
    """The cold builds' table, medians over the rounds. A number a side's build did not print is a
    dash, not a failure (that is a run that exited non-zero or printed no total), and a footnote
    names it."""
    lines = ["| model | side | wall | built | model code | cadgen | load | failures |",
             "|---|---|---:|---:|---:|---:|---:|---:|"]
    dashes: dict[str, list[str]] = {"base": [], "head": []}
    for model in models:
        name = Path(MODELS.get(model, model)).stem
        for side in dashes:
            mine = [r for r in rows if r["model"] == name and r["side"] == side]
            ok = [r for r in mine if r["status"] == 0 and "built" in r]
            for key, label in (("model_code", "model code"), ("cadgen", "cadgen")):
                if ok and not any(key in r for r in ok) and label not in dashes[side]:
                    dashes[side].append(label)
            lines.append(f"| {name} | {side} | {median(ok, 'wall')} | {median(ok, 'built')} | {median(ok, 'model_code')} | "
                         f"{median(ok, 'cadgen')} | {median(mine, 'load')} | {len(mine) - len(ok)} |")
    named = "; ".join(f"{side}: {', '.join(labels)}" for side, labels in dashes.items() if labels)
    if named:
        lines += ["", f"— is a number that side's build does not print ({named}): only cadgen 0.8.0's `built ... in` line "
                      "gives model code and cadgen, so that side's built is its `generated ... completed in` line."]
    return lines


def edits(python: Path, tree: Path, side: str, out: Path, iterations: int, max_load: float | None) -> Path:
    """The repository's edit-loop benchmark on a disposable moonwatch copy of this side's sources."""
    work = out / f"edits-{side}"
    shutil.rmtree(work, ignore_errors=True)
    (work / "moonwatch").mkdir(parents=True)
    shutil.copytree(tree / "models/moonwatch/src", work / "moonwatch/src")
    report = out / f"edits-{side}.json"
    command = [str(python), str(tree / "scripts/bench/cadgen-performance/agent_edits.py"),
               "--configuration", side, "--model", str(work / "moonwatch/src/moonwatch.py"),
               "--store", str(work / "store"), "--daemon-socket", f"/tmp/cgb-{side}-{os.getpid()}.sock",
               "--cadgen-src", str(tree / "packages/cadgen/src"),
               "--leaf-model", str(work / "moonwatch/src/lib/dial.py"), *EDIT_LOOP,
               "--report", str(report), "--iterations", str(iterations)]
    node = shutil.which("node")  # a checkout whose cadgen exports meshes through Node finds it here
    if node:
        command += ["--node-bin", str(Path(node).parent)]
    if max_load is not None:
        command += ["--max-load", str(max_load)]
    with open(out / f"edits-{side}.out", "w", encoding="utf-8") as sink:
        proc = subprocess.run(command, stdout=sink, stderr=subprocess.STDOUT)
    if proc.returncode != 0:
        print(f"  edit loop on {side}: status {proc.returncode}; see {out / f'edits-{side}.out'}", file=sys.stderr)
    return report


def milestones(logs: Path, root: str) -> dict[str, list[dict]]:
    """Per scenario, from each run's log (agent_edits.py names them NN-<scenario>-<iteration>.log),
    the seconds into the root model's own run at which its source was ready (its preview is
    published then), at which it was done (or current: nothing to build) and at which its STEP was
    saved; a mark a run does not have is missing. Only the model whose file is `root` counts: its
    children's events say the same things, and under 0.8.0 a current child reports itself with no
    parent, so the first event of a phase is not the root's. 0.7 prints the root's STEP saved event
    before its done; 0.8.0 prints a `STEP saved <file> completed in` line after it."""
    found: dict[str, list[dict]] = {}
    for log in sorted(logs.glob("*.log")):
        scenario = log.stem.split("-", 1)[1].rsplit("-", 1)[0]
        text = log.read_text(encoding="utf-8", errors="replace")
        mark: dict[str, float] = {}
        for line in text.splitlines():
            if not line.startswith("{"):
                continue
            try:
                event = json.loads(line)
            except ValueError:
                continue
            at = event.get("elapsed")
            if Path(str(event.get("model") or "").split("::")[0]).name != root or not isinstance(at, (int, float)):
                continue
            if event.get("phase") == "Source ready":
                mark.setdefault("preview", at)
            if event.get("state") in ("done", "current"):
                mark.setdefault("done", at)
            if event.get("phase") == "STEP saved" and event.get("state") == "building":
                mark.setdefault("saved", at)
        for name, value in SAVED.findall(text):
            if name == f"{Path(root).stem}.step":
                mark.setdefault("saved", seconds(value))
        found.setdefault(scenario, []).append(mark)
    return found


def milestone_table(marks: dict[str, dict[str, list[dict]]]) -> list[str]:
    """The root model's marks per edit scenario, in the order the loop ran them: medians over the
    iterations, a dash where no run of the scenario has the mark."""
    lines = ["| scenario | base preview | head preview | base done | head done | base saved | head saved |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for scenario in dict.fromkeys([*marks["base"], *marks["head"]]):
        cells = [median(marks[side].get(scenario, []), key) for key in ("preview", "done", "saved")
                 for side in ("base", "head")]
        lines.append(f"| {scenario} | " + " | ".join(cells) + " |")
    return lines


def output_dir(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute() and len(path.parts) == 1:
        path = ROOT / "tmp/bench" / path
    return path.resolve()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--base", required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--models", default="aft,nozzles,dial")
    parser.add_argument("--edits", action="store_true")
    parser.add_argument("--out", default="compare")
    parser.add_argument("--max-load", type=float)
    parser.add_argument("--edit-iterations", type=int, default=2)
    args = parser.parse_args()
    if not (RUNTIME / "native").is_dir():
        sys.exit(f"the packaged runtime is not built ({RUNTIME}): scripts/bundle/bundle.sh")
    python = venv_python()
    sides = {"base": git("rev-parse", "--verify", f"{args.base}^{{commit}}"),
             "head": git("rev-parse", "--verify", f"{args.head}^{{commit}}")}
    models = [m for m in args.models.split(",") if m]
    for model in models:
        if model not in MODELS and not (ROOT / model).is_file():
            parser.error(f"unknown model {model!r}: one of {', '.join(MODELS)}, or a script's path in the checkout")
    out = output_dir(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"base {sides['base'][:9]} ({args.base})  head {sides['head'][:9]} ({args.head})  "
          f"python {python}  out {out}", flush=True)
    trees = {}
    try:
        for side, sha in sides.items():
            trees[side] = worktree(python, sha, out / f"wt-{side}")
        rows = []
        with open(out / "runs.jsonl", "w", encoding="utf-8") as runs:
            for round_ in range(args.rounds):
                order = ["base", "head"] if round_ % 2 == 0 else ["head", "base"]
                for model in models:
                    for side in order:
                        name = Path(MODELS.get(model, model)).stem
                        with tempfile.TemporaryDirectory(prefix="store-", dir=out) as store:
                            row = {"round": round_, "side": side,
                                   **cold(python, trees[side], model, out / f"{side}-{name}-{round_}.log", Path(store))}
                        rows.append(row)
                        runs.write(json.dumps(row) + "\n")
                        runs.flush()
                        print(json.dumps(row), flush=True)
        lines = [f"base {sides['base'][:9]} ({args.base})  head {sides['head'][:9]} ({args.head})  "
                 f"rounds {args.rounds}  {platform.platform()}  {os.cpu_count()} cores", "",
                 *cold_table(rows, models)]
        if args.edits:
            reports = {side: edits(python, trees[side], side, out, args.edit_iterations, args.max_load)
                       for side in ("base", "head")}
            marks = {side: milestones(out / f"edits-{side}-logs", Path(MODELS["moonwatch"]).name)
                     for side in ("base", "head")}
            lines += ["", "moonwatch edit loop, the root model's own events (medians, seconds into its run):", "",
                      *milestone_table(marks)]
            compare = subprocess.run([str(python), str(trees["head"] / "scripts/bench/cadgen-performance/agent_edits.py"),
                                      "--compare", str(reports["base"]), str(reports["head"])],
                                     capture_output=True, text=True)
            if compare.returncode != 0:
                print(f"  agent_edits.py --compare: status {compare.returncode}: {compare.stderr.strip()}", file=sys.stderr)
            lines += ["", "moonwatch edit loop (medians, seconds):", "", compare.stdout.strip() or compare.stderr.strip()]
        (out / "table.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("\n".join(lines))
    finally:
        for side in ("base", "head"):
            remove_worktree(out / f"wt-{side}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
