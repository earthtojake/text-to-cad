#!/usr/bin/env python3
"""Build the sample corpus one model at a time, no daemon, into a fresh store; verify every STEP it exported.

The 0.8.0 migration's corpus gate (see "The 0.8.0 migration measurements" in
scripts/bench/README.md): every file a build exports holds the result it was written from. The
corpus is this checkout's models/. Each project's tracked files are copied under the run directory
(a copy has no committed output and nothing a developer built earlier, and the builds' outputs
land in it, never in the checkout), and every model script under models/<project>/src -- at most
two levels down, nothing under lib/, no __init__.py or conftest.py -- is run as
`python <script>` from its own directory: the active venv's Python with PYTHONPATH on this
checkout's packages/cadgen/src, CADGEN_DAEMON=0, one store under the run directory. Then every
STEP output a build's record names is verified against the record's tree
(cadgen.store.exports.verify_document, the verify a build's own pool job runs), --jobs files at
a time, and the summary is printed and written: files, verified, failed (each path and reason),
total seconds, seconds per model. The exit status is non-zero when a build or a verify failed.

usage: scripts/bench/corpus_verify.py [--projects a,b] [--out DIR] [--jobs N] [--timeout S]

  --projects a,b   only these projects (default: every models/<project> with a src/ folder);
                   the PROJECTS environment variable means the same
  --out DIR        the run directory (default tmp/bench/corpus/<UTC timestamp>); CORPUS_OUT means
                   the same
  --jobs N         verify processes (default: half the cores, at most four)
  --timeout S      seconds a model script may run before its build counts as failed (default 3600)

Output, under the run directory: models/<project>/ (the copies, holding the builds' outputs),
store/ (CADGEN_CACHE_DIR), logs/<project>/<script>.log (each build's output), build.jsonl (one
line per script: status, seconds), verify.jsonl (one line per exported STEP: result, what
differs, seconds; the verify runs as `--verify-shard I/N` processes of this script) and
summary.md (what the run printed).
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "packages/cadgen/src/cadgen/_runtime"
SKIPPED = {"__init__.py", "conftest.py"}


def venv_python() -> Path:
    """The active venv's interpreter: the activated one, this one when it is a venv's, else this
    checkout's .venv. It must import the CAD kernel."""
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


def environment(store: Path) -> dict[str, str]:
    return {**os.environ, "PYTHONPATH": str(ROOT / "packages/cadgen/src"), "CADGEN_CACHE_DIR": str(store),
            "CADGEN_DAEMON": "0", "CADGEN_TELEMETRY": "0", "CADGEN_UPDATE_CHECK": "0"}


def model_scripts(src: Path) -> list[Path]:
    """The model scripts of a project's src/: at most two levels down, nothing under lib/, no
    __init__.py or conftest.py (the rule the corpus has always been built by)."""
    found = []
    for path in list(src.glob("*.py")) + list(src.glob("*/*.py")):
        relative = path.relative_to(src)
        if "lib" in relative.parts[:-1] or path.name in SKIPPED:
            continue
        found.append(path)
    return sorted(found)


def copy_project(project: str, run: Path) -> int:
    """The project's tracked files, copied under run/models/<project>; how many."""
    listing = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--", f"models/{project}"],
                             check=True, capture_output=True, text=True).stdout
    copied = 0
    for relative in filter(None, listing.split("\0")):
        source = ROOT / relative
        if not source.is_file():
            print(f"  {relative}: tracked but missing, skipped", file=sys.stderr)
            continue
        target = run / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        copied += 1
    return copied


def build(python: Path, script: Path, log: Path, env: dict[str, str], timeout: float) -> dict:
    log.parent.mkdir(parents=True, exist_ok=True)
    start = time.perf_counter()
    with open(log, "w", encoding="utf-8") as sink:
        try:
            status: int | str = subprocess.run([str(python), script.name], cwd=script.parent, env=env,
                                               stdout=sink, stderr=subprocess.STDOUT, timeout=timeout).returncode
        except subprocess.TimeoutExpired:
            status = "timeout"
    return {"status": status, "seconds": round(time.perf_counter() - start, 1), "log": str(log)}


def verify_shard(shard: int, shards: int, out: Path) -> int:
    """This process's share of the exported STEP files, each verified against its record's tree;
    one JSON line per file. Runs with the build environment: PYTHONPATH names the cadgen to verify
    with, CADGEN_CACHE_DIR the store whose records are read."""
    import hashlib

    from cadgen.store.exports import verify_document
    from cadgen.store.paths import index_dir
    from cadgen.store.records import RECORD_KIND, RECORD_SCHEMA_VERSION, document_entry_for_hash

    files = []
    index = index_dir("model")
    for path in sorted(index.iterdir()) if index.is_dir() else []:
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if record.get("kind") != RECORD_KIND or record.get("schemaVersion") != RECORD_SCHEMA_VERSION:
            continue
        for file, output in sorted((record.get("outputs") or {}).items()):
            if str(file).lower().endswith((".step", ".stp")) and isinstance(output, dict):
                files.append((record, file, output))
    with out.open("w", encoding="utf-8") as sink:
        for position, (record, file, output) in enumerate(files):
            if position % shards != shard:
                continue
            row: dict = {"model": record.get("model"), "file": file, "plain": bool(output.get("plain"))}
            sha = str(output.get("sha256") or "")
            path = Path(file)
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != sha:
                row["result"] = "file changed"
            else:
                entry = document_entry_for_hash(sha) or {}
                producer = None if output.get("plain") else entry.get("producer")
                started = time.perf_counter()
                try:
                    answer = verify_document(record["tree"], path, sha, producer=producer)
                except Exception as error:  # noqa: BLE001 -- a gate reports every failure
                    row["result"] = f"error: {type(error).__name__}: {error}"
                else:
                    row["result"] = {True: "verified", False: "differs", None: "file changed"}[answer["ok"]]
                    if answer.get("differ"):
                        row["differ"] = answer["differ"]
                row["seconds"] = round(time.perf_counter() - started, 2)
            sink.write(json.dumps(row) + "\n")
            sink.flush()
    return 0


def verify(python: Path, run: Path, env: dict[str, str], jobs: int) -> list[dict]:
    shards = [subprocess.Popen([str(python), str(Path(__file__).resolve()), "--verify-shard", f"{shard}/{jobs}",
                                "--out", str(run)], env=env) for shard in range(jobs)]
    for shard, process in enumerate(shards):
        if process.wait() != 0:
            sys.exit(f"verify shard {shard} failed (status {process.returncode})")
    rows = []
    for shard in range(jobs):
        rows += [json.loads(line) for line in (run / f"verify-{shard}.jsonl").read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    rows.sort(key=lambda row: row["file"])
    (run / "verify.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--projects", default=os.environ.get("PROJECTS", ""))
    parser.add_argument("--out", default=os.environ.get("CORPUS_OUT", ""))
    parser.add_argument("--jobs", type=int, default=max(1, min(4, (os.cpu_count() or 2) // 2)))
    parser.add_argument("--timeout", type=float, default=3600.0)
    parser.add_argument("--verify-shard", metavar="I/N", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.verify_shard:
        shard, shards = (int(part) for part in args.verify_shard.split("/"))
        return verify_shard(shard, shards, Path(args.out) / f"verify-{shard}.jsonl")
    if not (RUNTIME / "native").is_dir():
        sys.exit(f"the packaged runtime is not built ({RUNTIME}): scripts/bundle/bundle.sh")
    python = venv_python()
    projects = sorted(path.name for path in (ROOT / "models").iterdir() if (path / "src").is_dir())
    if args.projects.strip():
        chosen = [name for name in args.projects.replace(",", " ").split() if name]
        unknown = [name for name in chosen if name not in projects]
        if unknown:
            parser.error(f"no such project: {', '.join(unknown)} (one of {', '.join(projects)})")
        projects = chosen
    run = Path(args.out).expanduser().resolve() if args.out else \
        ROOT / "tmp/bench/corpus" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    store = run / "store"
    store.mkdir(parents=True, exist_ok=True)
    env = environment(store)
    print(f"corpus run {run}: {', '.join(projects)}; python {python}; cadgen {ROOT / 'packages/cadgen/src'}", flush=True)

    builds = []
    started = time.perf_counter()
    with open(run / "build.jsonl", "w", encoding="utf-8") as sink:
        for project in projects:
            if not copy_project(project, run):
                print(f"  {project}: no tracked files, skipped", file=sys.stderr)
                continue
            for script in model_scripts(run / "models" / project / "src"):
                name = f"{project}/{script.relative_to(run / 'models' / project / 'src').as_posix()}"
                log = run / "logs" / project / (name.split("/", 1)[1].replace("/", "__") + ".log")
                row = {"model": name, **build(python, script, log, env, args.timeout)}
                builds.append(row)
                sink.write(json.dumps(row) + "\n")
                sink.flush()
                print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {name} status={row['status']} "
                      f"seconds={row['seconds']}", flush=True)
    build_seconds = time.perf_counter() - started

    started = time.perf_counter()
    rows = verify(python, run, env, args.jobs)
    verify_seconds = time.perf_counter() - started

    failed_builds = [row for row in builds if row["status"] != 0]
    failed_files = [row for row in rows if row["result"] != "verified"]
    plain = sum(1 for row in rows if row.get("plain"))
    lines = [f"{len(builds)} models in {len(projects)} projects, {len(builds) - len(failed_builds)} built; "
             f"{len(rows)} STEP files, {len(rows) - len(failed_files)} verified, {len(failed_files)} failed"
             + (f", {plain} written plain" if plain else "")
             + f"; {build_seconds:.0f} s building, {verify_seconds:.0f} s verifying, "
             f"{build_seconds + verify_seconds:.0f} s total"]
    if failed_builds:
        lines += ["", "builds that failed:"]
        lines += [f"  {row['model']}: status {row['status']}; see {row['log']}" for row in failed_builds]
    if failed_files:
        lines += ["", "files that did not verify:"]
        for row in failed_files:
            relative = row["file"].split("/models/", 1)[-1]
            reason = row["result"] + ("; " + "; ".join(str(d) for d in row["differ"][:4]) if row.get("differ") else "")
            lines.append(f"  {relative}: {reason}")
    lines += ["", "seconds per model:"]
    lines += [f"  {row['model']}  {row['seconds']}" + ("" if row["status"] == 0 else f"  (status {row['status']})")
              for row in builds]
    (run / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 1 if failed_builds or failed_files else 0


if __name__ == "__main__":
    sys.exit(main())
