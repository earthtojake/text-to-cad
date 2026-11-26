#!/usr/bin/env python3
"""Regenerate every file generated from the code: the documentation site's references and its copy of the registry,
and @cad/core's table of document types and copy of the engine's look. `--check` writes nothing and says which are
stale.

Each file is the text a function of its source's own module returns -- what the test that holds the file to its source
compares, and of the first four what `python -m <module> <flag>` prints -- made in a Python of its own that imports
this checkout's packages (`packages/cad/src`), never an installed cad:

| File | Made by | Held by |
| --- | --- | --- |
| `apps/docs/src/lib/docs/cli-reference.generated.json` | `python -m cad_server._internal.cli_reference --docs` | `test_cli_reference.py` |
| `apps/docs/src/lib/docs/library-reference.generated.json` | `python -m cad._internal.reference --docs` | `test_library_reference.py` |
| `apps/docs/src/lib/docs/registry.generated.json` | `python -m cad.registry --docs` | `test_registry.py` |
| `packages/core/src/lib/documentTypes.generated.js` | `python -m cad.registry --js` | `test_registry.py` |
| `packages/core/src/lib/xbf/look.generated.js` | `cad.engine.render.look.as_js()` | `test_look.py` |

    scripts/generated/regenerate.py           # each file whose text its source makes otherwise now, written
    scripts/generated/regenerate.py --check   # nothing written: exit 1 naming each stale file

The text is taken as the module's function returns it and written as UTF-8 bytes, so it is the same on every system
(a Windows console's encoding and line endings never reach it). The Python is the one the test runners take
(`scripts/test/common.sh`): `PYTHON_BIN`, else the checkout's `.venv`, else this one. Exit 2 where a source fails to
make its text, with what it said.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCES = REPO_ROOT / "packages" / "cad" / "src"
# Each generated file, by its path in the checkout: the module that makes it and the function that returns its text.
GENERATED = (
    ("apps/docs/src/lib/docs/cli-reference.generated.json", "cad_server._internal.cli_reference", "as_docs_json"),
    ("apps/docs/src/lib/docs/library-reference.generated.json", "cad._internal.reference", "as_docs_json"),
    ("apps/docs/src/lib/docs/registry.generated.json", "cad.registry", "as_docs_json"),
    ("packages/core/src/lib/documentTypes.generated.js", "cad.registry", "as_js"),
    ("packages/core/src/lib/xbf/look.generated.js", "cad.engine.render.look", "as_js"),
)
# Run in the child: the module's function, its text written to stdout as UTF-8, untranslated.
_MAKE = ("import importlib, sys; "
         "sys.stdout.buffer.write(getattr(importlib.import_module(sys.argv[1]), sys.argv[2])().encode('utf-8'))")


def python() -> str:
    """The Python the test runners take: ``PYTHON_BIN``, else the checkout's ``.venv``, else this one."""
    given = os.environ.get("PYTHON_BIN", "").strip()
    if given:
        return given
    for found in (REPO_ROOT / ".venv" / "bin" / "python", REPO_ROOT / ".venv" / "Scripts" / "python.exe"):
        if found.is_file():
            return str(found)
    return sys.executable


def made(module: str, function: str) -> bytes:
    """The text ``module.function()`` returns, as UTF-8, made in a Python of its own on this checkout's packages;
    ``SystemExit(2)`` with what it said where it fails."""
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(filter(None, [str(SOURCES), os.environ.get("PYTHONPATH")]))}
    done = subprocess.run([python(), "-P", "-c", _MAKE, module, function], cwd=REPO_ROOT, env=env,
                          capture_output=True, check=False)
    if done.returncode != 0:
        sys.stderr.write(done.stderr.decode("utf-8", "replace"))
        raise SystemExit(f"regenerate.py: {module}.{function}() failed (exit {done.returncode})")
    return done.stdout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scripts/generated/regenerate.py",
        description="Regenerate every file generated from the code: the documentation site's command and library "
                    "references and its copy of the registry, and @cad/core's table of document types and copy of "
                    "the engine's look.")
    parser.add_argument("--check", action="store_true",
                        help="write nothing: say which files are stale, and exit 1 where any is")
    args = parser.parse_args(argv)
    stale = []
    for relative, module, function in GENERATED:
        path = REPO_ROOT / relative
        text = made(module, function)
        try:
            current = path.read_bytes() == text
        except FileNotFoundError:
            current = False
        if current:
            continue
        stale.append(relative)
        if not args.check:
            path.write_bytes(text)
    if args.check:
        for relative in stale:
            print(f"stale: {relative}")
        print(f"{len(stale)} of {len(GENERATED)} generated files stale: run scripts/generated/regenerate.py" if stale
              else f"all {len(GENERATED)} generated files are current")
        return 1 if stale else 0
    for relative in stale:
        print(f"regenerated {relative}")
    print(f"{len(stale)} regenerated, {len(GENERATED) - len(stale)} current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
