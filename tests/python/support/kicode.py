"""The KiCad suite's KiCad: kicode, in the environment of ``cad[kicad]`` the server makes, as a person's gets.

The test's own Python holds no kicode (``requirements-dev.txt`` installs no ``kicad`` extra), so the suite
runs KiCad where the ``cad`` command does: in the environment of the kicad integration, made by
``cad_server._internal.integration_env`` (the library from this checkout, editable, with kicode).
``scripts/test/test-kicad.sh`` makes it once and names its Python in ``CAD_TEST_KICODE_PYTHON``, so every
test file reuses it; a file run on its own makes it (from uv's cache, after the first) or skips, saying why.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any

__all__ = ["call", "kicad_cli", "python", "run_python"]

VARIABLE = "CAD_TEST_KICODE_PYTHON"


@functools.cache
def _made() -> str:
    from cad_server._internal import integration_env

    return integration_env.environment("kicad", lambda line: print(line, file=sys.stderr))


def python(case: unittest.TestCase | None = None) -> str:
    """The Python of the kicad integration's environment; a test that cannot have one skips."""
    named = os.environ.get(VARIABLE, "").strip()
    if named:
        return named
    try:
        return _made()
    except Exception as error:  # noqa: BLE001 - uv or the network: the test says why it skips
        if case is None:
            raise
        case.skipTest(f"the environment of cad[kicad] could not be made: {error}")
        raise


def run_python(case: unittest.TestCase, code: str, *args: str, **options: Any) -> subprocess.CompletedProcess:
    """``code`` run by the environment's Python (``-c``), its output as text."""
    options.setdefault("capture_output", True)
    options.setdefault("text", True)
    options.setdefault("timeout", 600)
    return subprocess.run([python(case), "-c", code, *args], check=False, **options)


def kicad_cli(case: unittest.TestCase) -> Path:
    """kicode's kicad-cli, as the environment's Python finds it."""
    done = run_python(case, "import kicode; print(kicode.executable())")
    case.assertEqual(0, done.returncode, done.stderr)
    return Path(done.stdout.strip())


def call(case: unittest.TestCase, operation: str, *args: Any) -> dict[str, Any]:
    """``cad.kicad_pcb.<operation>(*args)`` run in the environment, as the ``cad`` command runs it: its
    result as data (``cad_server._internal.integration_env.call``)."""
    from cad_server._internal import integration_env

    return integration_env.call(python(case), "kicad_pcb", operation, [str(arg) for arg in args], {})


def environment(case: unittest.TestCase, root: Path) -> dict[str, str]:
    """The variables a headless run of kicode's kicad-cli sets, its homes inside ``root``."""
    done = run_python(case, "import json, sys, kicode; print(json.dumps(kicode.environment(sys.argv[1])))", str(root))
    case.assertEqual(0, done.returncode, done.stderr)
    return {**os.environ, **json.loads(done.stdout)}
