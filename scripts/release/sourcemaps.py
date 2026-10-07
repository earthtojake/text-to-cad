#!/usr/bin/env python3
"""The pages' source maps, gathered for the release to upload to PostHog (`release-publish.yml`).

The CAD Viewer's client and the CAD app's page are built with hidden source maps and a debug id on
every chunk with code of its own (apps/web/vite.config.mjs, apps/mcp/vite.config.mjs), and a crash on
either page names the chunk each of its frames ran in by that id (@text-to-cad/core's crash reporter).
The maps never ship in the wheel. This gathers each such chunk -- the text the page runs -- with its map
into one directory, for `posthog-cli sourcemap upload`, and zips them for the GitHub Release, so any
version's maps can be uploaded again. The CLI files a map under the id a chunk's `//# chunkId=` line names
(it uploads chunk and map as they are, and reads no bundler's debug id), so each gathered copy -- never
the page -- ends with that line naming the chunk's own debug id: what a crash's frame names. A line
after the code moves no code, so the map fits the copy as it fits the page.

    python3 scripts/release/sourcemaps.py collect --out DIR [--zip FILE]

It fails when a page built no maps, when a map has no debug id, or when a chunk and its map name
different ones: a release whose crashes PostHog could not show the source of stops here.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
# Each page: the built page, the table in it that names every chunk a crash on it can name (by debug id),
# and the directory its chunks lie in beside their maps.
PAGES = {
    "viewer": (Path("apps/web/dist/index.html"), re.compile(r"globalThis\.__cadChunkIds=(\{[^}]*\})"),
               Path("apps/web/dist/assets")),
    "cad-app": (Path("apps/mcp/dist/index.html"), re.compile(r"\bIDS=(\{[^}]*\})"), Path("apps/mcp/dist/sourcemaps")),
}
DEBUG_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
COMMENT = re.compile(r"^//# debugId=(\S+)\s*$")
CHUNK_ID_LINE = "\n//# chunkId={}"  # the line posthog-cli reads a chunk's id from (its CHUNKID_COMMENT_PREFIX)


class Unfit(Exception):
    """A page's maps PostHog could not use."""


def chunk_debug_id(text: str) -> str | None:
    """The debug id a chunk's last lines name (`//# debugId=`), as the bundler ends a chunk with it."""
    for line in reversed(text.rstrip().splitlines()[-3:]):
        match = COMMENT.match(line.strip())
        if match:
            return match.group(1)
    return None


def chunks_of(page: Path, table: re.Pattern[str]) -> dict[str, str]:
    """The chunks a crash on ``page`` can name, by file name, and their debug ids: the table its build
    wrote into it."""
    found = table.search(page.read_text(encoding="utf-8"))
    if found is None:
        raise Unfit(f"{page} names no chunk's debug id: its build wrote no table")
    ids = json.loads(found.group(1))
    if not ids or not all(isinstance(value, str) and DEBUG_ID.fullmatch(value) for value in ids.values()):
        raise Unfit(f"{page}'s table of debug ids is empty or holds something else")
    return ids


def pairs(directory: Path, ids: dict[str, str]) -> list[tuple[Path, Path, str]]:
    """Each named chunk in ``directory``, its map (``name.js.map``), and the debug id both name."""
    found = []
    for name, debug_id in sorted(ids.items()):
        chunk, source_map = directory / name, directory / f"{name}.map"
        if not chunk.is_file() or not source_map.is_file():
            raise Unfit(f"{chunk} or its map is not there")
        map_id = json.loads(source_map.read_text(encoding="utf-8")).get("debugId")
        chunk_id = chunk_debug_id(chunk.read_text(encoding="utf-8"))
        if not map_id == chunk_id == debug_id:
            raise Unfit(f"{chunk} names debug id {chunk_id}, its map {map_id}, its page {debug_id}")
        found.append((chunk, source_map, debug_id))
    return found


def collect(out: Path, *, root: Path = REPO_ROOT, pages: dict = PAGES) -> dict[str, int]:
    """Copy every page's named chunks and their maps into ``out/<page>/``: how many each page has."""
    if out.exists():
        shutil.rmtree(out)
    counts = {}
    for name, (page, table, directory) in pages.items():
        if not (root / page).is_file():
            raise Unfit(f"{page} is not there: build the pages first (scripts/bundle/bundle.sh)")
        found = pairs(root / directory, chunks_of(root / page, table))
        target = out / name
        target.mkdir(parents=True)
        for chunk, source_map, debug_id in found:
            text = chunk.read_text(encoding="utf-8").rstrip("\n")
            (target / chunk.name).write_text(text + CHUNK_ID_LINE.format(debug_id) + "\n", encoding="utf-8")
            shutil.copy2(source_map, target / source_map.name)
        counts[name] = len(found)
    return counts


def archive(directory: Path, zip_path: Path) -> None:
    """``directory``'s files, under their paths in it, as one zip."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive_file:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                archive_file.write(path, path.relative_to(directory).as_posix())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gather the pages' chunks and source maps for PostHog.")
    commands = parser.add_subparsers(dest="command", required=True)
    gather = commands.add_parser("collect", help="copy every page's chunks and maps into one directory")
    gather.add_argument("--out", type=Path, required=True, help="the directory to gather them in")
    gather.add_argument("--zip", type=Path, help="also zip the directory here, for the GitHub Release")
    args = parser.parse_args(argv)
    try:
        counts = collect(args.out)
    except Unfit as error:
        print(f"sourcemaps: {error}", file=sys.stderr)
        return 1
    if args.zip:
        archive(args.out, args.zip)
    print(", ".join(f"{page}: {count} chunks" for page, count in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
