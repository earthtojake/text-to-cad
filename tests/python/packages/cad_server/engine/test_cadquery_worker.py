"""The CadQuery worker's build and the daemon's side of it, with no CadQuery: the contract, the service and
the report.

``cad.cadquery._worker.build`` runs a script's ``@model`` functions and answers a kernel worker's reports with
a portable description in place of a document; the daemon routes an order whose contract names CadQuery's
kernel to the CadQuery worker service (``Daemon.service_of``) and accepts that kernel under its own protocol
(``contract.refusal``). The values are stand-ins with CadQuery's class names on build123d's shapes
(``tests/python/support/cadquery_like.py``); the real worker, through the daemon, is the ``cadquery`` job's.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support import cadquery_like
from tests.python.support.paths import add_sources

add_sources()

from cad.engine import contract, portable  # noqa: E402
from cad.engine.ids import model_id  # noqa: E402

SCRIPT = """
import cq_like
from cad import model, step


@model
def plate():
    return cq_like.plate()


@model
def bracket():
    found = cq_like.Assembly(name="bracket")
    found.add(plate().shape, name="plate")      # a child's value, composed here
    found.add(cq_like.peg(), loc=cq_like.at(10, 0, 8), name="peg")
    return found


@model
def nothing():
    return 42


@step("out.step")
def declared():
    return cq_like.plate()
"""


class TheWorkersBuild(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="cq-worker-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        shutil.copy(cadquery_like.__file__, self.folder / "cq_like.py")
        (self.folder / "models.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")

    def test_each_model_is_a_report_with_a_portable_description_the_engine_makes_a_document_of(self) -> None:
        import types

        from cad.cadquery import _memo, _worker

        # No CadQuery here: the memo is installed on an empty stand-in, so the build patches nothing and keys nothing.
        _memo.uninstall()
        _memo.install(types.ModuleType("stand_in"))
        self.addCleanup(_memo.uninstall)
        frames: list[dict] = []
        reports = _worker.build({"id": 1, "script": str(self.folder / "models.py"), "cwd": str(self.folder)}, frames.append)
        by_name = {report["model"]: report for report in reports}
        self.assertEqual(sorted(by_name), ["models.py::bracket", "models.py::declared", "models.py::nothing",
                                           "models.py::plate"])
        plate = by_name["models.py::plate"]
        self.assertTrue(plate["ok"], plate.get("error"))
        self.assertEqual((plate["id"], plate["kernel"], plate["bodies"]),
                         (model_id(self.folder / "models.py", "plate"), "cadquery", {f"{self.folder / 'models.py'}::plate": "run"}))
        self.assertEqual(set(plate["memo"]), {"hits", "misses", "unkeyable"})
        self.assertTrue(plate["closure"]["key"])
        self.assertEqual([path for path, _digest in plate["closure"]["modules"]], [str(self.folder / "cq_like.py")])
        self.assertEqual(plate["source"]["name"], "plate")
        self.assertIn("progress", plate)
        header = plate["portable"]["header"]
        self.assertEqual((header["format"], header["integration"], header["closure"]["key"]),
                         (portable.FORMAT, "cadquery", plate["closure"]["key"]))
        import base64

        made = portable.embody(header, base64.b64decode(plate["portable"]["bytes"]), "plate")
        self.assertEqual(made["parts"], 1)
        self.assertEqual([round(value) for value in made["facts"]["bounds"]], [40, 20, 6])
        from cad.engine import document, previous

        doc = document.read_bytes(made["xbf"])
        _writer, closure = previous.read_record(doc)
        self.assertIn('"cadquery"', closure, "the document's closure names CadQuery's build")
        self.assertIn(plate["closure"]["key"], closure)
        bracket = by_name["models.py::bracket"]
        self.assertTrue(bracket["ok"], bracket.get("error"))
        assembled = portable.embody(bracket["portable"]["header"], base64.b64decode(bracket["portable"]["bytes"]), "bracket")
        self.assertEqual(assembled["parts"], 2)
        self.assertEqual([round(value) for value in assembled["facts"]["bounds"]], [40, 20, 16])
        self.assertFalse(by_name["models.py::nothing"]["ok"])
        self.assertIn("returned int", by_name["models.py::nothing"]["error"])
        self.assertFalse(by_name["models.py::declared"]["ok"])
        self.assertIn("declared is declared by @step: a CadQuery model declares no file", by_name["models.py::declared"]["error"])
        self.assertTrue(any(frame.get("progress", {}).get("stage") == "body" for frame in frames))

    def test_the_contract_speaks_cadquery_s_kernel_and_the_daemon_routes_it_to_the_cadquery_worker(self) -> None:
        theirs = {**contract.CONTRACT, "kernel": contract.CADQUERY}
        self.assertIsNone(contract.refusal({"release": contract.release(), "contract": theirs}))
        self.assertIsNotNone(contract.refusal({"release": contract.release(), "contract": {**theirs, "kernel": "OCP 7.9"}}))
        self.assertIsNotNone(contract.refusal({"release": contract.release(), "contract": {**theirs, "protocol": -1}}))
        self.assertEqual(contract.kernel_here(), contract.CONTRACT["kernel"], "this environment is the kernel's")
        from cad_server.engine.daemon import Daemon
        from cad_server.engine.services import SERVICES

        self.assertEqual(Daemon.service_of({"interpreter": {"contract": theirs}}), "cadquery")
        self.assertEqual(Daemon.service_of({"interpreter": {"contract": contract.CONTRACT}}), "worker")
        self.assertEqual(Daemon.service_of({}), "worker")
        cadquery = next(service for service in SERVICES if service.name == "cadquery")
        self.assertEqual(cadquery.command[-1], "cad.cadquery._worker")
        self.assertEqual((cadquery.interpreter, cadquery.drain, cadquery.standby), ("lease", False, None))


if __name__ == "__main__":
    unittest.main()
