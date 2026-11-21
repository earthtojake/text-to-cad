"""A CNC check's holes read by quiddity in an engine whose checks processes lack it: their environment is the
base, which holds no quiddity, so the recogniser a check starts runs in the quiddity integration's environment,
asked of the engine over its door from inside the checks process, while that process measures the check. Here
the checks processes of an engine of this file's own find no quiddity (a ``sitecustomize`` says so there, and
nowhere else), and the engine answers with its own environment, which holds it. On an engine, a state and a
cache folder of this file's own."""

from __future__ import annotations

import importlib.util
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.dfm_cnc import A, _part
from tests.python.support.manufacturing_fixtures import SRC, _counts

QUIDDITY = importlib.util.find_spec("quiddity") is not None
NEEDS = "quiddity is the quiddity extra's: uv sync installs it"

# In the engine's checks processes alone: no quiddity is found there, as in a base environment, and each time
# one is looked for the process says so (``CAD_TEST_NO_QUIDDITY``: the file its pid is added to). The suite's own
# ``sitecustomize`` (the journal's, which this one would hide) runs after it.
BASE = """
import os
import sys


def _base():
    asked = os.environ.get("CAD_TEST_NO_QUIDDITY")
    if not asked or "cad.engine.worker" not in " ".join(getattr(sys, "orig_argv", sys.argv)):
        return
    import importlib.util

    real = importlib.util.find_spec

    def find_spec(name, *rest):
        if name != "quiddity":
            return real(name, *rest)
        with open(asked, "a", encoding="utf-8") as handle:
            handle.write(f"{os.getpid()}\\n")
        return None

    importlib.util.find_spec = find_spec


_base()
if os.path.isfile(JOURNAL):
    with open(JOURNAL, encoding="utf-8") as _source:
        exec(compile(_source.read(), JOURNAL, "exec"))
"""


def setUpModule() -> None:
    engine_daemon.isolate(unittest.addModuleCleanup, started=False)


@unittest.skipUnless(QUIDDITY, NEEDS)
class RecogniserTest(unittest.TestCase):
    def test_a_checks_process_that_lacks_quiddity_has_its_environment_from_the_engine_while_it_measures(self) -> None:
        import build123d as bd

        import cad
        from cad.build123d import _dfm_cnc_recognised
        from cad.engine import api

        folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-recogniser-")))
        self.addCleanup(shutil.rmtree, folder, True)
        asked = folder / "asked"
        (folder / "site").mkdir()
        (folder / "site" / "sitecustomize.py").write_text(
            f"JOURNAL = {str(engine_daemon.SITE / 'sitecustomize.py')!r}\n{BASE}", encoding="utf-8")
        env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_TEST_NO_QUIDDITY": str(asked)},
                                    self.addCleanup, started=False)
        env["PYTHONPATH"] = os.pathsep.join((str(folder / "site"), env["PYTHONPATH"]))
        engine_daemon.start(env, self.addCleanup)
        # a 16 mm bore 12 deep whose floor's edge is rounded: blind to quiddity, through to the detector's ray
        part = bd.Box(60, 40, 20) - bd.Pos(0, 0, 10) * bd.Cylinder(8, 12, align=(A.CENTER, A.CENTER, A.MAX))
        part = bd.fillet([edge for edge in part.edges() if edge.geom_type == bd.GeomType.CIRCLE
                          and abs(edge.center().Z + 2) < 1e-6], 1.0)
        step = folder / "capped.step"
        bd.export_step(_part(part, "capped"), str(step))
        before = _counts()
        result = cad.step.dfm(step, process="cnc", material="aluminum")
        self.assertEqual(_counts()["measured"], before["measured"] + 1, "measured by the engine's checks process")
        (pid,) = set(asked.read_text(encoding="utf-8").split())
        self.assertIn(int(pid), [process["pid"] for process in api.status()["checks"]["pool"]["processes"]],
                      "which looked for quiddity and found none")
        holes = result.measurements["holes"]
        self.assertEqual(holes["recognition"], {
            "library": "quiddity", "version": _dfm_cnc_recognised.QUIDDITY, "holes": {"quiddity": 1, "cad": 0},
            "parts": {"quiddity": 1, "cad": 0}, "fallbacks": [], "declined": [],
            "disagreements": [{"location": holes["items"][0]["location"], "field": "through", "quiddity": False,
                               "cad": True}], "repeatable": True})
        self.assertEqual((holes["items"][0]["through"], holes["items"][0]["bottom"]), (False, "flat"))
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
