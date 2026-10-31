"""The served documents' render processes as the daemon runs them (``renders``, the supervisor's
``render`` service): a version held, frames answered with PNG bytes, and gone after a frame that
leaves one over its memory cap; ``status`` lists the live ones alone."""

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

from cad.engine.snapshot import Still  # noqa: E402
from cad_server.engine.renders import Renders  # noqa: E402
from cad_server.engine.services import RENDER  # noqa: E402
from cad_server.engine.supervisor import Process, Supervisor  # noqa: E402
from tests.python.packages.texttocad.engine.test_render import BENCH, SIZE, build, drawn, gl, served, shapes  # noqa: E402


class RenderProcessTest(unittest.TestCase):
    """The render process, as the daemon talks to it: a version held, frames answered with PNG
    bytes, and gone after a frame that leaves it over its memory cap."""

    def setUp(self) -> None:
        gl()
        self.folder = Path(tempfile.mkdtemp(prefix="engine-render-process-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)
        self.document = build(self.folder, BENCH, "bench")
        self.structure, self.buffers = served(self.document)

    def start(self, cap: str) -> Process:
        # A render process takes the daemon's environment (``RENDER.env``): this process's, here.
        with mock.patch.dict(os.environ, {"PYTHONPATH": str(SRC), "CAD_ENGINE_WORKER_RSS_MB": cap}):
            process = Process.start(RENDER, "bench", str(self.document), {})
        self.addCleanup(process.stop)
        keys = sorted(self.buffers)
        answer = process.request({"op": "hold", "path": str(self.document), "structure": self.structure,
                                  "meshes": [[key, len(self.buffers[key])] for key in keys]},
                                 None, b"".join(self.buffers[key] for key in keys))
        self.assertEqual(answer["held"]["made"], shapes(self.structure))
        return process

    def test_frames_are_answered_warm_and_a_process_over_its_cap_retires(self) -> None:
        process = self.start("0")
        still = Still({"mode": "solid"}, size=SIZE).as_json()
        first = process.request({"op": "frame", "still": still})
        drawn(first["payload"], SIZE)
        second = process.request({"op": "frame", "still": still})
        self.assertEqual((first["done"]["process"]["frames"], second["done"]["process"]["frames"]), (1, 2))
        self.assertNotIn("sceneMs", second["done"]["timings"], "the second picture is drawn on the first's scene")
        refused = process.request({"op": "frame", "still": {**still, "pose": "shut"}})
        self.assertIn("no mechanism state 'shut'", refused["refused"])
        capped = self.start("1")
        answer = capped.request({"op": "frame", "still": still})
        self.assertIn("CAD_ENGINE_WORKER_RSS_MB", answer["done"]["retired"])
        self.assertTrue(capped.retired, "it said so to the daemon too")
        self.assertEqual(capped.popen.wait(timeout=30), 0, "gone once it has answered")


class RenderStatusTest(unittest.TestCase):
    def test_a_render_process_that_is_gone_is_no_row_of_the_status(self) -> None:
        def launch(service, key, label, environment, cwd, standby):
            return SimpleNamespace(service=service, key=key, label=label, environment=environment, pid=1, rss=10,
                                   requests=0, leased=False, retired=False, used=0.0,
                                   state={"version": "v", "held": {}, "frames": 1},
                                   alive=lambda: label != "gone.xbf", stop=lambda: None)

        supervisor = Supervisor(1, (RENDER,), launch=launch)
        renders = Renders(server=None, supervisor=supervisor)
        supervisor.release(supervisor.lease("render", "live", {}, label="live.xbf"))
        supervisor.lease("render", "gone", {}, label="gone.xbf")  # it died while a picture waits on it
        self.assertEqual([row["document"] for row in renders.status()], ["live.xbf"],
                         "exited or retired, it waits for no picture to leave the status")


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
