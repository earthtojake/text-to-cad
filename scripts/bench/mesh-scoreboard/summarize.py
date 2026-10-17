"""The scoreboard table from `score.py` rows: one column per JSONL, one row per corpus file and a
total, as Markdown for a pull request description.

    ./.venv/bin/python scripts/bench/mesh-scoreboard/summarize.py \
        main=tmp/mesh-scoreboard/main.jsonl branch=tmp/mesh-scoreboard/branch.jsonl \
        occt=tmp/mesh-scoreboard/occt.jsonl

Each cell is `open-edge solids / cracks over 1 d / silent empty faces / faces off area / faces off
surface / folded / needles / errors`, with the triangles and seconds beside it; `--by file` gives the
rows per file, `--by total` (the default) the totals alone. A column that scored fewer solids than
another is marked, since its totals are not comparable.
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

COLUMNS = ("solids", "open_solids", "cracks", "empty", "area_off", "dev_off", "folded", "needles", "errors",
           "triangles", "seconds")


def load(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def totals(rows: list[dict]) -> dict:
    total = dict.fromkeys(COLUMNS, 0)
    for row in rows:
        total["solids"] += 1
        if "error" in row:
            total["errors"] += 1
            continue
        total["open_solids"] += int(row["open"] > 0)
        total["cracks"] += int(row.get("widest", 0.0) > 1.0)
        for key in ("empty", "area_off", "dev_off", "folded", "needles", "triangles"):
            total[key] += int(row.get(key, 0) or 0)
        total["seconds"] += float(row.get("seconds", 0.0) or 0.0)
    return total


def cell(total: dict) -> str:
    return (f"{total['open_solids']} / {total['cracks']} / {total['empty']} / {total['area_off']} / "
            f"{total['dev_off']} / {total['folded']} / {total['needles']} / {total['errors']}"
            f" · {total['triangles']:,} tri · {total['seconds']:.0f} s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scores", nargs="+", help="NAME=PATH.jsonl, one per column")
    parser.add_argument("--by", choices=("total", "file"), default="total")
    args = parser.parse_args(argv)
    columns = []
    for item in args.scores:
        name, _, path = item.partition("=")
        if not path:
            parser.error(f"{item}: expected NAME=PATH.jsonl")
        columns.append((name, load(Path(path))))
    counts = {name: len(rows) for name, rows in columns}
    most = max(counts.values())
    print("Cells: open-edge solids / cracks > 1 d / silent empty faces / faces off area > 1% / faces off "
          "surface > 2 d / folded / needles / errors · triangles · seconds")
    print()
    header = "| " + (" | ".join(["file"] + [name + ("" if counts[name] == most else " (fewer solids)")
                                            for name, _ in columns])) + " |"
    print(header)
    print("|" + "---|" * (len(columns) + 1))
    if args.by == "file":
        files = collections.OrderedDict()
        for _name, rows in columns:
            for row in rows:
                files.setdefault(row["file"], None)
        for file in files:
            print("| " + " | ".join([file] + [cell(totals([r for r in rows if r["file"] == file]))
                                              for _name, rows in columns]) + " |")
    print("| " + " | ".join([f"**total ({most} solids)**"] + [cell(totals(rows)) for _name, rows in columns]) + " |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
