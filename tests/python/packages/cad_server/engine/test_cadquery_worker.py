"""The CadQuery worker's build and the daemon's side of it, with no CadQuery: the contract, the service, the
report, its closure, and the documents the daemon makes of its descriptions.

``cad.cadquery._worker.build`` runs a script's ``@model`` functions and answers a kernel worker's reports with
a portable description in place of a document; its closure keys the script, every module the body imported
(inside the body too) and every file it opened, by digest. The daemon routes an order whose contract names
CadQuery's kernel to the CadQuery worker service (``Daemon.service_of``), accepts that kernel under its own
protocol (``contract.refusal``), and makes each report's document through its documents worker
(``Models.embody``, ``register``), held whole and read the drained way (``Daemon.document``). The values are
stand-ins with CadQuery's class names on build123d's shapes (``tests/python/support/cadquery_like.py``), the
daemon an in-process one; the real worker, through a real daemon, is the ``cadquery`` job's.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
import textwrap
import types
import unittest
from unittest import mock
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

# A body that imports a helper inside itself and reads a data file: both are its closure's.
READING = """
import json
import pathlib

import cq_like
from cad import model


@model
def sized():
    import helper                                                   # imported inside the body
    params = json.loads(pathlib.Path(__file__).with_name("params.json").read_text(encoding="utf-8"))
    return cq_like.box(params["width"], 20, helper.THICKNESS)
"""

# A body that imports a module of an environment that lives under the project's folder (``cad run``'s cache,
# say): the environment's, not the script's own.
PACKAGED = """
import cq_like
from cad import model


@model
def sized():
    import libmod                                                   # the environment's module
    return cq_like.box(libmod.WIDTH, 20, 6)
"""

CLAIMING = """
import cq_like
from cad import model


@model(name="shared")
def {function}():
    return cq_like.plate()
"""


def _install_stand_in(case: unittest.TestCase) -> None:
    from cad.cadquery import _memo

    # No CadQuery here: the memo is installed on an empty stand-in, so a build patches nothing and keys nothing.
    _memo.uninstall()
    _memo.install(types.ModuleType("stand_in"))
    case.addCleanup(_memo.uninstall)


def _build(folder: Path, script: str, frames: list | None = None) -> list[dict]:
    from cad.cadquery import _worker

    sink = frames if frames is not None else []
    return _worker.build({"id": 1, "script": str(folder / script), "cwd": str(folder)}, sink.append)


class TheWorkersBuild(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="cq-worker-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        shutil.copy(cadquery_like.__file__, self.folder / "cq_like.py")
        (self.folder / "models.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        _install_stand_in(self)

    def test_each_model_is_a_report_with_a_portable_description_the_engine_makes_a_document_of(self) -> None:
        frames: list[dict] = []
        reports = _build(self.folder, "models.py", frames)
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
        self.assertEqual(plate["closure"]["inputs"], [], "the body opened no file of its own")
        self.assertEqual(plate["source"]["name"], "plate")
        self.assertIn("progress", plate)
        header = plate["portable"]["header"]
        self.assertEqual((header["format"], header["integration"], header["closure"]["key"]),
                         (portable.FORMAT, "cadquery", plate["closure"]["key"]))
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
        json.dumps(reports)  # what the daemon sends on to the client

    def test_the_closure_keys_what_the_body_imported_and_opened_and_moves_when_either_changes(self) -> None:
        (self.folder / "reading.py").write_text(textwrap.dedent(READING), encoding="utf-8")
        (self.folder / "helper.py").write_text("THICKNESS = 6\n", encoding="utf-8")
        (self.folder / "params.json").write_text('{"width": 40}\n', encoding="utf-8")
        [first] = _build(self.folder, "reading.py")
        self.assertTrue(first["ok"], first.get("error"))
        closure = first["closure"]
        self.assertEqual(sorted(path for path, _digest in closure["modules"]),
                         [str(self.folder / "cq_like.py"), str(self.folder / "helper.py")],
                         "the module imported inside the body is the closure's")
        self.assertEqual([(kind, path) for kind, path, _digest in closure["inputs"]],
                         [("file", str(self.folder / "params.json"))], "the file the body opened is its input")
        from cad.engine import document, previous

        header = first["portable"]["header"]
        _writer, text = previous.read_record(document.read_bytes(
            portable.embody(header, base64.b64decode(first["portable"]["bytes"]), "sized")["xbf"]))
        record = json.loads(text)
        self.assertIn(["file", "params.json", closure["inputs"][0][2]], record["inputs"], "the main label's record too")
        self.assertIn("helper.py", [path for path, _digest in record["modules"]])
        # The same code and inputs: the same key. An edited data file, or an edited helper: another key, each.
        [again] = _build(self.folder, "reading.py")
        self.assertEqual(again["closure"]["key"], closure["key"])
        (self.folder / "params.json").write_text('{"width": 50}\n', encoding="utf-8")
        [widened] = _build(self.folder, "reading.py")
        self.assertNotEqual(widened["closure"]["key"], closure["key"], "an edited input is another revision")
        made = portable.embody(widened["portable"]["header"], base64.b64decode(widened["portable"]["bytes"]), "sized")
        self.assertEqual([round(value) for value in made["facts"]["bounds"]], [50, 20, 6])
        (self.folder / "helper.py").write_text("THICKNESS = 8\n", encoding="utf-8")
        [thickened] = _build(self.folder, "reading.py")
        self.assertNotIn(thickened["closure"]["key"], (closure["key"], widened["closure"]["key"]),
                         "an edited module imported inside the body is another revision")

    def test_a_module_of_an_environment_under_the_project_is_the_library_s_and_is_never_forgotten(self) -> None:
        # The one-slot suite's shape: the cache folder, with the environment ``cad run`` made, inside the folder
        # of the script. Its modules are not the project's own: not the closure's, not forgotten before a load.
        site_packages = self.folder / "cache" / "base" / "env" / "lib" / "python3" / "site-packages"
        site_packages.mkdir(parents=True)
        (site_packages / "libmod.py").write_text("WIDTH = 40\n", encoding="utf-8")
        (self.folder / "packaged.py").write_text(textwrap.dedent(PACKAGED), encoding="utf-8")
        sys.path.insert(0, str(site_packages))
        self.addCleanup(sys.path.remove, str(site_packages))
        self.addCleanup(sys.modules.pop, "libmod", None)
        with mock.patch.object(sys, "prefix", str(site_packages.parents[2])):
            [first] = _build(self.folder, "packaged.py")
            self.assertTrue(first["ok"], first.get("error"))
            self.assertEqual([path for path, _digest in first["closure"]["modules"]], [str(self.folder / "cq_like.py")],
                             "the environment's module is not the project's own")
            loaded = sys.modules["libmod"]
            [again] = _build(self.folder, "packaged.py")
            self.assertTrue(again["ok"], again.get("error"))
            self.assertIs(sys.modules["libmod"], loaded, "a library module is never forgotten between loads")
            self.assertEqual(again["closure"]["key"], first["closure"]["key"])

    def test_the_contract_speaks_cadquery_s_kernel_and_the_daemon_routes_it_to_the_cadquery_worker(self) -> None:
        theirs = {**contract.CONTRACT, "kernel": contract.CADQUERY}
        self.assertIsNone(contract.refusal({"release": contract.release(), "contract": theirs}))
        self.assertIsNone(contract.refusal({"release": contract.release(), "contract": theirs}, ours=dict(contract.CONTRACT)),
                          "an equal copy of the server's contract speaks the same kernels")
        other = contract.refusal({"release": contract.release(), "contract": {**theirs, "kernel": "OCP 7.9"}})
        self.assertIsNotNone(other)
        self.assertIn("not OCP 7.9", other)
        self.assertIn("cadquery integration", other)
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

    def test_a_person_s_own_environment_with_cadquery_and_no_build123d_speaks_cadquery_s_kernel(self) -> None:
        import importlib.util
        from unittest import mock

        from cad.engine import places

        found = {"cadquery": object(), "build123d": None}
        with mock.patch.object(places, "INTEGRATIONS", ()), \
                mock.patch.object(importlib.util, "find_spec", lambda name, *rest: found.get(name)):
            self.assertEqual(contract.kernel_here(), contract.CADQUERY)
            found["build123d"] = object()
            self.assertEqual(contract.kernel_here(), contract.CONTRACT["kernel"], "both installed: the kernel's")
        with mock.patch.object(places, "INTEGRATIONS", ("cadquery",)):
            self.assertEqual(contract.kernel_here(), contract.CADQUERY, "an environment cad run made for cadquery")


def _fake_worker(key: str) -> types.SimpleNamespace:
    """The daemon's side of a CadQuery worker, as ``Models.register`` and ``Daemon.document`` read it."""
    return types.SimpleNamespace(service=types.SimpleNamespace(name="cadquery"), key=key, label=key, pid=4242,
                                 environment={}, python_key="cq", requests=1, progress=None, alive=lambda: True,
                                 retired=False, leased=False)


class TheDaemonEmbodiesTheReports(unittest.TestCase):
    """``Models.register`` on a CadQuery worker's reports through an in-process daemon: each description made a
    document by the documents worker (a cap of one slot: the CadQuery worker was let go first), held whole and
    cached under the model's id, read the drained way; a report the registry refuses stays a JSON answer."""

    def setUp(self) -> None:
        from cad_server.engine import daemon

        self.folder = Path(os.path.realpath(tempfile.mkdtemp(prefix="cq-daemon-")))
        self.addCleanup(shutil.rmtree, self.folder, True)
        shutil.copy(cadquery_like.__file__, self.folder / "cq_like.py")
        (self.folder / "models.py").write_text(textwrap.dedent(SCRIPT), encoding="utf-8")
        _install_stand_in(self)
        self.engine = daemon.Daemon(cap=1)
        self.addCleanup(self.engine.supervisor.stop)

    def test_each_description_is_a_document_the_daemon_holds_whole_and_serves_by_the_model_s_id(self) -> None:
        reports = _build(self.folder, "models.py")
        worker = _fake_worker(str(self.folder / "models.py"))
        self.engine.models.register(worker, {"done": reports, "program": str(self.folder / "models.py")})
        json.dumps(reports)  # nothing of what was made stays in a report
        by_name = {report["model"]: report for report in reports}
        bracket = by_name["models.py::bracket"]
        ident = model_id(self.folder / "models.py", "bracket")
        self.assertTrue(bracket["ok"], bracket.get("error"))
        self.assertNotIn("portable", bracket)
        self.assertEqual((bracket["parts"], [round(value) for value in bracket["delta"]["bounds"]["now"]]), (2, [40, 20, 16]))
        self.assertTrue(bracket["url"])
        record = self.engine.models.records[ident]
        self.assertEqual((record["kind"], record["worker"], record["revision"]), ("model", worker, bracket["closure"]["key"]))
        self.assertTrue(self.engine.server.has(ident, record["version"], whole=True), "held whole, as a shape handed over is")
        source, data = self.engine.document(ident)
        self.assertEqual(source, {"document": ident, "name": "bracket"}, "read the drained way, never from the worker")
        self.assertTrue(data.startswith(b"BINFILE"), "the document's bytes")
        self.assertIsNone(self.engine.provenance(ident, "k", "face", 1))
        self.engine.models.cache.final(10)
        self.assertTrue(self.engine.models.cache.current(ident, record["revision"]), "kept in the cache at once")
        for name in ("nothing", "declared"):
            self.assertFalse(by_name[f"models.py::{name}"]["ok"])
            self.assertNotIn(model_id(self.folder / "models.py", name), self.engine.models.records)

    def test_a_name_another_script_claims_is_refused_in_a_report_the_client_can_read(self) -> None:
        for function, script in (("first", "a.py"), ("second", "b.py")):
            (self.folder / script).write_text(textwrap.dedent(CLAIMING).format(function=function), encoding="utf-8")
        first = _build(self.folder, "a.py")
        self.engine.models.register(_fake_worker(str(self.folder / "a.py")), {"done": first})
        self.assertTrue(first[0]["ok"], first[0].get("error"))
        second = _build(self.folder, "b.py")
        self.engine.models.register(_fake_worker(str(self.folder / "b.py")), {"done": second})
        self.assertFalse(second[0]["ok"])
        self.assertIn("name 'shared' in namespace", second[0]["error"])
        json.dumps(second)  # the refusal reaches the client: no bytes left in the report


if __name__ == "__main__":
    unittest.main()
