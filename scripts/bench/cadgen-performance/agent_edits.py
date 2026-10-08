#!/usr/bin/env python3
"""End-to-end timings of the edits an agent makes, through ``python <model>.py``.

Every run is a fresh ``python <model>.py --json --verbose`` client against a
private warm daemon and store, so the timing includes what an agent waits for:
interpreter start, the client gate, daemon IPC, child builds and the save. An
unmeasured forced rebuild of the top model starts the daemon first. Each
scenario then starts from a current baseline:

- ``noop``: rerun with nothing changed;
- ``comment``: append a comment to the leaf source (semantically a no-op);
- ``leaf``: a dimension edit in a leaf part (the leaf and its parents rebuild);
- ``revert-leaf``: the leaf source back to the baseline;
- ``parent`` / ``revert-parent``: a parent-only edit, such as a placement literal;
- ``label`` / ``revert-label``: a label-only edit that leaves geometry alone.

Edits are exact substitutions that must match once. Each iteration takes the
next ``--*-to`` value, so an edit is new to the store; reverts return to bytes
the store has built before. Sources are restored in ``finally``.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

from common import REPO, metadata, sha256, write_json

STAGE = re.compile(r"^\[cadgen\] (.+?) completed in ([0-9.]+)(ms|s)$", re.MULTILINE)
# A model's build-tree phases, in the order the pipeline announces them.
MARKS = ("Building geometry", "Collecting parts", "Source ready", "Saving STEP", "STEP saved")


def parse_stages(stderr: str) -> dict[str, float]:
    """The root model's ``--verbose`` stages in seconds, first occurrence of each
    label, with the document's file name dropped so models compare."""
    stages: dict[str, float] = {}
    for label, value, unit in STAGE.findall(stderr):
        label = re.sub(r" \S+\.(step|stp)$", "", label)
        stages.setdefault(label, float(value) / (1000.0 if unit == "ms" else 1.0))
    return stages


def parse_models(stderr: str) -> dict[str, dict]:
    """Per model (by script name): its terminal state and the seconds between
    the build-tree phases. ``elapsed`` restarts at each model's own job."""
    models: dict[str, dict] = {}
    for line in stderr.splitlines():
        if not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except ValueError:
            continue
        name = Path(str(event.get("model") or "?").split("::")[0]).name
        row = models.setdefault(name, {"states": [], "marks": {}})
        state, phase, elapsed = event.get("state"), event.get("phase"), float(event.get("elapsed") or 0.0)
        if not row["states"] or row["states"][-1] != state:
            row["states"].append(state)
        if state == "building" and phase in MARKS:
            row["marks"].setdefault(phase, elapsed)
        if state in {"done", "failed", "current"}:
            row["terminal"], row["seconds"] = state, elapsed
    for row in models.values():
        marks = row["marks"]
        points = [("preBody", 0.0, marks.get("Building geometry")),
                  ("body", marks.get("Building geometry"), marks.get("Collecting parts")),
                  ("package", marks.get("Collecting parts"), marks.get("Source ready")),
                  ("preview", marks.get("Source ready"), marks.get("Saving STEP")),
                  ("save", marks.get("Saving STEP"), marks.get("STEP saved")),
                  ("tail", marks.get("STEP saved"), row.get("seconds")
                   if row.get("terminal") == "done" else None)]
        row["phases"] = {name: round(end - start, 3) for name, start, end in points
                         if start is not None and end is not None}
        row["built"] = row.get("terminal") == "done"
    return models


def step_digests(root: Path, known: dict[str, tuple[int, int, str]]) -> dict[str, str]:
    """sha256 of every STEP under the project, re-hashing only files whose size
    or mtime moved since the last call (outside the timed region)."""
    found: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".step", ".stp"} or not path.is_file() or path.name.startswith("."):
            continue
        stat = path.stat()
        key = str(path.relative_to(root))
        cached = known.get(key)
        if cached is None or cached[:2] != (stat.st_size, stat.st_mtime_ns):
            cached = (stat.st_size, stat.st_mtime_ns, sha256(path.read_bytes()))
            known[key] = cached
        found[key] = cached[2]
    return found


def summary(values: list[float]) -> dict:
    return {"count": len(values), "min": min(values), "median": statistics.median(values), "max": max(values)}


def markdown(reports: list[dict]) -> str:
    """Median wall seconds per scenario, one column per report."""
    scenarios: list[str] = []
    for report in reports:
        for name in report.get("summary", {}):
            if name not in scenarios:
                scenarios.append(name)
    header = "| scenario | " + " | ".join(r.get("configuration") or "?" for r in reports) + " |"
    lines = [header, "|---|" + "---:|" * len(reports)]
    for name in scenarios:
        cells = []
        for report in reports:
            row = report.get("summary", {}).get(name)
            cells.append("—" if row is None else f"{row['median']:.2f}")
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--compare", nargs="+", type=Path, metavar="REPORT",
                        help="Print a Markdown table of earlier reports' medians, then exit")
    parser.add_argument("--model", help="Top model script, in a disposable project copy")
    parser.add_argument("--project", help="Project folder whose STEP files are fingerprinted after each run "
                                          "(default: the folder holding the script's src/)")
    parser.add_argument("--configuration", default="", help="Name for this checkout in reports (e.g. main)")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--iterations", type=int, default=1)
    parser.add_argument("--store", help="Dedicated CADGEN_CACHE_DIR; never ~/.cache/cadgen")
    parser.add_argument("--daemon-socket", help="Private CADGEN_DAEMON_SOCKET (keep the path short)")
    parser.add_argument("--daemon-state", help="Private CADGEN_DAEMON_STATE_DIR (default: beside --store)")
    parser.add_argument("--idle-timeout", default="300", help="CADGEN_DAEMON_IDLE_TIMEOUT for the private daemon")
    parser.add_argument("--cadgen-src", default=str(REPO / "packages/cadgen/src"),
                        help="cadgen source root put on PYTHONPATH (default: this checkout)")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--node-bin", help="Directory prepended to PATH (Node 22 for the mesh builders)")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Seconds before a run counts as failed")
    parser.add_argument("--max-load", type=float,
                        help="Before each run, wait (up to 30 min) for the one-minute load average to drop below this")
    for kind in ("leaf", "parent", "label"):
        parser.add_argument(f"--{kind}-model", help=f"Source holding the {kind} edit (default: --model)")
        parser.add_argument(f"--{kind}-from", help=f"Exact text the {kind} edit replaces")
        parser.add_argument(f"--{kind}-to", action="append", default=[],
                            help="Replacement; repeat once per iteration so each edit is new")
    parser.add_argument("--comment-model", help="Source the comment edit appends to (default: the leaf source)")
    args = parser.parse_args()
    if args.compare:
        print(markdown([json.loads(path.read_text(encoding="utf-8")) for path in args.compare]))
        return 0
    for required in ("model", "report", "store", "daemon_socket", "leaf_from"):
        if not getattr(args, required):
            parser.error(f"--{required.replace('_', '-')} is required")
    if args.iterations < 1:
        parser.error("--iterations must be positive")
    model = Path(args.model).expanduser().resolve()
    store = Path(args.store).expanduser().resolve()
    if store == (Path.home() / ".cache/cadgen").resolve():
        parser.error("--store must be a dedicated benchmark store")
    corpus = (REPO / "models").resolve()
    if model.is_relative_to(corpus) and not model.is_relative_to(corpus / "tmp"):
        parser.error("--model must be a disposable copy: this edits its sources")
    if args.project:
        project = Path(args.project).expanduser().resolve()
    else:
        # The project holding the script's `src/` folder, else the script's folder.
        project = next((folder.parent for folder in model.parents if folder.name == "src"), model.parent)
    if not model.is_relative_to(project):
        parser.error("--model must be inside --project")

    edits: dict[str, tuple[Path, str, list[str]]] = {}
    for kind in ("leaf", "parent", "label"):
        old, new = getattr(args, f"{kind}_from"), getattr(args, f"{kind}_to")
        if old is None:
            continue
        if len(new) < args.iterations:
            parser.error(f"--{kind}-to needs one value per iteration ({args.iterations})")
        path = Path(getattr(args, f"{kind}_model") or model).expanduser().resolve()
        text = path.read_text(encoding="utf-8")
        if text.count(old) != 1 or old in new:
            parser.error(f"--{kind}-from must match {path.name} exactly once and every --{kind}-to must change it")
        edits[kind] = (path, old, new)
    comment_path = Path(args.comment_model or edits["leaf"][0]).expanduser().resolve()
    sources = {path for path, _, _ in edits.values()} | {model, comment_path}
    originals = {path: (path.read_bytes(), path.stat()) for path in sources}

    env = dict(os.environ)
    env.update(PYTHONPATH=str(Path(args.cadgen_src).expanduser().resolve()), CADGEN_CACHE_DIR=str(store),
               CADGEN_DAEMON_SOCKET=str(Path(args.daemon_socket).expanduser()),
               CADGEN_DAEMON_STATE_DIR=str(Path(args.daemon_state or store.parent / "daemon").expanduser().resolve()),
               CADGEN_DAEMON_IDLE_TIMEOUT=str(args.idle_timeout))
    for name in ("CADGEN_DAEMON", "PYTHONDONTWRITEBYTECODE", "CADGEN_JOBS"):
        env.pop(name, None)
    if args.node_bin:
        env["PATH"] = f"{Path(args.node_bin).expanduser().resolve()}{os.pathsep}{env.get('PATH', '')}"
    store.mkdir(parents=True, exist_ok=True)
    Path(env["CADGEN_DAEMON_STATE_DIR"]).mkdir(parents=True, exist_ok=True)

    environment = {key: env[key] for key in ("CADGEN_CACHE_DIR", "CADGEN_DAEMON_STATE_DIR", "CADGEN_DAEMON_IDLE_TIMEOUT")}
    report = {"metadata": metadata(), "configuration": args.configuration, "model": str(model),
              "project": str(project), "cadgenSource": env["PYTHONPATH"], "python": args.python,
              "environment": environment,
              "timingBoundary": "wall clock of one `python <model>.py --json --verbose` client, "
                                "private warm daemon, sources written before the clock starts",
              "edits": {kind: {"file": str(path), "from": old, "to": new[: args.iterations]}
                        for kind, (path, old, new) in edits.items()},
              "commentFile": str(comment_path), "runs": []}
    logs = args.report.resolve().with_suffix("").with_name(args.report.stem + "-logs")
    logs.mkdir(parents=True, exist_ok=True)
    digests: dict[str, tuple[int, int, str]] = {}
    previous_steps = step_digests(project, digests)

    def write_variant(variant: dict[Path, bytes]) -> None:
        for path, (payload, _stat) in originals.items():
            wanted = variant.get(path, payload)
            if path.read_bytes() != wanted:
                path.write_bytes(wanted)

    def run(scenario: str, iteration: int, variant: dict[Path, bytes], *, measured: bool,
            expect: str | None = None, flags: tuple[str, ...] = ()) -> dict:
        nonlocal previous_steps
        write_variant(variant)
        index = len(report["runs"])
        waited = time.monotonic()
        while args.max_load is not None and os.getloadavg()[0] >= args.max_load and time.monotonic() - waited < 1800:
            time.sleep(5)
        load_before = os.getloadavg()[0]
        started = time.perf_counter()
        try:
            completed = subprocess.run([args.python, str(model), "--json", "--verbose", *flags], cwd=model.parent,
                                       env=env, capture_output=True, text=True, timeout=args.timeout)
            code, stdout, stderr = completed.returncode, completed.stdout, completed.stderr
        except subprocess.TimeoutExpired as exc:
            code, stdout, stderr = -1, exc.stdout or "", (exc.stderr or "") + "\n[benchmark] timed out"
            stdout = stdout.decode() if isinstance(stdout, bytes) else stdout
            stderr = stderr.decode() if isinstance(stderr, bytes) else stderr
        wall = time.perf_counter() - started
        (logs / f"{index:02d}-{scenario}-{iteration}.log").write_text(stdout + "\n" + stderr, encoding="utf-8")
        result = {}
        for line in reversed(stdout.splitlines()):
            if line.startswith("{"):
                try:
                    result = json.loads(line)
                    break
                except ValueError:
                    continue
        models = parse_models(stderr)
        steps = step_digests(project, digests)
        changed = sorted(key for key in steps.keys() | previous_steps.keys() if steps.get(key) != previous_steps.get(key))
        previous_steps = steps
        built = sorted(name for name, row in models.items() if row["built"])
        row = {"scenario": scenario, "iteration": iteration, "measured": measured, "wallSeconds": round(wall, 3),
               # One-minute load average around the run: other work on the machine
               # is the usual cause of an outlier.
               "load": [round(load_before, 1), round(os.getloadavg()[0], 1)],
               "exit": code, "outcome": result.get("outcome"), "tree": result.get("tree"),
               "built": built, "changedSteps": changed, "steps": steps, "stages": parse_stages(stderr),
               "models": models}
        problems = []
        if code != 0 or not result.get("ok"):
            problems.append(f"exit {code}: {result.get('error') or stderr.strip().splitlines()[-1:]}")
        if expect == "current" and (result.get("outcome") != "current" or built):
            problems.append(f"expected nothing to build, built {built or result.get('outcome')}")
        if expect == "built" and result.get("outcome") != "built":
            problems.append(f"expected a rebuild, outcome {result.get('outcome')}")
        if problems:
            row["problems"] = problems
        report["runs"].append(row)
        write_json(args.report, report)
        print(json.dumps({key: row[key] for key in ("scenario", "iteration", "wallSeconds", "outcome", "built", "changedSteps")}
                         | ({"problems": problems} if problems else {})), flush=True)
        return row

    baseline = {path: saved[0] for path, saved in originals.items()}

    def variant(kind: str, iteration: int) -> dict[Path, bytes]:
        path, old, new = edits[kind]
        edited = dict(baseline)
        edited[path] = baseline[path].decode("utf-8").replace(old, new[iteration]).encode("utf-8")
        return edited

    commented = dict(baseline)
    commented[comment_path] = baseline[comment_path] + b"\n# agent-edit benchmark: a comment changes no geometry\n"
    try:
        cold = run("cold", 0, baseline, measured=False)
        if cold.get("problems"):
            raise RuntimeError(f"baseline build failed; see {logs}")
        # Start the private daemon and bind the root's worker before any timing:
        # a forced root rebuild leaves the baseline current.
        run("warmup", 0, baseline, measured=False, expect="built", flags=("--force",))
        run("prime", 0, baseline, measured=False, expect="current")
        for iteration in range(args.iterations):
            run("noop", iteration, baseline, measured=True, expect="current")
            run("comment", iteration, commented, measured=True, expect="current")
            run("restore-comment", iteration, baseline, measured=False, expect="current")
            for kind in ("leaf", "parent", "label"):
                if kind in edits:
                    run(kind, iteration, variant(kind, iteration), measured=True, expect="built")
                    run(f"revert-{kind}", iteration, baseline, measured=True, expect="built")
        report["summary"] = {}
        for row in report["runs"]:
            if row["measured"] and not row.get("problems"):
                report["summary"].setdefault(row["scenario"], []).append(row["wallSeconds"])
        report["summary"] = {name: summary(values) for name, values in report["summary"].items()}
        print(markdown([report]))
        return 0 if not any(row.get("problems") for row in report["runs"]) else 1
    finally:
        for path, (payload, original_stat) in originals.items():
            path.write_bytes(payload)
            os.utime(path, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))
        report["sourceRestored"] = all(path.read_bytes() == saved[0] for path, saved in originals.items())
        write_json(args.report, report)


if __name__ == "__main__":
    raise SystemExit(main())
