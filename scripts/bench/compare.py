#!/usr/bin/env python3
"""Recorded store-engine baseline against this branch: the old engine's recorded numbers beside a corpus batch's, per model.

A manual report, never run in CI; it prints Markdown, and ``--out`` writes it too (under ``tmp/``:
never committed).

    .venv/bin/python scripts/bench/compare.py tmp/bench/corpus-<time>/rows.jsonl [more rows.jsonl ...]

The new side is ``corpus_bench.py``'s rows, per model: the median wall of its ``cold``, ``noop``
and ``edit`` builds over every batch given (a failed step counts for nothing), and its document:
the xbf's size and its separately measured export time. The old side is
``old-engine-numbers.json`` beside this script (``--old`` for another), kept by hand: the old
engine's (#568's store engine before the xbf engine, not a main release) cold, no-op and edit, each a range of seconds, and
the STEP its model wrote, each number with the note it was recorded in (``source``) and the words
that say it (``line``). Nothing here runs the old engine: a model or a measure with no old number
says "no recorded old number". This command never fills a missing baseline by running old code.

The table has a row per model and measure, old beside new, and the speedup: old over new, a range
where the old number is one; for the file, how many times smaller the xbf is than the STEP. The
old numbers' sources follow, numbered, then what each side measured.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Iterable

OLD = Path(__file__).with_name("old-engine-numbers.json")
TIMES = (("cold", "cold"), ("noop", "no-op"), ("edit", "edit"))
NO_OLD = "no recorded old number"
TIME_KEYS = frozenset({"seconds", "approx", "source", "line", "note"})
FILE_KEYS = frozenset({"kind", "MB", "seconds", "source", "line", "note"})


def read_rows(lines: Iterable[str]) -> tuple[list[dict[str, Any]], list[int]]:
    """A JSONL file's objects, and the numbers of the lines that hold none (a batch cut off in the
    middle of a line, say). Blank lines are passed over."""
    rows: list[dict[str, Any]] = []
    bad: list[int] = []
    for number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            row = None
        if isinstance(row, dict):
            rows.append(row)
        else:
            bad.append(number)
    return rows, bad


def _span(value: Any) -> bool:
    return (isinstance(value, list) and len(value) == 2
            and all(isinstance(end, (int, float)) and not isinstance(end, bool) for end in value)
            and 0 < value[0] <= value[1])


def old_problems(old: Any) -> list[str]:
    """What is wrong with the old numbers, each in words; empty when nothing is. A time is
    ``{"seconds": [low, high]}`` (``approx`` when the note says about); the file is ``{"kind",
    "MB"}``, with the ``seconds`` it took to write if recorded; each has its ``source`` and ``line``."""
    if not isinstance(old, dict) or not isinstance(old.get("models"), dict):
        return ["the old numbers are an object whose `models` maps each model to its numbers"]
    found = [f"unknown key `{key}`" for key in sorted(set(old) - {"about", "models"})]
    for model, numbers in old["models"].items():
        if not isinstance(numbers, dict):
            found.append(f"{model}: not an object")
            continue
        for measure, entry in numbers.items():
            where = f"{model}.{measure}"
            if measure not in ("cold", "noop", "edit", "file"):
                found.append(f"{where}: no such measure (cold, noop, edit, file)")
                continue
            if not isinstance(entry, dict):
                found.append(f"{where}: not an object")
                continue
            found += [f"{where}: unknown key `{key}`"
                      for key in sorted(set(entry) - (FILE_KEYS if measure == "file" else TIME_KEYS))]
            found += [f"{where}: no `{key}`" for key in ("source", "line")
                      if not isinstance(entry.get(key), str) or not entry[key].strip()]
            if measure == "file":
                if not isinstance(entry.get("kind"), str) or not entry["kind"]:
                    found.append(f"{where}: `kind` is the file's kind")
                if not isinstance(entry.get("MB"), (int, float)) or isinstance(entry.get("MB"), bool) or entry["MB"] <= 0:
                    found.append(f"{where}: `MB` is its size")
                if "seconds" in entry and not _span(entry["seconds"]):
                    found.append(f"{where}: `seconds` is [low, high], 0 < low <= high")
            elif not _span(entry.get("seconds")):
                found.append(f"{where}: `seconds` is [low, high], 0 < low <= high")
            if not isinstance(entry.get("approx", False), bool):
                found.append(f"{where}: `approx` is true or false")
            if not isinstance(entry.get("note", ""), str):
                found.append(f"{where}: `note` is text")
    return found


def new_numbers(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per model, in the order the rows first name it: the median wall of its ``cold``, ``noop`` and
    ``edit`` steps that did not fail, and which did (``failed``); its document's size in MB
    (``xbf_mb``) and write time (``xbf_seconds``) after its cold builds; and the other kinds its
    builds wrote (``declares``)."""
    found: dict[str, dict[str, Any]] = {}
    for row in rows:
        if row.get("kind") != "step" or not isinstance(row.get("model"), str):
            continue
        mine = found.setdefault(row["model"], {"declares": set(), "failed": set()})
        step = row.get("step")
        if row.get("comparison_note"):
            mine.setdefault("comparison_notes", set()).add(row["comparison_note"])
        if step == "export" and row.get("ok") and row.get("xbf_bytes"):
            mine.setdefault("xbf_mb", []).append(row["xbf_bytes"] / 1e6)
            if isinstance(row.get("xbf_seconds"), (int, float)):
                mine.setdefault("xbf_seconds", []).append(row["xbf_seconds"])
            continue
        if step not in ("cold", "noop", "edit"):
            continue
        if not row.get("ok"):
            mine["failed"].add(step)
            continue
        if isinstance(row.get("wall"), (int, float)):
            mine.setdefault(step, []).append(row["wall"])
        files = row.get("files") or {}
        mine["declares"].update(kind for kind in files if kind != "xbf")
        if step == "cold" and row.get("xbf_bytes"):
            mine.setdefault("xbf_mb", []).append(row["xbf_bytes"] / 1e6)
            if isinstance((files.get("xbf") or {}).get("seconds"), (int, float)):
                mine.setdefault("xbf_seconds", []).append(files["xbf"]["seconds"])
    return {model: {key: sorted(values) if key in ("declares", "failed", "comparison_notes") else statistics.median(values)
                    for key, values in measures.items()} for model, measures in found.items()}


def seconds(value: float) -> str:
    """As the batch notes write a time: two decimals under 10, one under 100, none above."""
    return f"{value:.2f}" if value < 10 else f"{value:.1f}" if value < 100 else f"{value:.0f}"


def megabytes(value: float) -> str:
    return f"{value:.2f}" if value < 1 else f"{value:.1f}"


def _range(entry: dict[str, Any]) -> str:
    low, high = entry["seconds"]
    return ("~" if entry.get("approx") else "") + (f"{low:g}" if low == high else f"{low:g}–{high:g}") + " s"


def _times(entry: dict[str, Any], new: float | None) -> str:
    """Old over new, a range where the old number is one."""
    if not new:
        return "—"
    low, high = (f"{end / new:.1f}" for end in entry["seconds"])
    return ("~" if entry.get("approx") else "") + (low if low == high else f"{low}–{high}") + "×"


def _summary(mine: dict[str, Any] | None) -> str:
    if not mine:
        return "not run"
    said = [f"{label} {seconds(mine[key])} s" for key, label in TIMES if key in mine]
    if "xbf_mb" in mine:
        said.append(f"xbf {megabytes(mine['xbf_mb'])} MB")
    return " · ".join(said) or "every step failed"


def table(old: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    """The comparison as Markdown: the table, the old numbers' sources, and what each side measured."""
    new = new_numbers(rows)
    recorded = old.get("models") or {}
    sources: dict[tuple[str, str], int] = {}
    notes: list[str] = []

    def cite(entry: dict[str, Any]) -> str:
        number = sources.setdefault((entry["source"], entry["line"]), len(sources) + 1)
        return f" [{number}]"

    lines = ["| model | measure | old engine (#568 store) | xbf engine | speedup |", "|---|---|---|---|---|"]
    for model in [*new, *(name for name in recorded if name not in new)]:
        mine, theirs = new.get(model), recorded.get(model) or {}
        if not theirs:
            lines.append(f"| {model} | all | {NO_OLD} | {_summary(mine)} | — |")
            continue
        failed = (mine or {}).get("failed", ())
        limitations = (mine or {}).get("comparison_notes", [])
        notes += [f"- {model}: {note}" for note in limitations]
        for key, label in TIMES:
            entry, value = theirs.get(key), (mine or {}).get(key)
            old_cell = NO_OLD if entry is None else _range(entry) + cite(entry)
            new_cell = f"{seconds(value)} s" if value is not None else "failed" if key in failed else "not run"
            speedup = "workload differs" if limitations and value is not None else "—" if entry is None else _times(entry, value)
            lines.append(f"| {model} | {label} | {old_cell} | {new_cell} | {speedup} |")
        entry, size = theirs.get("file"), (mine or {}).get("xbf_mb")
        old_cell = NO_OLD if entry is None else (f"{entry['kind'].upper()} {entry['MB']:g} MB"
                                                 + (f", written in {_range(entry)}" if "seconds" in entry else "")
                                                 + cite(entry))
        if size is None:
            new_cell = "failed" if "cold" in failed else "not run"
        else:
            new_cell = f"xbf {megabytes(size)} MB" + (f", written in {seconds(mine['xbf_seconds'])} s"
                                                      if "xbf_seconds" in mine else "")
        ratio = "—" if entry is None or not size else f"{entry['MB'] / size:.1f}× smaller"
        lines.append(f"| {model} | file | {old_cell} | {new_cell} | {ratio} |")
        notes += [f"- {model} {key}: {entry['note']}" for key, entry in theirs.items() if entry.get("note")]
    lines.append("")
    if sources:
        lines.append("Sources of the old numbers (`old-engine-numbers.json`):")
        lines.append("")
        lines += [f"{number}. {source}: “{line}”" for (source, line), number in sources.items()]
        lines.append("")
    if notes:
        lines += ["Notes:", "", *notes, ""]
    runs = [row for row in rows if row.get("kind") == "run"]
    load = [row["load"] for row in rows if row.get("kind") == "step" and isinstance(row.get("load"), (int, float))]
    for run in runs:
        lines.append(f"xbf engine: {str(run.get('commit') or '?')[:10]} on {run.get('branch') or '?'}"
                     f"{' (uncommitted changes)' if run.get('dirty') else ''}, {run.get('started', '?')}, "
                     f"{run.get('platform', '?')}.")
    if load:
        lines.append(f"Its 1-minute load average over the steps: {min(load):.1f}–{max(load):.1f}.")
    declared = [f"{model} ({', '.join(mine['declares'])})" for model, mine in new.items() if mine.get("declares")]
    lines.append("A new wall is the script's process, including every explicit model call and any declared files. "
                 "The benchmark's xbf export is measured separately." +
                 (f" Other declared files: {'; '.join(declared)}." if declared else ""))
    lines += ["", old.get("about", "")]
    return "\n".join(lines).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("rows", nargs="+", type=Path, help="corpus_bench.py's rows.jsonl, one or more batches")
    parser.add_argument("--old", type=Path, default=OLD, help="the old engine's numbers (default: beside this)")
    parser.add_argument("--out", type=Path, help="write the table here too")
    args = parser.parse_args(argv)
    try:
        old = json.loads(args.old.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(f"compare: {args.old}: {error}", file=sys.stderr)
        return 2
    found = old_problems(old)
    if found:
        print("\n".join(f"compare: {args.old}: {text}" for text in found), file=sys.stderr)
        return 2
    rows: list[dict[str, Any]] = []
    for path in args.rows:
        try:
            with open(path, encoding="utf-8") as handle:
                read, bad = read_rows(handle)
        except OSError as error:
            print(f"compare: {error}", file=sys.stderr)
            return 2
        if bad:
            print(f"compare: {path}: {'lines' if len(bad) > 1 else 'line'} {', '.join(map(str, bad))} "
                  f"{'hold' if len(bad) > 1 else 'holds'} no JSON object: passed over", file=sys.stderr)
        rows += read
    text = table(old, rows)
    print(text, end="")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
