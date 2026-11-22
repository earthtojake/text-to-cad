"""A save and a build of one script, each held open at a known step by a gate in the script's own load
(``cad_server.engine.parameters.Setting``'s turn): a save never writes the script while a build of it runs, in
any of its workers -- another Python's build is another worker's -- and a build asked while a save writes the
script or builds it again waits for the save, and reads the bytes it wrote."""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path

from tests.python.support import engine_daemon
from tests.python.support.parameters import save
from tests.python.support.paths import add_sources

add_sources()

from cad.engine import api, client  # noqa: E402
from cad.engine.ids import model_id  # noqa: E402
from cad.engine.parameters import ParameterRefused  # noqa: E402

GATED = """\
import socket
from pathlib import Path

import build123d as bd
from cad import model

WALL = model.param("wall", 2.0, min=1, max=5)
_HOLD = Path(__file__).with_name("hold")
if _HOLD.exists():  # the test's gate: this load waits until the test lets it go
    with socket.create_connection(("127.0.0.1", int(_HOLD.read_text()))) as _gate:
        _gate.recv(1)


@model
def bracket():
    return bd.Box(30, 10, WALL)
"""


class _Gate:
    """A load of the script held open: the next load to start connects (``accept``) and waits until ``release``."""

    def __init__(self, folder: Path) -> None:
        import socket

        self.hold = folder / "hold"
        self.listener = socket.create_server(("127.0.0.1", 0))
        self.listener.settimeout(120)
        self.hold.write_text(str(self.listener.getsockname()[1]), encoding="utf-8")
        self.held = None

    def accept(self) -> None:
        self.held, _address = self.listener.accept()  # a load of the script is under way, and waits
        self.hold.unlink()  # every later load goes straight through

    def release(self) -> None:
        held, self.held = self.held, None
        if held is not None:
            held.sendall(b"x")
            held.close()
        self.listener.close()
        self.hold.unlink(missing_ok=True)


class TurnTest(unittest.TestCase):
    """A save and a build of one script, each held open at a known step by a gate in the script's own load: a
    save never writes while a build of the script runs, in any worker, and a build asked while a save writes or
    builds the script waits for it."""

    @classmethod
    def setUpClass(cls) -> None:
        engine_daemon.isolate(cls.addClassCleanup)
        cls.folder = Path(tempfile.mkdtemp(prefix="parameters-turn-")).resolve()
        cls.addClassCleanup(shutil.rmtree, cls.folder, True)
        cls.script = cls.folder / "bracket.py"
        cls.ident = model_id(cls.script, "bracket")
        cls.other = cls.folder / "other-python"  # another environment's Python: a worker of its own
        cls.other.mkdir()

    def setUp(self) -> None:
        self.script.write_text(GATED, encoding="utf-8")
        self.assertTrue(api.build_script(self.script, ["bracket"], progress=False).ok)  # the server's own worker

    def elsewhere(self, said: list, heard=lambda _message: None) -> threading.Thread:
        """A build of the script asked from another Python (as ``cad run``'s and ``python``'s are), so another
        worker of it builds: its answer appended to ``said``, each log line it is told to ``heard``."""
        from cad.engine.contract import CONTRACT, release

        order = {"op": "build", "script": str(self.script), "functions": ["bracket"], "cwd": str(self.folder),
                 "run": f"{os.getpid()}:{os.urandom(8).hex()}", "env": client.environment(),
                 "interpreter": {"executable": sys.executable, "prefix": str(self.other), "release": release(),
                                 "contract": dict(CONTRACT)}}
        thread = threading.Thread(target=lambda: said.append(client.request(order, heard)))
        thread.start()
        self.addCleanup(thread.join, 120)
        return thread

    def wall(self) -> float:
        rows = api.inspect(self.ident, query="structure", progress=False)["summary"]["parameters"]
        return next(row["value"] for row in rows if row["name"] == "wall")

    def test_a_save_while_another_worker_builds_the_script_is_refused_and_writes_nothing(self) -> None:
        gate = _Gate(self.folder)
        self.addCleanup(gate.release)
        said: list = []
        thread = self.elsewhere(said)
        gate.accept()  # the other worker is loading the script now
        before = self.script.read_bytes()
        with self.assertRaises(ParameterRefused) as caught:
            save(self.ident, wall=3.0)
        self.assertEqual(caught.exception.code, "busy", str(caught.exception))
        self.assertEqual(self.script.read_bytes(), before, "nothing written while the build reads the script")
        gate.release()
        thread.join(120)
        self.assertTrue(said and all(row["ok"] for row in said[0]["done"]), said)
        self.assertEqual(save(self.ident, wall=3.0)["written"][0]["to"], 3.0, "and set once it is done")

    def test_a_build_asked_while_a_save_builds_the_script_waits_for_it(self) -> None:
        gate = _Gate(self.folder)
        self.addCleanup(gate.release)
        answers: dict = {}
        saving = threading.Thread(target=lambda: answers.update(params=save(self.ident, wall=3.0)))
        saving.start()
        self.addCleanup(saving.join, 120)
        gate.accept()  # the save wrote the script, and its build is loading it
        self.assertIn(b'"wall", 3.0', self.script.read_bytes())
        logs: list = []
        waiting = threading.Event()

        def heard(message: dict) -> None:
            logs.append(message)
            if message.get("stream") == "waiting":
                waiting.set()

        said: list = []
        build = self.elsewhere(said, heard)
        self.assertTrue(waiting.wait(120), f"the build waits for the save, and says so: {logs}")
        self.assertIn("waiting for the parameters of bracket.py to be set", [message.get("log") for message in logs])
        self.assertEqual((answers, said), ({}, []), "neither has answered: the save's build is held, the build waits")
        gate.release()
        saving.join(120)
        build.join(120)
        self.assertEqual(answers["params"]["written"][0]["to"], 3.0)
        self.assertTrue(said and all(row["ok"] for row in said[0]["done"]), said)
        self.assertEqual(self.wall(), 3.0, "the build read the bytes the save wrote")


if __name__ == "__main__":
    unittest.main()
