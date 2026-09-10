#!/usr/bin/env python3
"""Search step.parts for common standard parts and download STEP files."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_ORIGIN = "https://api.step.parts"
DEFAULT_OUT_DIR = tempfile.gettempdir()
USER_AGENT = "step-parts-skill/1.0"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Search the step.parts hosted catalog for low-level common standard parts "
            "(screws, bolts, bearings, electronics parts, motors, connectors, etc.) "
            "and optionally download canonical STEP files."
        ),
    )
    parser.add_argument("query", nargs="?", help="Fuzzy search query, for example 'M3 socket head 12'.")
    parser.add_argument("--id", dest="part_id", help="Fetch a specific part id instead of searching.")
    parser.add_argument("--origin", default=DEFAULT_ORIGIN, help=f"API origin. Default: {DEFAULT_ORIGIN}")
    parser.add_argument("--download", action="store_true", help="Download the selected STEP file.")
    parser.add_argument("--all", action="store_true", help="With --download, download every result on the returned page.")
    parser.add_argument("--out-dir", default=DEFAULT_OUT_DIR, help="Directory for downloaded STEP files. Default: active temp directory.")
    parser.add_argument("--filename", help="Filename to use when downloading one selected part.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite an existing downloaded file.")
    parser.add_argument("--limit", type=int, default=10, help="Search page size. The API caps this at 500.")
    parser.add_argument("--page", type=int, default=1, help="1-based search page.")
    parser.add_argument("--tag", action="append", default=[], help="Repeatable tag filter.")
    parser.add_argument("--category", action="append", default=[], help="Repeatable category filter.")
    parser.add_argument("--family", action="append", default=[], help="Repeatable family filter.")
    parser.add_argument("--standard", action="append", default=[], help="Repeatable standard filter, for example 'ISO 4762'.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds.")
    return parser.parse_args()


def origin_url(origin: str) -> str:
    parsed = urllib.parse.urlparse(origin)
    if not parsed.scheme or not parsed.netloc:
        raise SystemExit(f"Invalid origin: {origin!r}")
    return origin.rstrip("/")


def build_url(origin: str, path: str, params: list[tuple[str, str]] | None = None) -> str:
    url = f"{origin_url(origin)}{path}"
    if params:
        return f"{url}?{urllib.parse.urlencode(params)}"
    return url


def request(url: str, timeout: float) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"HTTP {exc.code} for {url}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to fetch {url}: {exc.reason}") from exc


def fetch_json(url: str, timeout: float) -> Any:
    data = request(url, timeout)
    try:
        return json.loads(data)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Expected JSON from {url}: {exc}") from exc


def search_parts(args: argparse.Namespace) -> dict[str, Any]:
    params: list[tuple[str, str]] = [
        ("page", str(max(1, args.page))),
        ("pageSize", str(max(1, args.limit))),
    ]
    if args.query:
        params.append(("q", args.query))
    for key in ("tag", "category", "family", "standard"):
        for value in getattr(args, key):
            params.append((key, value))
    return fetch_json(build_url(args.origin, "/v1/parts", params), args.timeout)


def get_part(args: argparse.Namespace, part_id: str) -> dict[str, Any]:
    safe_id = urllib.parse.quote(part_id, safe="")
    return fetch_json(build_url(args.origin, f"/v1/parts/{safe_id}"), args.timeout)


def selected_parts(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.part_id:
        return [get_part(args, args.part_id)]

    result = search_parts(args)
    items = result.get("items", [])
    if not items:
        raise SystemExit("No parts matched the query.")
    if args.download and args.all:
        return items
    return [items[0]]


def filename_for(part: dict[str, Any], requested_filename: str | None, allow_requested: bool) -> str:
    if requested_filename and allow_requested:
        return requested_filename
    step_url = str(part.get("stepUrl") or "")
    name = Path(urllib.parse.urlparse(step_url).path).name
    if name:
        return name
    return f"{part['id']}.step"


def step_download_url(part: dict[str, Any], origin: str) -> str:
    step_url = part.get("stepUrl")
    if not step_url:
        raise SystemExit(f"Part {part.get('id', '<unknown>')} does not include stepUrl.")
    return urllib.parse.urljoin(f"{origin_url(origin)}/", str(step_url))


def write_download(part: dict[str, Any], args: argparse.Namespace, allow_requested_filename: bool) -> dict[str, Any]:
    step_url = step_download_url(part, args.origin)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename_for(part, args.filename, allow_requested_filename)
    if path.exists() and not args.overwrite:
        raise SystemExit(f"Refusing to overwrite existing file: {path}")

    data = request(step_url, args.timeout)
    path.write_bytes(data)

    actual_sha256 = hashlib.sha256(data).hexdigest()
    expected_sha256 = part.get("sha256")
    checksum_ok = expected_sha256 is None or expected_sha256 == actual_sha256
    if not checksum_ok:
        raise SystemExit(
            f"Checksum mismatch for {path}: expected {expected_sha256}, got {actual_sha256}",
        )

    return {
        "id": part.get("id"),
        "name": part.get("name"),
        "path": str(path),
        "stepUrl": step_url,
        "pageUrl": part.get("pageUrl"),
        "apiUrl": part.get("apiUrl"),
        "byteSize": len(data),
        "sha256": actual_sha256,
        "checksumVerified": expected_sha256 is not None,
    }


def compact_part(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": part.get("id"),
        "name": part.get("name"),
        "category": part.get("category"),
        "family": part.get("family"),
        "standard": part.get("standard"),
        "attributes": part.get("attributes"),
        "stepUrl": part.get("stepUrl"),
        "pageUrl": part.get("pageUrl"),
        "apiUrl": part.get("apiUrl"),
        "sha256": part.get("sha256"),
    }


def main() -> int:
    args = parse_args()
    if args.filename and (not args.download or args.all):
        raise SystemExit("--filename can only be used with --download for one selected part.")
    if not args.part_id and not args.query and not any([args.tag, args.category, args.family, args.standard]):
        raise SystemExit("Provide a query, --id, or at least one facet filter.")

    if not args.download:
        if args.part_id:
            output: Any = compact_part(get_part(args, args.part_id))
        else:
            result = search_parts(args)
            result["items"] = [compact_part(part) for part in result.get("items", [])]
            output = result
        json.dump(output, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    parts = selected_parts(args)
    downloads = [
        write_download(part, args, allow_requested_filename=len(parts) == 1)
        for part in parts
    ]
    json.dump({"downloads": downloads}, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
