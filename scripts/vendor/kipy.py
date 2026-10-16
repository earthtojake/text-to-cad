#!/usr/bin/env python3
"""Vendor kicad-python (``kipy``) into ``packages/cadgen/src/cadgen/kipy``.

    scripts/vendor/kipy.py            regenerate the tree in place
    scripts/vendor/kipy.py --check    regenerate into scratch and diff it against the tree

cadgen drives KiCad through kicad-python, KiCad's own API client. No PyPI release of it
targets the KiCad 11 API (the 10.99 nightly) and PyPI forbids git dependencies, so the
package is vendored: the upstream ``kipy`` tree at a pinned commit, verbatim, with its
protobuf modules generated from the KiCad commit that commit pins, and its absolute
self-imports (``from kipy.x import``, ``import kipy.x``) rewritten to ``cadgen.kipy``. The
one subtraction is ``kipy/packaging``, kicad-python's plugin packager CLI, which needs
``jsonschema`` and which nothing in cadgen calls. When kicad-python releases for KiCad 11,
cadgen depends on it and this tree goes.

The pins live in ONE place, the tree's own ``VENDOR.json``: the two commits (kicad-python,
and the KiCad commit whose ``api/proto`` the protobufs come from), the version string the
KiCad commit reports (what upstream's build derives from ``git describe``; a tarball has no
git metadata), and the generator toolchain, every version exact. To move them, edit that
file and run this script; ``--check`` then proves the committed tree is what the pins make.

The toolchain is installed into a scratch environment by ``uv`` (``requirements-dev.txt``):
``protoc-wheel-0`` (protoc, pip-installable for Linux, macOS and Windows), ``mypy-protobuf``
(the ``.pyi`` stubs), ``protoletariat`` (``protol``, which turns protoc's absolute imports
into relative ones), and the ``protobuf`` runtime the plugin needs. Everything is pinned, so
the output is reproducible on any Python the package supports (3.11 to 3.13); the committed
tree is byte-for-byte what a fresh run writes. Called by hand when a pin moves; checked by
``tests/python/global/test_kipy_vendor.py`` (the tree's integrity, no network) and by this
script's ``--check``, which downloads.
"""

from __future__ import annotations

import argparse
import datetime as dt
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TARGET = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "kipy"
VENDOR_JSON = "VENDOR.json"

KICAD_PYTHON_ARCHIVE = "https://gitlab.com/kicad/code/kicad-python/-/archive/{sha}/kicad-python-{sha}.tar.gz"
KICAD_PROTO_ARCHIVE = "https://gitlab.com/kicad/code/kicad/-/archive/{sha}/kicad-{sha}.tar.gz?path=api/proto"
GITLAB_COMMIT = "https://gitlab.com/api/v4/projects/{project}/repository/commits/{sha}"

# The subtraction, and why (see the module docstring).
OMITTED = ("packaging",)

# `from kipy.x import y`, `import kipy.x`, `import kipy` -- and nothing in a string or a
# docstring (`:meth:`~kipy.board.Board.save``), which the anchored prefix leaves alone.
_SELF_IMPORT = re.compile(r"^(\s*)(from|import)(\s+)kipy(?=[.\s]|$)", re.MULTILINE)


def _vendor_file(tree: Path) -> dict:
    return json.loads((tree / VENDOR_JSON).read_text(encoding="utf-8"))


def _download(url: str, into: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response, into.open("wb") as out:
        shutil.copyfileobj(response, out)


def _extract(archive: Path, into: Path) -> Path:
    """Unpack ``archive`` into ``into`` and return its one top-level directory."""
    with tarfile.open(archive) as tar:
        if hasattr(tarfile, "data_filter"):
            tar.extractall(into, filter="data")
        else:  # pragma: no cover - Python before the filter existed
            tar.extractall(into)
    tops = [path for path in into.iterdir() if path.is_dir()]
    if len(tops) != 1:
        raise SystemExit(f"{archive.name}: expected one top-level directory, found {sorted(p.name for p in tops)}")
    return tops[0]


def _commit_date(project: str, sha: str) -> str:
    """The commit's date from GitLab, as the record wants it (YYYY-MM-DD)."""
    with urllib.request.urlopen(GITLAB_COMMIT.format(project=project, sha=sha), timeout=60) as response:
        committed = json.load(response)["committed_date"]
    return dt.datetime.fromisoformat(committed).astimezone(dt.timezone.utc).date().isoformat()


def _tool_environment(work: Path, toolchain: dict[str, str]) -> Path:
    """A scratch environment holding exactly the pinned generator toolchain; its ``bin``."""
    uv = shutil.which("uv")
    if uv is None:
        raise SystemExit("uv is required to install the generator toolchain (requirements-dev.txt)")
    venv = work / "tools"
    subprocess.run([uv, "venv", "--quiet", "--python", sys.executable, str(venv)], check=True)
    pins = [f"{name}=={version}" for name, version in toolchain.items()]
    subprocess.run([uv, "pip", "install", "--quiet", "--python", str(_venv_python(venv)), *pins], check=True)
    return venv / ("Scripts" if sys.platform.startswith("win") else "bin")


def _venv_python(venv: Path) -> Path:
    if sys.platform.startswith("win"):
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _generate_protos(tools: Path, proto_in: Path, proto_out: Path) -> None:
    """Upstream's ``tools/generate_protos.py``, step for step: protoc with the mypy plugin, then
    protoletariat rewriting the generated imports to relative ones."""
    sources = sorted(str(path) for path in proto_in.rglob("*.proto"))
    env = dict(os.environ, PATH=str(tools) + os.pathsep + os.environ.get("PATH", ""))
    protoc = str(tools / ("protoc.exe" if sys.platform.startswith("win") else "protoc"))
    protol = str(tools / ("protol.exe" if sys.platform.startswith("win") else "protol"))
    for command in (
        [protoc, f"--python_out={proto_out}", f"--mypy_out={proto_out}", f"--proto_path={proto_in}",
         "--experimental_allow_proto3_optional", *sources],
        [protol, "--dont-create-package", "--in-place", "--exclude-google-imports", "--python-out", str(proto_out),
         "protoc", "--experimental_allow_proto3_optional", "--proto-path", str(proto_in), *sources],
    ):
        # The mypy plugin narrates every stub it writes; only a failure is worth reading.
        completed = subprocess.run(command, env=env, capture_output=True, text=True)
        if completed.returncode != 0:
            raise SystemExit(f"{Path(command[0]).name} failed:\n{completed.stdout}{completed.stderr}")


def _rewrite_imports(tree: Path) -> int:
    """``kipy`` -> ``cadgen.kipy`` in every import statement; the number of lines changed."""
    changed = 0
    for path in sorted(list(tree.rglob("*.py")) + list(tree.rglob("*.pyi"))):
        text = path.read_text(encoding="utf-8")
        new, count = _SELF_IMPORT.subn(r"\1\2\3cadgen.kipy", text)
        if count:
            path.write_text(new, encoding="utf-8")
            changed += count
    return changed


def build(vendor: dict, out: Path, work: Path) -> dict:
    """Write the vendored tree into ``out`` (which must not exist); the VENDOR.json record."""
    pins, toolchain = vendor["pins"], vendor["toolchain"]
    downloads = work / "downloads"
    downloads.mkdir()
    kicad_python_tar = downloads / "kicad-python.tar.gz"
    kicad_proto_tar = downloads / "kicad-proto.tar.gz"
    _download(KICAD_PYTHON_ARCHIVE.format(sha=pins["kicad_python"]), kicad_python_tar)
    _download(KICAD_PROTO_ARCHIVE.format(sha=pins["kicad"]), kicad_proto_tar)
    kicad_python = _extract(kicad_python_tar, work / "kicad-python")
    proto_in = _extract(kicad_proto_tar, work / "kicad") / "api" / "proto"
    if not proto_in.is_dir():
        raise SystemExit(f"the KiCad archive holds no api/proto under {proto_in.parent.parent}")

    shutil.copytree(kicad_python / "kipy", out, ignore=shutil.ignore_patterns("__pycache__"))
    for name in OMITTED:
        shutil.rmtree(out / name)
    tools = _tool_environment(work, toolchain)
    _generate_protos(tools, proto_in, out / "proto")
    (out / "kicad_api_version.py").write_text(
        "# This file is automatically generated, do not modify it\n"
        f'KICAD_API_VERSION = "{pins["kicad_api_version"]}"\n',
        encoding="utf-8",
    )
    rewritten = _rewrite_imports(out)
    shutil.copy2(kicad_python / "LICENSE", out / "LICENSE")

    record = {
        "package": "kicad-python (kipy), vendored verbatim; see scripts/vendor/kipy.py",
        "license": "MIT, Copyright The KiCad Developers (LICENSE beside this file)",
        "pins": dict(pins),
        "dates": {
            "kicad_python": _commit_date("kicad%2Fcode%2Fkicad-python", pins["kicad_python"]),
            "kicad": _commit_date("kicad%2Fcode%2Fkicad", pins["kicad"]),
        },
        "toolchain": dict(toolchain),
        "omitted": [f"kipy/{name}" for name in OMITTED],
        "imports_rewritten": rewritten,
        "generated": dt.datetime.now(dt.timezone.utc).date().isoformat(),
    }
    (out / VENDOR_JSON).write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def _differences(fresh: Path, committed: Path) -> list[str]:
    """Every path whose presence or bytes differ between the two trees, ``VENDOR.json``'s
    ``generated`` date excepted."""
    def listing(root: Path) -> dict[str, Path]:
        return {path.relative_to(root).as_posix(): path for path in root.rglob("*")
                if path.is_file() and "__pycache__" not in path.parts}

    left, right = listing(fresh), listing(committed)
    problems = [f"missing from the tree: {name}" for name in sorted(left.keys() - right.keys())]
    problems += [f"not produced by the pins: {name}" for name in sorted(right.keys() - left.keys())]
    for name in sorted(left.keys() & right.keys()):
        if name == VENDOR_JSON:
            a, b = (json.loads(p.read_text(encoding="utf-8")) for p in (left[name], right[name]))
            a.pop("generated", None), b.pop("generated", None)
            if a != b:
                problems.append(f"differs: {name}")
        elif not filecmp.cmp(left[name], right[name], shallow=False):
            problems.append(f"differs: {name}")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="regenerate into scratch and diff against the tree")
    args = parser.parse_args(argv)
    if not (TARGET / VENDOR_JSON).is_file():
        raise SystemExit(f"{TARGET / VENDOR_JSON} holds the pins and is missing")
    vendor = _vendor_file(TARGET)
    with tempfile.TemporaryDirectory(prefix="kipy-vendor-") as scratch:
        work = Path(scratch)
        fresh = work / "kipy"
        record = build(vendor, fresh, work)
        if args.check:
            problems = _differences(fresh, TARGET)
            if problems:
                print("\n".join(["cadgen/kipy does not match its pins:", *problems]), file=sys.stderr)
                return 1
            print(f"cadgen/kipy matches its pins (kicad-python {record['pins']['kicad_python']}, "
                  f"KiCad {record['pins']['kicad']})")
            return 0
        if TARGET.exists():
            shutil.rmtree(TARGET)
        shutil.copytree(fresh, TARGET)
    print(f"wrote {TARGET.relative_to(REPO_ROOT)}: kicad-python {record['pins']['kicad_python']} "
          f"({record['dates']['kicad_python']}), protos from KiCad {record['pins']['kicad']} "
          f"({record['dates']['kicad']}), {record['imports_rewritten']} imports rewritten")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
