#!/usr/bin/env python3
"""The PCB corpus, fetched: every project ``pcb_corpus.json`` names, in an ignored folder of its own.

A manual step before a PCB benchmark (``pcb_bench.py``), never run in CI: nothing here is committed and
nothing in CI touches the network. An ``upstream`` project is downloaded from GitHub at its pinned commit,
file by file, each checked against the manifest's sha256 before it is kept; a ``build`` project is one of
this repository's code-made samples (``models/electronics``), its tracked files copied and its build run in
the copy, never in ``models/``.

    .venv/bin/python scripts/bench/pcb_fetch.py --check              # the manifest, checked; no network
    .venv/bin/python scripts/bench/pcb_fetch.py                      # every project, into tmp/pcb-corpus/
    .venv/bin/python scripts/bench/pcb_fetch.py --project ecc83 --tier small

Fetching is idempotent: a file already there with its sha256 is kept; a project is never half-written over
(each file lands by rename). Beside each project the fetch writes ``SOURCE.md`` (where it came from, at which
commit, under which licence) and the licence file itself. See ``README.md``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = Path(__file__).with_name("pcb_corpus.json")
OUT = ROOT / "tmp" / "pcb-corpus"
RAW = "https://raw.githubusercontent.com"
MAX_FILE = 10 * 1024 * 1024  # no single file over 10 MB is fetched
TIERS = ("small", "medium", "large")
KINDS = ("upstream", "build")
# Open licences only, by SPDX id: a design under any other (non-commercial, no-derivatives, none) is refused.
LICENCES = frozenset({
    "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0", "CERN-OHL-P-2.0",
    "CERN-OHL-S-2.0", "CERN-OHL-W-2.0", "GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later",
    "LGPL-2.1-or-later", "LGPL-3.0-or-later", "MIT", "MPL-2.0", "TAPR-OHL-1.0"})
COMMON = ("name", "tier", "kind", "board", "schematic", "licence")
UPSTREAM_KEYS = frozenset({*COMMON, "repo", "ref", "commit", "root", "files", "licence_file", "kicad_format",
                           "copper_layers", "footprints", "bytes", "note"})
BUILD_KEYS = frozenset({*COMMON, "sample", "build", "note"})
NAME = re.compile(r"[a-z0-9][a-z0-9_.-]*")
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
SHA1 = re.compile(r"[0-9a-f]{40}")
SHA256 = re.compile(r"[0-9a-f]{64}")
TELEMETRY_OFF = {"DO_NOT_TRACK": "1", "CAD_TELEMETRY": "0"}
BENCH_INSTALLATION = "0.0.0+bench"
REGISTER = ("import sys\nfrom cad_server._internal import installations\n"
            "installations.register(sys.argv[1])\ninstallations.point(sys.argv[1])")


# --- the manifest -------------------------------------------------------------------------------


def safe_path(value: Any, *, empty: bool = False) -> bool:
    """A relative POSIX path that stays where it is put: no absolute path, no ``..``, no backslash or NUL,
    no empty or ``.`` part (``empty`` allows ``""``, a repository's root)."""
    if not isinstance(value, str):
        return False
    if value == "":
        return empty
    if "\\" in value or "\0" in value or value.startswith("/") or re.match(r"[A-Za-z]:", value):
        return False
    return all(part not in ("", ".", "..") for part in value.split("/"))


def licence_problem(spdx: Any) -> str | None:
    """Why a licence keeps a project out of the corpus, or None for an open one."""
    if not isinstance(spdx, str) or not spdx.strip():
        return "no licence: a design without one is not in the corpus"
    if re.search(r"(^|-)NC(-|$)", spdx):
        return f"licence {spdx} forbids commercial use (NC): not in the corpus"
    if re.search(r"(^|-)ND(-|$)", spdx):
        return f"licence {spdx} forbids derivatives (ND): a benchmark changes the design"
    if spdx not in LICENCES:
        return f"licence {spdx} is not one of the open licences the corpus takes ({', '.join(sorted(LICENCES))})"
    return None


def _file_problems(entry: Any, where: str) -> list[str]:
    if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "bytes"}:
        return [f"{where}: a file is {{path, sha256, bytes}}"]
    found = []
    if not safe_path(entry["path"]):
        found.append(f"{where}: `{entry['path']}` is not a safe relative path")
    if not isinstance(entry["sha256"], str) or not SHA256.fullmatch(entry["sha256"]):
        found.append(f"{where}: `{entry['path']}`'s sha256 is 64 lowercase hex digits")
    if not isinstance(entry["bytes"], int) or isinstance(entry["bytes"], bool) or entry["bytes"] < 0:
        found.append(f"{where}: `{entry['path']}`'s bytes is a count")
    elif entry["bytes"] > MAX_FILE:
        found.append(f"{where}: `{entry['path']}` is {entry['bytes']} bytes, over the 10 MB cap")
    return found


def _upstream_problems(project: dict[str, Any], name: str) -> list[str]:
    found = []
    if not isinstance(project.get("repo"), str) or not REPO.fullmatch(project["repo"]):
        found.append(f"{name}: `repo` is owner/name")
    if not isinstance(project.get("commit"), str) or not SHA1.fullmatch(project["commit"]):
        found.append(f"{name}: `commit` is a full 40-character lowercase commit sha, not a tag or branch")
    if "ref" in project and project["ref"] is not None and not isinstance(project["ref"], str):
        found.append(f"{name}: `ref` is the tag the commit was resolved from, or null")
    root = project.get("root")
    if not safe_path(root, empty=True):
        found.append(f"{name}: `root` is a safe relative folder of the repository (\"\" for its root)")
    files = project.get("files")
    if not isinstance(files, list) or not files:
        return found + [f"{name}: `files` lists every file the project needs"]
    paths = []
    for entry in files:
        found += _file_problems(entry, name)
        if isinstance(entry, dict) and isinstance(entry.get("path"), str):
            paths.append(entry["path"])
    lowered = [path.lower() for path in paths]
    if len(set(lowered)) != len(lowered):
        found.append(f"{name}: a file is named twice (case-insensitively)")
    for key in ("board", "schematic"):
        if project.get(key) not in paths:
            found.append(f"{name}: `{key}` is one of its files")
    board = project.get("board")
    if isinstance(board, str) and board.endswith(".kicad_pcb") and board[:-len(".kicad_pcb")] + ".kicad_pro" not in paths:
        found.append(f"{name}: the board's .kicad_pro is one of its files (it carries the rules)")
    licence_file = project.get("licence_file")
    if not isinstance(licence_file, dict):
        found.append(f"{name}: `licence_file` is {{path, sha256, bytes}}, the licence's own file in the repository")
    else:
        found += _file_problems(licence_file, f"{name} licence_file")
        path = licence_file.get("path")
        if isinstance(path, str) and isinstance(root, str) and safe_path(path):
            inner = relative_to_root(path, root)
            if inner is not None and inner not in paths:
                found.append(f"{name}: a licence file inside the project's root is one of its files")
            if inner is None and PurePosixPath(path).name.lower() in {p.lower() for p in paths}:
                found.append(f"{name}: the licence file's name collides with a project file")
    for key in ("kicad_format", "copper_layers", "footprints", "bytes"):
        if not isinstance(project.get(key), int) or isinstance(project.get(key), bool) or project[key] <= 0:
            found.append(f"{name}: `{key}` is a positive count, measured from the fetched board")
    if isinstance(project.get("bytes"), int) and isinstance(files, list):
        total = sum(entry["bytes"] for entry in files
                    if isinstance(entry, dict) and isinstance(entry.get("bytes"), int))
        if total != project["bytes"]:
            found.append(f"{name}: `bytes` is {project['bytes']}, its files add to {total}")
    return found


def _build_problems(project: dict[str, Any], name: str) -> list[str]:
    found = []
    sample = project.get("sample")
    if not safe_path(sample) or not str(sample).startswith("models/electronics/"):
        found.append(f"{name}: `sample` is a folder of models/electronics")
    for key in ("build", "board", "schematic"):
        if not safe_path(project.get(key)):
            found.append(f"{name}: `{key}` is a safe relative path inside the sample")
    return found


def problems(manifest: Any) -> list[str]:
    """Everything wrong with a manifest, each as a line (none: it is well-formed)."""
    if not isinstance(manifest, dict) or not isinstance(manifest.get("projects"), list):
        return ["the manifest is {about, projects: [...]}"]
    found = [f"unknown top-level key `{key}`" for key in sorted(set(manifest) - {"about", "projects"})]
    names: set[str] = set()
    for project in manifest["projects"]:
        if not isinstance(project, dict):
            found.append("a project is an object")
            continue
        name = project.get("name")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            found.append(f"{name!r}: `name` is a folder name: lowercase letters, digits, `_`, `.` and `-`")
            name = str(name)
        elif name in names:
            found.append(f"{name}: a second project of this name")
        names.add(name)
        kind = project.get("kind")
        if kind not in KINDS:
            found.append(f"{name}: `kind` is upstream or build")
            continue
        allowed = UPSTREAM_KEYS if kind == "upstream" else BUILD_KEYS
        found += [f"{name}: unknown key `{key}`" for key in sorted(set(project) - allowed)]
        found += [f"{name}: no `{key}`" for key in COMMON if key not in project]
        if project.get("tier") not in TIERS:
            found.append(f"{name}: `tier` is small, medium or large")
        said = licence_problem(project.get("licence"))
        if said:
            found.append(f"{name}: {said}")
        found += _upstream_problems(project, name) if kind == "upstream" else _build_problems(project, name)
    return found


def relative_to_root(path: str, root: str) -> str | None:
    """``path`` (the repository's) inside the project's ``root``, or None when it lies outside it."""
    if not root:
        return path
    return path[len(root) + 1:] if path.startswith(root + "/") else None


def selected(manifest: dict[str, Any], names: list[str], tiers: list[str]) -> list[dict[str, Any]]:
    """The projects named and of the tiers given (every one, when neither is)."""
    known = {project["name"] for project in manifest["projects"]}
    unknown = sorted(set(names) - known)
    if unknown:
        raise SystemExit(f"pcb_fetch: no project {', '.join(unknown)} in the manifest")
    return [project for project in manifest["projects"]
            if (not names or project["name"] in names) and (not tiers or project["tier"] in tiers)]


# --- the files ----------------------------------------------------------------------------------


def inside(folder: Path, relative: str) -> Path:
    """``folder / relative``, refused when it would leave ``folder`` or pass through a symlink."""
    if not safe_path(relative):
        raise ValueError(f"refuses unsafe path {relative!r}")
    target = folder / relative
    walked = folder
    for part in PurePosixPath(relative).parts:
        walked = walked / part
        if walked.is_symlink():
            raise ValueError(f"refuses symlink {walked}")
    if not target.resolve().is_relative_to(folder.resolve()):
        raise ValueError(f"{relative!r} escapes {folder}")
    return target


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def verified(path: Path, entry: dict[str, Any]) -> bool:
    """The file is there, no symlink, of the manifest's size and sha256."""
    return (path.is_file() and not path.is_symlink() and path.stat().st_size == entry["bytes"]
            and sha256(path) == entry["sha256"])


def download(url: str, limit: int = MAX_FILE) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "text-to-cad pcb_fetch"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise SystemExit(f"pcb_fetch: could not download {url}: {error}") from None
    if len(data) > limit:
        raise SystemExit(f"pcb_fetch: {url} is over the {limit // (1024 * 1024)} MB cap; refused")
    return data


def place(folder: Path, relative: str, entry: dict[str, Any], url: str) -> str:
    """One file at ``folder/relative``, fetched from ``url`` unless already there and verified."""
    target = inside(folder, relative)
    if verified(target, entry):
        return "kept"
    data = download(url)
    if len(data) != entry["bytes"] or hashlib.sha256(data).hexdigest() != entry["sha256"]:
        raise SystemExit(f"pcb_fetch: {url} does not match the manifest (size {len(data)}, sha256 "
                         f"{hashlib.sha256(data).hexdigest()}); nothing kept")
    target.parent.mkdir(parents=True, exist_ok=True)
    inside(folder, relative)  # a folder made above cannot be a symlink, but a raced one is refused
    partial = target.with_name(target.name + ".part")
    partial.write_bytes(data)
    os.replace(partial, target)
    return "fetched"


def raw_url(project: dict[str, Any], path: str) -> str:
    return f"{RAW}/{project['repo']}/{project['commit']}/{urllib.parse.quote(path)}"


def source_note(project: dict[str, Any], licence_name: str) -> str:
    if project["kind"] == "upstream":
        where = f"{project['root']}/" if project["root"] else ""
        url = f"https://github.com/{project['repo']}/tree/{project['commit']}/{urllib.parse.quote(where)}"
        origin = (f"- Repository: https://github.com/{project['repo']}\n- Commit: {project['commit']}"
                  + (f" (tag {project['ref']})" if project.get("ref") else "") + f"\n- Folder: {url}\n")
    else:
        origin = f"- text-to-cad's own sample `{project['sample']}`, built by `{project['build']}`\n"
    return (f"# {project['name']}\n\n{origin}- Licence: {project['licence']} (`{licence_name}`)\n"
            f"- Board: `{project['board']}`; schematic: `{project['schematic']}`\n")


def fetch_upstream(project: dict[str, Any], out: Path) -> dict[str, int]:
    folder = out / project["name"]
    folder.mkdir(parents=True, exist_ok=True)
    if folder.is_symlink():
        raise ValueError(f"refuses symlink {folder}")
    counts = {"kept": 0, "fetched": 0}
    root = project["root"]
    for entry in project["files"]:
        repo_path = f"{root}/{entry['path']}" if root else entry["path"]
        counts[place(folder, entry["path"], entry, raw_url(project, repo_path))] += 1
    licence = project["licence_file"]
    inner = relative_to_root(licence["path"], root)
    if inner is None:  # the repository's own, outside the project's folder: kept beside it by its name
        counts[place(folder, PurePosixPath(licence["path"]).name, licence, raw_url(project, licence["path"]))] += 1
    inside(folder, "SOURCE.md").write_text(source_note(project, PurePosixPath(licence["path"]).name), encoding="utf-8")
    return counts


# --- the code-made samples ----------------------------------------------------------------------


def tracked(sample: str) -> list[str]:
    """The sample's files Git tracks, relative to it: what a clean checkout builds from. A tracked symlink
    is refused."""
    listed = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-s", "-z", "--", sample],
                            capture_output=True, check=True).stdout.decode("utf-8").split("\0")
    files = []
    for line in filter(None, listed):
        meta, path = line.split("\t", 1)
        if meta.startswith("120000"):
            raise ValueError(f"refuses tracked symlink {path}")
        files.append(path[len(sample) + 1:])
    if not files:
        raise SystemExit(f"pcb_fetch: {sample} has no tracked files")
    return sorted(files)


def private_env(runtime: Path, python: str) -> dict[str, str]:
    """An environment whose engine, state, cache and command folders are the corpus's own, with the
    interpreter's own ``cad`` first on PATH: a build never reaches the person's engine or installation."""
    env = {**os.environ, "CAD_ENGINE_DIR": str(runtime / "engine"), "CAD_STATE_DIR": str(runtime / "state"),
           "CAD_CACHE_DIR": str(runtime / "cache"), "CAD_LAUNCHER_DIR": str(runtime / "launcher"),
           "CAD_ENGINE_PORT": "0", "CAD_ENGINE_STANDBY": "0", "BROWSER": "true",
           "PATH": os.pathsep.join([str(Path(python).parent), os.environ.get("PATH", "")]), **TELEMETRY_OFF}
    env.pop("PYTHONDONTWRITEBYTECODE", None)
    return env


def fetch_build(project: dict[str, Any], out: Path, runtime: Path, python: str) -> dict[str, int]:
    sample = project["sample"]
    files = tracked(sample)
    digest = hashlib.sha256()
    for relative in files:
        digest.update(relative.encode() + b"\0" + hashlib.sha256((ROOT / sample / relative).read_bytes()).digest())
    stamp_value = digest.hexdigest()
    folder = out / project["name"]
    stamp = folder / ".built-from"
    if stamp.is_file() and stamp.read_text().strip() == stamp_value and (folder / project["board"]).is_file():
        return {"kept": len(files), "built": 0}
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    for relative in files:
        target = inside(folder, relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / sample / relative, target)
    env = private_env(runtime, python)
    registered = subprocess.run([python, "-c", REGISTER, BENCH_INSTALLATION], env=env, capture_output=True, text=True)
    if registered.returncode:
        raise SystemExit(f"pcb_fetch: could not register {python} as the corpus's installation: {registered.stderr[-500:]}")
    build = inside(folder, project["build"])
    started = time.monotonic()
    done = subprocess.run([python, build.name], cwd=build.parent, env=env)
    if done.returncode:
        raise SystemExit(f"pcb_fetch: {project['name']}'s build failed (exit {done.returncode})")
    if not (folder / project["board"]).is_file():
        raise SystemExit(f"pcb_fetch: {project['name']}'s build wrote no {project['board']}")
    shutil.copy2(ROOT / "LICENSE", inside(folder, "LICENSE.text-to-cad"))
    inside(folder, "SOURCE.md").write_text(source_note(project, "LICENSE.text-to-cad"), encoding="utf-8")
    stamp.write_text(stamp_value + "\n", encoding="utf-8")
    print(f"  built in {time.monotonic() - started:.0f} s", file=sys.stderr)
    return {"kept": 0, "built": len(files)}


def stop_engine(runtime: Path, python: str) -> None:
    if (runtime / "state").exists():
        subprocess.run([python, "-m", "cad_server.cli", "stop"], env=private_env(runtime, python),
                       capture_output=True, text=True, timeout=300)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--out", type=Path, default=OUT, help="the corpus folder (default tmp/pcb-corpus)")
    parser.add_argument("--project", action="append", default=[], help="one project (repeat for more)")
    parser.add_argument("--tier", action="append", default=[], choices=TIERS, help="one tier (repeat for more)")
    parser.add_argument("--check", action="store_true", help="check the manifest and stop: no network")
    args = parser.parse_args(argv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    found = problems(manifest)
    if found:
        print("\n".join(f"pcb_fetch: {line}" for line in found), file=sys.stderr)
        return 1
    chosen = selected(manifest, args.project, args.tier)
    if args.check:
        print(f"pcb_fetch: {len(manifest['projects'])} projects, well-formed")
        return 0
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    runtime = out / ".runtime"
    python = sys.executable
    try:
        for project in chosen:
            print(f"==> {project['name']} ({project['tier']}, {project['kind']})", file=sys.stderr, flush=True)
            if project["kind"] == "upstream":
                counts = fetch_upstream(project, out)
            else:
                counts = fetch_build(project, out, runtime, python)
            print(f"  {project['name']}: " + ", ".join(f"{value} {key}" for key, value in counts.items()), file=sys.stderr)
    finally:
        stop_engine(runtime, python)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
