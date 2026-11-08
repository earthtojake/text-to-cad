"""The CadQuery suite's CadQuery: in the environment of ``cad[cadquery]`` the server makes, as a person's gets.

The test's own Python holds no CadQuery (``requirements-dev.txt`` installs no ``cadquery`` extra, and none
could stand beside the kernel: CadQuery's OCP is 7.9, the kernel's 8.0), so the suite runs CadQuery where
``cad run`` does: in the environment of the cadquery integration, made by
``cad_server._internal.integration_env`` (the library from this checkout, editable, and CadQuery).
``scripts/test/test-cadquery.sh`` makes it once and names its Python in ``CAD_TEST_CADQUERY_PYTHON``, so every
test file reuses it; a file run on its own makes it (from uv's cache, after the first) or skips, saying why.
"""

from __future__ import annotations

import functools
import os
import subprocess
import sys
import unittest
from typing import Any

__all__ = ["VARIABLE", "python", "run"]

VARIABLE = "CAD_TEST_CADQUERY_PYTHON"


@functools.cache
def _made() -> str:
    from cad_server._internal import integration_env

    return integration_env.environment("cadquery", lambda line: print(line, file=sys.stderr))


def python(case: unittest.TestCase | None = None) -> str:
    """The Python of the cadquery integration's environment; a test that cannot have one skips."""
    named = os.environ.get(VARIABLE, "").strip()
    if named:
        return named
    try:
        return _made()
    except Exception as error:  # noqa: BLE001 - uv or the network: the test says why it skips
        if case is None:
            raise
        case.skipTest(f"the environment of cad[cadquery] could not be made: {error}")
        raise


def run(case: unittest.TestCase, *args: str, **options: Any) -> subprocess.CompletedProcess:
    """``python ARGS`` run by the environment's Python, its output as text."""
    options.setdefault("capture_output", True)
    options.setdefault("text", True)
    options.setdefault("timeout", 600)
    return subprocess.run([python(case), *args], check=False, **options)
