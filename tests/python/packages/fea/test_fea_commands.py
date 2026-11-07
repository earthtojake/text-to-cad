"""``cad step fea`` and ``cad xbf fea`` are the library's operation, run where its integrations are: in the command's
own process when its environment holds the kernel and netgen, else by the library's runner of one operation
(``cad._internal.operation``) in the environment of ``cad[build123d,netgen]`` the engine makes. Here this Python
stands in for that environment, so the runner's real subprocess runs the study, and what comes back is the result
the operation returned, as its own type; a study's options are refused before any environment is made."""

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

from tests.python.packages.fea.test_fea_assembly import _write_assembly
from tests.python.support.paths import SOURCE_PATH

from cad.results import FeaResult  # noqa: E402
from cad_server._internal import integration_env  # noqa: E402
from cad_server.cli import step  # noqa: E402


@contextlib.contextmanager
def elsewhere(made: list):
    """The command's environment lacking the integrations, and this Python the one made for them."""

    def environment(integrations, told, **_):
        made.append(integrations)
        return sys.executable

    with mock.patch.object(integration_env, "carries", return_value=False), \
            mock.patch.object(integration_env, "environment", side_effect=environment), \
            mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}):
        yield


class FeaElsewhereTest(unittest.TestCase):
    def test_an_assemblys_setup_comes_back_through_the_runner_as_its_type(self):
        made: list = []
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, elsewhere(made), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(io.StringIO()):
            code = step.main(["fea", str(_write_assembly(Path(tmp))), "--json"])
        self.assertEqual(code, 0, out.getvalue())
        # The netgen integration's environment, which holds the kernel beside it (the registry's ``alongside``).
        self.assertEqual(made, ["netgen"])
        self.assertEqual(integration_env._names("netgen"), ("build123d", "netgen"))
        result = FeaResult.from_data(json.loads(out.getvalue().strip().splitlines()[-1]))
        (pair,) = result.pairs
        self.assertEqual((pair.between, pair.type), (("post", "base"), "bonded"))
        self.assertEqual([part.name for part in result.parts], ["base", "post"])
        # Two parts and no --occurrence: no faces, and a line saying how to list one part's.
        self.assertEqual(([], ["faces_of_one_part"]), (list(result.faces), [f.code for f in result.findings]))

    def test_a_solves_options_are_refused_before_any_environment_is_made(self):
        made: list = []
        for argv, said in ((["--out", "r.glb"], "--out is a solve's"),
                           (["--study", "{}"], "give --out RESULT.glb"),
                           (["--study", "{}", "--out", "r.stl"], "must end in .glb")):
            with self.subTest(argv=argv), tempfile.TemporaryDirectory() as tmp, elsewhere(made), \
                    contextlib.redirect_stderr(io.StringIO()) as err, contextlib.redirect_stdout(io.StringIO()):
                part = _write_assembly(Path(tmp))
                self.assertEqual(step.main(["fea", str(part), *argv]), 2)
                self.assertIn(said, err.getvalue())
        self.assertEqual(made, [])


if __name__ == "__main__":
    unittest.main()
