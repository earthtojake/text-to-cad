"""What the quiddity integration's tests share (``tests/python/packages/cad/test_quiddity_*.py``): a module named
``quiddity`` on the recogniser's path, standing in for the real one, so the process and its frames are the real
ones and what quiddity does with a part is the test's to say."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from cad.quiddity import _process

# A stand-in for quiddity: what it does with a part is the part's own first word.
STAND_IN = """
import json, os, threading

__version__ = "0.0.0"


def recognise(step):
    word = bytes(step).split()[0]
    if word == b"hang":
        threading.Event().wait()
    if word == b"die":
        os._exit(7)
    if word == b"refuse":
        raise ValueError("no solid in the file")
    if word == b"panic":
        raise RuntimeError("index out of bounds")
    return json.dumps({"document": {"schema_version": "stand-in"}})


def anchors(step):
    return "[]"
"""

#: A quiddity that does not import, as on a machine it was never built for.
UNIMPORTABLE = "raise ImportError('no wheel was built for this machine')\n"


class StandIn(unittest.TestCase):
    """A folder first on the recogniser's path, for a module that stands in for quiddity there."""

    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="quiddity-stand-in-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        path = os.pathsep.join(filter(None, [str(self.folder), os.environ.get("PYTHONPATH")]))
        patched = mock.patch.dict(os.environ, {"PYTHONPATH": path})
        patched.start()
        self.addCleanup(patched.stop)
        # The recogniser is this interpreter, whatever this environment holds.
        python = mock.patch.object(_process, "_python", lambda: (sys.executable, True))
        python.start()
        self.addCleanup(python.stop)

    def stand_in(self, source: str) -> None:
        (self.folder / "quiddity.py").write_text(textwrap.dedent(source), encoding="utf-8")
