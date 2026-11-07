"""``cad fea faces|parts|solve`` are the library's verbs, run where the CAD kernel is: from an installation whose own
environment has none, the base's Python runs them (``kernel_verb``), and what comes back is what the verb returned
or raised."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.packages.cad.test_fea_assembly import _write_assembly
from tests.python.support.paths import SOURCE_PATH

from cad.results import FeaPair, FeaPartsResult  # noqa: E402
from cad_server._internal import base, kernel_verb  # noqa: E402
from cad_server.cli import fea_faces  # noqa: E402


@contextlib.contextmanager
def in_base():
    with mock.patch.object(base, "ensure", return_value=base.Environment(sys.executable, sys.prefix, False)), \
            mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}):
        yield


class FeaInTheBaseTest(unittest.TestCase):
    def test_an_assemblys_parts_and_pairs_come_back_as_their_types(self):
        with tempfile.TemporaryDirectory() as tmp, in_base(), contextlib.redirect_stderr(io.StringIO()):
            result = kernel_verb.in_kernel(("cad.fea", "parts"), prog="cad fea parts")(_write_assembly(Path(tmp)))
        self.assertIsInstance(result, FeaPartsResult)
        self.assertIsInstance(result.document, Path)
        (pair,) = result.pairs
        self.assertIsInstance(pair, FeaPair)
        self.assertEqual((pair.between, pair.type), (("post", "base"), "bonded"))

    def test_a_refusal_is_the_commands_error(self):
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, in_base(), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            missing = Path(tmp) / "missing.step"
            code = fea_faces.main([str(missing), "--json"])
        self.assertNotEqual(code, 0)
        payload = json.loads(out.getvalue().strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        self.assertIn("document does not exist", payload["error"])


if __name__ == "__main__":
    unittest.main()
