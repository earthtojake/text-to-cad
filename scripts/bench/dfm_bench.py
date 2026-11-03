#!/usr/bin/env python3
"""The manufacturing checks on real parts, timed: every STEP under the roots given, each checked for
every process, in this process (the checkout's environment holds the build123d and trimesh
integrations), one part at a time.

    .venv/bin/python scripts/bench/dfm_bench.py --root ../../../models --limit 40
    .venv/bin/python scripts/bench/dfm_bench.py --root /Applications/KiCad/KiCad.app/Contents/SharedSupport/3dmodels --limit 60 --process printing
    .venv/bin/python scripts/bench/dfm_bench.py --dry-run --root models

A worktree holds no built model (``models/`` is code; its STEP files are made by ``python model.py``),
so point ``--root`` at a checkout that has built them, or at any folder of STEP files (KiCad's 3D
models). Files are taken smallest first, ``--limit`` of them (``--max-mb`` caps a file's size), and the
same order every run. Each row: the file, its size, the process, the wall time of the check, its
``ok``, how many findings of each severity, the rule ids that failed, the families that could not be
measured, and the faces and parts the document holds; a check that raised records its error. The
batch writes ``tmp/bench/dfm-<time>/rows.jsonl`` (appended after each check) and ``table.md`` (per
process: parts, median and p95 and max seconds, failures to measure, the most frequent rule ids).
Manual, never in CI (``scripts/bench/README.md``); only ``summarize`` is a pure helper.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import traceback
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

PROCESSES = ("cnc", "sheet", "molding", "printing")
SUFFIXES = (".step", ".stp")


def files(roots: Iterable[Path], limit: int | None, max_mb: float) -> list[Path]:
    """The STEP files under ``roots``, smallest first (then by path), at most ``limit``, none over ``max_mb``."""
    found = {path.resolve() for root in roots for path in Path(root).rglob("*")
             if path.suffix.lower() in SUFFIXES and path.is_file()}
    chosen = sorted((path for path in found if path.stat().st_size <= max_mb * 1e6),
                    key=lambda path: (path.stat().st_size, str(path)))
    return chosen[:limit] if limit else chosen


def row_of(path: Path, process: str, result: Any, seconds: float) -> dict[str, Any]:
    findings = list(result.findings)
    measurements = result.measurements or {}
    return {
        "file": str(path), "bytes": path.stat().st_size, "process": process, "seconds": round(seconds, 3),
        "ok": bool(result.ok),
        "severities": dict(Counter(finding.severity for finding in findings)),
        "failed_rules": sorted({finding.code for finding in findings
                                if finding.severity in ("error", "warning") and "." in (finding.code or "")}),
        "unmeasured": list(measurements.get("partial_sections") or []),
        "codes": sorted({finding.code for finding in findings if finding.code}),
        "faces": sum(body.get("face_count", 0) for body in measurements.get("bodies") or []),
        "parts": len(measurements.get("bodies") or []),
    }


def summarize(rows: list[dict[str, Any]]) -> str:
    """The table of a batch's rows: per process, the parts checked, seconds (median, p95, max), the checks
    that raised or could not measure a family, and the ten most frequent failing rule ids."""
    lines = ["| process | parts | median s | p95 s | max s | raised | unmeasured | most frequent rules |",
             "|---|---|---|---|---|---|---|---|"]
    for process in PROCESSES:
        group = [row for row in rows if row["process"] == process]
        if not group:
            continue
        times = sorted(row["seconds"] for row in group if "error" not in row)
        p95 = times[min(len(times) - 1, int(round(0.95 * (len(times) - 1))))] if times else None
        rules = Counter(rule for row in group for rule in row.get("failed_rules") or ())
        common = ", ".join(f"{rule} ({count})" for rule, count in rules.most_common(10))
        lines.append(
            f"| {process} | {len(group)} | {statistics.median(times) if times else '-'} | {p95 if p95 is not None else '-'} "
            f"| {times[-1] if times else '-'} | {sum(1 for row in group if 'error' in row)} "
            f"| {sum(1 for row in group if row.get('unmeasured'))} | {common or '-'} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", action="append", type=Path, required=True, help="a folder of STEP files (repeat)")
    parser.add_argument("--process", action="append", choices=PROCESSES, help="a process to check (repeat; default all)")
    parser.add_argument("--limit", type=int, default=40, help="files, smallest first (0: all)")
    parser.add_argument("--max-mb", type=float, default=20.0, help="skip files over this many megabytes")
    parser.add_argument("--out", type=Path, help="a fresh folder (default tmp/bench/dfm-<time>)")
    parser.add_argument("--dry-run", action="store_true", help="list the files and stop")
    args = parser.parse_args(argv)
    chosen = files(args.root, args.limit or None, args.max_mb)
    processes = args.process or list(PROCESSES)
    if args.dry_run:
        for path in chosen:
            print(f"{path.stat().st_size:>10} {path}")
        print(f"{len(chosen)} files x {len(processes)} processes")
        return 0
    out = args.out or Path("tmp/bench") / time.strftime("dfm-%Y%m%d-%H%M%S")
    out.mkdir(parents=True, exist_ok=False)
    import cad

    rows: list[dict[str, Any]] = []
    with open(out / "rows.jsonl", "a", encoding="utf-8") as log:
        log.write(json.dumps({"python": sys.version, "files": len(chosen), "processes": processes,
                              "roots": [str(root) for root in args.root]}) + "\n")
        for path in chosen:
            for process in processes:
                start = time.perf_counter()
                try:
                    result = cad.step.check(path, process=process)
                    row = row_of(path, process, result, time.perf_counter() - start)
                except Exception as error:  # noqa: BLE001 - a check that raises is a row, not the batch's end
                    row = {"file": str(path), "bytes": path.stat().st_size, "process": process,
                           "seconds": round(time.perf_counter() - start, 3), "error": f"{type(error).__name__}: {error}",
                           "trace": traceback.format_exc(limit=4)}
                rows.append(row)
                log.write(json.dumps(row) + "\n")
                log.flush()
                print(f"{row['seconds']:>7.2f}s {process:<8} {'raised' if 'error' in row else 'ok' if row['ok'] else 'fails'}"
                      f" {path.name}", flush=True)
            (out / "table.md").write_text(summarize(rows), encoding="utf-8")
    print(summarize(rows))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
