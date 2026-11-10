"""Shared fixtures for the manufacturing checks suite (``tests/python/packages/cad_server/engine/
test_manufacturing_checks_*.py``): the models its tests build, the check as it was measured before the
engine measured it (``_today``), a check run in a thread (``Checking``), and the seam an engine's
checks wait at (``held_engine``). Each test file isolates itself (``engine_daemon.isolate``): what
these reach through ``cad.engine.api`` is that file's engine.

Importing this puts the packages' sources on ``sys.path``."""

from __future__ import annotations

import dataclasses
import json
import os
import shutil
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from pathlib import Path
from typing import Any

from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

# Two models: a plate with a pocket, and an assembly of a thin sheet and one boss placed twice, once
# turned -- a part with two occurrences, placed off the identity.
MODELS = """
import build123d as bd
from cad import model


@model
def plate():
    part = bd.Box(40, 30, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 4.01)
    part.label = "plate"
    return part


@model
def pair():
    sheet = bd.Box(60, 40, 2) - bd.Pos(10, 0, 0) * bd.Cylinder(3, 2)
    sheet.label = "sheet"
    boss = bd.Cylinder(6, 14) - bd.Cylinder(2.5, 14)
    first = bd.Pos(-15, 0, 8) * boss
    second = bd.Rot(0, 0, 30) * bd.Pos(20, 12, 8) * boss
    first.label, second.label = "boss_a", "boss_b"
    return bd.Compound(children=[sheet, first, second], label="pair")


if __name__ == "__main__":
    print(plate().id)
    print(pair().id)
"""

# A part whose material declares its process (machined aluminum): checked for cnc given none, its material
# read from the engine's document (``material_from_json``) as from the file (the XCAF label's).
DECLARED = """
import build123d as bd
from bd_materials import metals
from bd_materials.processes import machined
from cad import model


@model
def block():
    part = bd.Box(30, 20, 12) - bd.Pos(0, 0, 4) * bd.Box(12, 8, 4.01)
    part.label, part.material = "block", metals.aluminum(process=machined())
    return part


if __name__ == "__main__":
    print(block().id)
"""

JOIN_SECONDS = 120.0


def _plain(result: Any) -> Any:
    """A result as its ``--json`` says it: tuples and lists alike."""
    return json.loads(json.dumps(dataclasses.asdict(result), default=str))


# What measures in a process (``contract.measuring``), as a test's callers and its checks processes say it.
MEASURES = {"code": "c0de", "libraries": {"build123d": "0.13.0", "OCP": "8.0.1", "numpy": "2.0.0"}}


def _counts() -> dict[str, int]:
    from cad.engine import api

    return api.status()["checks"]


def _until(case: unittest.TestCase, condition: Any, what: str) -> None:
    """``condition()`` awaited: a test that waits too long fails saying for what."""
    deadline = time.monotonic() + JOIN_SECONDS
    while not condition():
        case.assertLess(time.monotonic(), deadline, f"never: {what}")
        time.sleep(0.02)


# A test's seam, in the checks processes of an engine started with it (``held_engine``): a ``sitecustomize``
# first on ``PYTHONPATH`` that makes each check say it is measuring (``<hold>.reached``, holding the pid of its
# process) and wait until the file ``CAD_TEST_CHECK_HOLD`` names is there, so a test can build, inspect, kill or
# stop while a check measures. Nothing of it is in the library. The suite's own ``sitecustomize`` (the
# journal's, which this one would hide) runs after it.
SEAM = """
import os
import sys


def _seam():
    hold = os.environ.get("CAD_TEST_CHECK_HOLD")
    if not hold or "cad.engine.worker" not in " ".join(getattr(sys, "orig_argv", sys.argv)):
        return
    import time

    import cad.registry as registry

    integration = registry.manufacturing_check

    class Held:
        def __getattr__(self, name):
            return getattr(integration(), name)

        def held(self, *args, **kwargs):
            with open(hold + ".reached", "w", encoding="utf-8") as handle:
                handle.write(str(os.getpid()))
            deadline = time.monotonic() + SECONDS
            while not os.path.exists(hold) and time.monotonic() < deadline:
                time.sleep(0.01)
            return integration().held(*args, **kwargs)

    registry.manufacturing_check = Held


_seam()
if os.path.isfile(JOURNAL):
    with open(JOURNAL, encoding="utf-8") as _source:
        exec(compile(_source.read(), JOURNAL, "exec"))
"""


def held_engine(case: unittest.TestCase, env: dict[str, str] | None = None) -> tuple[dict[str, str], Path]:
    """An engine of the test's own whose checks wait at the seam (``SEAM``), started in ``env`` beside it: the
    environment it was started in, which a command of the test's runs in, and the file a check waits for.
    Stopped at the test's end, any check still waiting let go first."""
    from cad.engine import api

    api.stop()
    case.addCleanup(api.stop)
    folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-seam-")))
    case.addCleanup(shutil.rmtree, folder, True)
    hold = folder / "go"
    case.addCleanup(lambda: hold.write_text("", encoding="utf-8"))  # whatever happens, no check waits on
    (folder / "site").mkdir()
    (folder / "site" / "sitecustomize.py").write_text(
        f"SECONDS = {JOIN_SECONDS}\nJOURNAL = {str(engine_daemon.SITE / 'sitecustomize.py')!r}\n{SEAM}", encoding="utf-8")
    found = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), "CAD_TEST_CHECK_HOLD": str(hold),
                                   **(env or {})}, case.addCleanup)
    found["PYTHONPATH"] = os.pathsep.join((str(folder / "site"), found["PYTHONPATH"]))
    started = engine_daemon.run([sys.executable, "-c", "from cad.engine import client; client.connect()"], env=found)
    case.assertEqual(started.returncode, 0, started.stderr)
    return found, hold


def held_check(case: unittest.TestCase, hold: Path, check: Any) -> tuple["Checking", int]:
    """``check`` running in a thread, once its checks process says it is measuring: the thread, and that
    process's pid."""
    reached = Path(f"{hold}.reached")
    reached.unlink(missing_ok=True)
    thread = Checking(check)
    thread.start()
    _until(case, lambda: (reached.exists() and reached.read_text(encoding="utf-8")) or not thread.is_alive(),
           "the check reached its seam")
    case.assertTrue(thread.is_alive(), thread.answered)
    return thread, int(reached.read_text(encoding="utf-8"))


def box(case: unittest.TestCase, *heights: float) -> list[Path]:
    """A STEP of a box of each height, in a folder of the test's own."""
    import build123d as bd

    folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-box-")))
    case.addCleanup(shutil.rmtree, folder, True)
    steps = [folder / f"part{index}.step" for index in range(len(heights))]
    for height, step in zip(heights, steps):
        bd.export_step(bd.Box(30, 20, height), str(step))
    return steps


class Fixture:
    """A script of ``text`` in a folder of its own, built through the engine; its models' ids."""

    def __init__(self, case: unittest.TestCase, text: str, env: dict[str, str] | None = None) -> None:
        self.case = case
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="engine-dfm-")))
        case.addCleanup(shutil.rmtree, self.folder, True)
        self.script = self.folder / "parts.py"
        self.env = engine_daemon.watched({**os.environ, "PYTHONPATH": str(SRC), **(env or {})}, case.addCleanup)
        self.ids = self.build(text)

    def build(self, text: str | None = None) -> list[str]:
        if text is not None:
            self.script.write_text(textwrap.dedent(text), encoding="utf-8")
        built = engine_daemon.run([sys.executable, str(self.script)], cwd=self.folder, env=self.env)
        self.case.assertEqual(built.returncode, 0, built.stderr)
        self.said = built.stderr
        ids = [word for word in built.stdout.split() if len(word) == 36 and word.count("-") == 4]
        return list(dict.fromkeys(ids))  # each model once, as its run printed it (its id: line and the script's)


def _today(document_type: str, source: Any, label: Path, process: str | None, candidates: bool = False,
           **given: Any) -> Any:
    """The check as it was before the engine measured it: the document read from its file in this process
    (a model's exported to an xbf first), then measured and finished here."""
    from cad._internal import manufacturing
    from cad.build123d import _dfm_check

    resolved = manufacturing.options(document_type, process, given, candidates=candidates)
    if process is None:
        process, resolved, report = _dfm_check.measure_declared(document_type, source, given, candidates)
    else:
        report = _dfm_check.measure(document_type, source, process, resolved, candidates)
    return manufacturing.finish(label, {"process": process, **report}, process, resolved, candidates)


class Checking(threading.Thread):
    """A check run in a thread: what it answered, or raised."""

    def __init__(self, check: Any) -> None:
        super().__init__(daemon=True)
        self.check, self.answered = check, None

    def run(self) -> None:
        try:
            self.answered = self.check()
        except Exception as error:  # noqa: BLE001 - what the check raised is the test's to read
            self.answered = error

    def result(self, case: unittest.TestCase) -> Any:
        self.join(JOIN_SECONDS)
        case.assertFalse(self.is_alive(), f"the check did not answer within {JOIN_SECONDS:.0f} s")
        return self.answered
