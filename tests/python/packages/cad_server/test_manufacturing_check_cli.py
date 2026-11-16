"""``cad <type> dfm --process cnc|sheet|molding|printing``: a type's manufacturing check, as a command (a mesh's:
printing alone).

The measurements are the library's (``tests/python/packages/cad/test_trimesh_*.py``); this holds the
command: its options, its one result shape, its exit status (0 ok, 1 failed, 3 not checked, 2 the command
line's mistake), its refusals before anything is read, a STEP measured
on its exact geometry through the engine (with no engine and no kernel here, in the base's environment),
and the run in the environment of the trimesh integration when the command's own environment lacks it.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import trimesh

from cad_server._internal import integration_env
from cad_server.cli.document_types import pull_value, type_main
from tests.python.support import engine_daemon
from tests.python.support.paths import add_sources

SRC = add_sources()  # the three packages' sources, as PYTHONPATH names them

# A model whose pocket has sharp in-plane corners: no end mill cuts them.
POCKETED = """
import build123d as bd
from cad import model


@model
def plate():
    part = bd.Box(40, 30, 10) - bd.Pos(0, 0, 3) * bd.Box(20, 10, 4.01)
    part.label = "plate"
    return part


if __name__ == "__main__":
    print(plate().id)
"""


# The same plate, its material declared with its process: machined, so cnc is the check given no --process.
DECLARED = POCKETED.replace("    part.label = \"plate\"\n", """    from bd_materials import metals
    from bd_materials.processes import machined

    part.label, part.material = "plate", metals.aluminum(process=machined())
""")


def setUpModule() -> None:
    # An engine, a state and a cache folder of this file's own, run directly too: never the device's.
    engine_daemon.isolate(unittest.addModuleCleanup)


def _run(document_type: str, *argv: str) -> tuple[int, str, str]:
    """The command run: its exit status (a source its parser refuses exits, as argparse's errors do), stdout
    and stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = type_main(document_type, ["dfm", *argv])
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class ManufacturingCheckCommand(unittest.TestCase):
    def setUp(self) -> None:
        folder = tempfile.TemporaryDirectory(prefix="cad-check-cli-")
        self.addCleanup(folder.cleanup)
        self.folder = Path(folder.name)
        self.box = self.folder / "box.stl"
        trimesh.creation.box(extents=(20, 20, 15)).export(self.box)

    def test_a_mesh_refuses_molding_with_the_reason_and_the_fix(self) -> None:
        """Molding, CNC and sheet are judged on exact geometry: each mesh type refuses them before anything is read,
        the command line's mistake (exit 2, ``invalid_argument``), naming the check to run instead -- whatever else
        is given, that process's own flags (``--pull``, ``--axes``) included."""
        for document_type, name in (("stl", "box.stl"), ("threemf", "box.3mf"), ("glb", "box.glb")):
            with self.subTest(document_type=document_type):
                path = self.folder / name
                if not path.exists():
                    path.write_bytes(b"")
                code, out, _ = _run(document_type, str(path), "--process", "molding", "--json")
                found = json.loads(out)
                self.assertEqual((code, found["ok"], found["reason"], found["status"]),
                                 (2, False, "invalid_argument", "usage"))
                self.assertIn("a molding check is judged on exact geometry", found["error"])
                self.assertIn("check the part's STEP or model instead (cad step dfm part.step --process molding",
                              found["error"])
        for argv, words in (
                (("--process", "molding", "--pull", "z"), "a molding check is judged on exact geometry"),
                (("--pull", "-z", "--process=molding", "--candidates"), "a molding check is judged on exact geometry"),
                (("--axes", "5", "--process", "cnc"), "a cnc check measures exact geometry"),
                (("--process", "sheet", "--thickness", "2", "--k-factor", "0.4"), "a sheet check measures exact geometry")):
            with self.subTest(argv=argv):
                code, out, _ = _run("stl", str(self.box), *argv, "--json")
                found = json.loads(out)
                self.assertEqual((code, found["reason"]), (2, "invalid_argument"))
                self.assertIn(words, found["error"])
                self.assertIn("check the part's STEP or model instead", found["error"])
        code, _out, err = _run("stl", str(self.box), "--process", "cnc", "--axes", "5")
        self.assertEqual(code, 2)
        self.assertIn("a cnc check measures exact geometry", err)
        self.assertNotIn("unrecognized arguments", err)
        self.assertEqual(pull_value(["p.step", "--pull", "-z"]), ["p.step", "--pull=-z"])

    def test_a_part_that_fails_its_rules_exits_one_with_its_json_line(self) -> None:
        """A box missing two triangles is open: nothing prints it, an error (exit 1)."""
        opened = self.folder / "open.stl"
        box = trimesh.creation.box(extents=(20, 20, 15))
        trimesh.Trimesh(box.vertices, box.faces[:-2], process=False).export(opened)
        code, out, _ = _run("stl", str(opened), "--process", "printing", "--json")
        payload = json.loads(out)
        self.assertEqual((code, payload["ok"], payload["status"], payload["reason"]), (1, False, "failed", None), out)
        self.assertEqual(sorted(payload), ["findings", "measurements", "ok", "path", "reason", "status", "summary"])
        self.assertIn("not_watertight", [f["code"] for f in payload["findings"] if f["severity"] == "error"])
        self.assertEqual(sorted(payload["findings"][0]),
                         ["code", "hint", "items", "limit", "location", "message", "op", "refs", "rule", "severity",
                          "source", "unit", "value"])

    def test_a_check_that_judged_nothing_is_not_checked_and_exits_three(self) -> None:
        """Exit 1 says the part fails. A source the check could not measure -- a STEP of a face, a mesh of no
        triangle, whose every family fails to measure -- fails no rule: it is not checked, exit 3, its reason
        the code of the finding that says so, with ``--json`` and without."""
        from build123d import Rectangle, export_step

        face = self.folder / "face.step"
        export_step(Rectangle(10, 10).face(), str(face))
        broken = self.folder / "broken.stl"
        broken.write_bytes(b"solid nothing\nfacet nonsense\n")
        for document_type, path, reasons in (("step", face, {"not_solid"}),
                                             ("stl", broken, {"mesh_empty"})):
            with self.subTest(document_type=document_type):
                code, out, _ = _run(document_type, str(path), "--process", "printing", "--json")
                payload = json.loads(out)
                self.assertEqual((code, payload["ok"], payload["status"]), (3, False, "not_checked"), out)
                reason = payload["reason"]
                self.assertIn(reason, reasons)
                self.assertEqual(payload["findings"][0]["code"], reason)
                code, out, _ = _run(document_type, str(path), "--process", "printing")
                self.assertEqual(code, 3)
                self.assertRegex(out.splitlines()[-1], rf"^NOT CHECKED .*{path.name}: {reason}\b")

    def test_a_check_the_engine_did_not_finish_is_not_checked_with_its_reason(self) -> None:
        """An engine that cancelled the check, lost its worker or stopped measured nothing: exit 3, never the 1
        that says the part fails; ``--json`` is the failure's document with the engine's own reason where its
        error carries one, and a document the engine does not hold stays the command line's mistake."""
        from build123d import Box, export_step

        from cad.engine import api, serve

        step = self.folder / "box.step"
        export_step(Box(20, 20, 15), str(step))
        cancelled = api.EngineError("the check was cancelled: its script is being built")
        cancelled.reason = "cancelled"  # type: ignore[attr-defined]
        for error, reason in ((cancelled, "cancelled"), (api.Stopped(api.STOPPED), "engine_stopped"),
                              (api.EngineError("the checks process died"), "engine_failed")):
            with self.subTest(reason=reason), mock.patch.object(api, "check", side_effect=error):
                reason = getattr(error, "reason", None) or reason  # a release whose errors carry their own
                code, out, _ = _run("step", str(step), "--process", "printing", "--json")
                payload = json.loads(out)
                self.assertEqual((code, payload["ok"], payload["status"], payload["reason"]),
                                 (3, False, "not_checked", reason), out)
                self.assertEqual(payload["error"], str(error))
                code, out, err = _run("step", str(step), "--process", "printing")
                self.assertEqual((code, out.splitlines()[-1]), (3, f"NOT CHECKED {step}: {reason}"))
                # one line, which says the state and the reason: no part failed, and no frame is the reader's
                self.assertEqual(err.splitlines(), [f"cad step dfm: NOT CHECKED ({reason}): {error}"])
        with mock.patch.object(api, "check", side_effect=TypeError("a bug in the check")):
            code, out, err = _run("step", str(step), "--process", "printing")
        self.assertEqual((code, out.splitlines()[-1]), (3, f"NOT CHECKED {step}: failed"))
        self.assertEqual(err.splitlines(), ["cad step dfm: NOT CHECKED (failed): TypeError: a bug in the check"])
        with mock.patch.object(api, "check", side_effect=serve.NotHeld("no document is held")):
            code, out, _ = _run("model", "01234567-89ab-5def-8123-456789abcdef", "--process", "printing", "--json")
        self.assertEqual((code, json.loads(out)["reason"], json.loads(out)["status"]), (2, "not_found", "usage"))

    def test_a_check_measured_here_past_a_check_s_limit_is_stopped_and_not_checked(self) -> None:
        """A mesh's check is measured by the command, in a process it holds to the engine's limits for a check:
        past one it is stopped, exit 3 with the limit's reason, never left to run on."""
        import os

        from cad._internal import manufacturing

        with mock.patch.object(manufacturing, "WATCH_SECONDS", 0.01), \
                mock.patch.dict(os.environ, {"CAD_ENGINE_CHECK_SECONDS": "1e-9"}):
            code, out, _ = _run("stl", str(self.box), "--process", "printing")
            # the path as the command names it, resolved (a temporary folder is a link on macOS)
            self.assertEqual((code, out.splitlines()[-1]), (3, f"NOT CHECKED {self.box.resolve().as_posix()}: over_time"))
            code, out, _ = _run("stl", str(self.box), "--process", "printing", "--json")
        payload = json.loads(out)
        self.assertEqual((code, payload["status"], payload["reason"]), (3, "not_checked", "over_time"))
        self.assertIn("CAD_ENGINE_CHECK_SECONDS", payload["findings"][0]["message"])

    def test_strict_fails_on_a_warning(self) -> None:
        from build123d import Box, export_step

        step = self.folder / "block.step"
        export_step(Box(40, 30, 15), str(step))
        argv = (str(step), "--process", "printing", "--technology", "pbf")
        code, out, _ = _run("step", *argv)
        self.assertEqual(code, 0)
        self.assertRegex(out.splitlines()[-1], r"^OK .*block\.step: 1 warning\(s\); printing pbf: ")
        code, out, _ = _run("step", *argv, "--strict", "--json")
        payload = json.loads(out)
        self.assertEqual((code, payload["status"]), (1, "failed"))
        self.assertIn("(--strict: a warning fails)", payload["summary"])

    def test_printing_says_its_findings_then_its_summary(self) -> None:
        code, out, _ = _run("stl", str(self.box), "--process", "printing", "--angle-limit", "30")
        self.assertEqual(code, 0)
        self.assertRegex(out.splitlines()[-1], r"^OK .*box\.stl: printing fdm: 6000 mm3, 1 body\(ies\); overhangs under 30 deg")

    def test_a_mistake_is_refused_before_anything_is_read(self) -> None:
        """An option's value it refuses is the command line's mistake, exit 2, named by its flag: a choice
        its parser does not take (``usage``), or a value the check refuses (``invalid_argument``)."""
        for argv, words, reason in (
                ((str(self.box), "--process", "casting"), "argument --process: invalid choice: 'casting'", "usage"),
                ((str(self.box), "--process", "cnc"), "a cnc check measures exact geometry", "invalid_argument"),
                ((str(self.box), "--process", "printing", "--pull", "z"), "unrecognized arguments: --pull", "usage"),
                ((str(self.box), "--process", "printing", "--samples", "0"), "--samples is a count of at least 1",
                 "invalid_argument"),
                ((str(self.box), "--process", "printing", "--units", "yd"), "argument --units: invalid choice: 'yd'",
                 "usage")):
            with self.subTest(argv=argv):
                code, out, _ = _run("stl", *argv, "--json")
                found = json.loads(out)
                # a result says its state in ``status``, and so does the command line's mistake: one field
                self.assertEqual((code, found["ok"], found["reason"], found["status"]), (2, False, reason, "usage"))
                self.assertIn(words, found["error"])
        # units are an STL's alone: a type that declares its own takes no such flag
        (self.folder / "box.3mf").write_bytes(b"")
        code, out, _ = _run("threemf", str(self.folder / "box.3mf"), "--process", "printing", "--units", "cm", "--json")
        self.assertEqual((code, json.loads(out)["reason"]), (2, "usage"))
        self.assertIn("unrecognized arguments: --units cm", json.loads(out)["error"])
        # a value no machine has is refused before anything is read, and a material is taken by its name
        code, out, _ = _run("stl", str(self.box), "--process", "printing", "--layer-height", "5", "--json")
        self.assertEqual((code, json.loads(out)["reason"]), (2, "invalid_argument"))
        self.assertIn("--layer-height 5 mm is taller than the 0.4 mm nozzle", json.loads(out)["error"])
        code, out, _ = _run("stl", str(self.box), "--process", "printing", "--material", "PLA filament", "--json")
        self.assertEqual((code, json.loads(out)["measurements"]["rules"]["context"]["material"]), (0, "pla"), out)
        code, _, err = _run("stl", str(self.folder / "box.glb"), "--process", "printing")
        self.assertEqual(code, 2)
        self.assertIn("box.glb is a glb, not a stl: use cad glb dfm", err)

    def test_a_usage_error_is_argparses_two(self) -> None:
        """Exit 1 is a part that fails and exit 3 a check that judged nothing; a misspelled flag never reads as
        either, nor does a file that is not there."""
        code, _out, err = _run("stl", str(self.box), "--process", "printing", "--not-a-flag")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments: --not-a-flag", err)
        # the checks are general: no flag picks a shop's rules
        code, _out, err = _run("stl", str(self.box), "--process", "printing", "--rules", "generic")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments: --rules generic", err)
        code, out, _ = _run("stl", str(self.folder / "missing.stl"), "--process", "printing", "--json")
        self.assertEqual((code, json.loads(out)["reason"], json.loads(out)["status"]), (2, "not_found", "usage"))

    def test_a_step_is_measured_on_its_exact_geometry(self) -> None:
        from build123d import Box, export_step

        step = self.folder / "box.step"
        export_step(Box(20, 20, 15), str(step))
        code, out, _ = _run("step", str(step), "--process", "printing", "--json")
        payload = json.loads(out)
        self.assertEqual(code, 0, out)
        self.assertAlmostEqual(payload["measurements"]["solid"]["volume_mm3"], 6000.0, delta=1e-6)
        self.assertEqual(payload["measurements"]["source"]["measured_as"], "brep")
        self.assertEqual(payload["path"], str(step.resolve()))

    def test_without_trimesh_here_it_runs_in_the_integrations_environment(self) -> None:
        """The command's environment lacks the integration: the check runs in the one that holds it (this
        interpreter stands in for it), answering exactly as it does here, a refusal before one is made."""
        from build123d import Box, export_step

        step = self.folder / "box.step"
        export_step(Box(20, 20, 15), str(step))
        argv = (str(self.box), "--process", "printing", "--candidates", "--json")
        _code, here, _ = _run("stl", *argv)
        with mock.patch.object(integration_env, "carries", return_value=False), \
                mock.patch.object(integration_env, "environment", return_value=sys.executable) as made:
            code, there, _ = _run("stl", *argv)
            refused, said, _ = _run("stl", str(self.box), "--process", "printing", "--samples", "0", "--json")
            # a STEP keeps no process: refused here, not after the file is read there
            unasked, kept, _ = _run("step", str(step), "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(there), json.loads(here))
        self.assertEqual((refused, made.call_count), (2, 1), "a refusal makes no environment")
        self.assertIn("--samples is a count of at least 1", json.loads(said)["error"])
        self.assertEqual((unasked, json.loads(kept)["reason"]), (2, "invalid_argument"))
        self.assertIn("a STEP keeps no process: give --process cnc", json.loads(kept)["error"])

    def test_a_breps_check_is_the_engines_and_with_no_engine_the_bases(self) -> None:
        """A B-rep's check is asked of the engine from this process, whatever it holds. With no engine to reach
        (a sandbox) and no kernel here, it runs in the base's environment, as it did (this interpreter stands
        in for it), and answers the same."""
        from build123d import Box, export_step

        step = self.folder / "box.step"
        export_step(Box(20, 20, 15), str(step))
        argv = (str(step), "--process", "printing", "--json")
        with mock.patch.object(integration_env, "carries", return_value=False), \
                mock.patch.object(integration_env, "environment", return_value=sys.executable) as made:
            code, asked, _ = _run("step", *argv)
            self.assertEqual((code, made.call_count), (0, 0), "the engine measured it: no environment started")
            with mock.patch("cad.engine.client.connect", side_effect=ConnectionError("no engine here")):
                code, there, _ = _run("step", *argv)
            self.assertEqual((code, made.call_count), (0, 1))
        self.assertEqual(json.loads(there), json.loads(asked))

    def test_a_command_with_no_kernel_sends_another_releases_check_elsewhere_never_here(self) -> None:
        """The engine measured nothing (another release's): a command with no kernel neither measures here nor
        exports here, for a file and for a model's id alike. The base's environment answers."""
        from build123d import Box, export_step

        from cad._internal import manufacturing
        from cad.engine import api

        step = self.folder / "box.step"
        export_step(Box(20, 20, 15), str(step))
        ident = "01234567-89ab-5def-8123-456789abcdef"
        answered = {"process": "x"}
        for argv, document_type in (((str(step),), "step"), ((ident,), "model")):
            with self.subTest(document_type), \
                    mock.patch.object(integration_env, "carries", return_value=False), \
                    mock.patch.object(integration_env, "environment", return_value=sys.executable), \
                    mock.patch.object(integration_env, "call", return_value={
                        "ok": True, "path": str(argv[0]), "findings": [], "summary": "there",
                        "measurements": answered}) as there, \
                    mock.patch.object(api, "check", side_effect=api.Unanswered("another release")), \
                    mock.patch.object(manufacturing, "_here", side_effect=AssertionError("measured here")), \
                    mock.patch.object(manufacturing, "_exported", side_effect=AssertionError("exported here")):
                code, out, _ = _run(document_type, *argv, "--process", "printing", "--json")
                self.assertEqual((code, json.loads(out)["summary"], there.call_count), (0, "there", 1), out)

    def test_each_type_offers_its_processes_and_their_flags(self) -> None:
        from cad_server.cli.document_types import build_parser

        def flags(document_type: str) -> dict:
            return {action.dest: action for action in build_parser(document_type, "dfm")._actions}  # noqa: SLF001

        stl, dxf = flags("stl"), flags("dxf")
        # a mesh is checked for printing alone (the default); the rest are refused with the reason and the fix
        self.assertEqual((list(stl["process"].choices), stl["process"].default, "axes" in stl, "pull" in stl),
                         (["cnc", "sheet", "molding", "printing"], "printing", False, False))
        self.assertEqual((list(dxf["process"].choices), dxf["process"].default, "pull" in dxf), (["sheet"], "sheet", False))
        code, _, err = _run("stl", str(self.box), "--process", "cnc")
        self.assertEqual(code, 2)
        self.assertIn("a cnc check measures exact geometry", err)

    def test_exact_geometry_runs_in_the_base_and_a_mesh_in_trimeshs(self) -> None:
        """A STEP's check is build123d's, whose environment is the base the engine's kernel runs in: no second
        environment of the kernel is made for it; a mesh's is trimesh's own."""
        from cad.registry import DOCUMENT_TYPES
        from cad_server._internal import base, extras

        self.assertEqual({kind: DOCUMENT_TYPES[kind].operation("dfm").integration for kind in ("step", "stl")},
                         {"step": "build123d", "stl": "trimesh"})
        found = base.Environment(sys.executable, sys.prefix, True)
        with mock.patch.object(base, "ensure", return_value=found) as kernel, \
                mock.patch.object(extras, "ensure", return_value=found) as other:
            integration_env.environment("build123d", print)
            self.assertEqual((kernel.call_count, other.call_count), (1, 0))
            integration_env.environment("trimesh", print)
            self.assertEqual((kernel.call_count, other.call_count), (1, 1))


class ModelTest(unittest.TestCase):
    """A model's document, checked by its id as a check script does: built by the engine (the runner's, this
    file's own), read back through it, every finding at a ref the engine's inspect resolves to the face."""

    def test_a_model_is_checked_by_its_id_and_its_refs_resolve(self) -> None:
        import os

        import cad

        with tempfile.TemporaryDirectory(prefix="cad-dfm-model-") as folder:
            script = Path(folder) / "plate.py"
            script.write_text(POCKETED, encoding="utf-8")
            built = engine_daemon.run([sys.executable, str(script)], cwd=folder,
                                      env={**os.environ, "PYTHONPATH": str(SRC)})
            self.assertEqual(built.returncode, 0, built.stderr)
            ident = built.stdout.strip().splitlines()[-1]
            result = cad.model.dfm(ident, process="cnc", material="aluminum")
            sharp = [f for f in result.findings if f.code == "cnc.internal_corner_sharp"]
            self.assertTrue(sharp, [f.code for f in result.findings])
            self.assertFalse(result.ok)
            # a corner is its edge: the finding is at it, its faces beside it, each a ref inspect resolves
            self.assertRegex(sharp[0].location, r"plate/edge \d+$")
            self.assertEqual(cad.model.inspect(ident, sharp[0].location)["kind"], "edge")
            self.assertEqual([cad.model.inspect(ident, ref)["kind"] for ref in sharp[0].refs[1:3]], ["face", "face"])
            code, out, _ = _run("model", ident, "--process", "cnc", "--json")
            self.assertEqual(code, 1)
            self.assertIn("cnc.internal_corner_sharp", {f["code"] for f in json.loads(out)["findings"]})
            refused, said, _ = _run("xbf", ident, "--process", "cnc", "--json")
            self.assertEqual((refused, json.loads(said)["reason"]), (2, "wrong_type"))
            self.assertIn("use cad model dfm", json.loads(said)["error"])

    def test_a_model_given_no_process_is_checked_for_the_one_its_part_declares(self) -> None:
        """Reads the part's declared process back from the engine's document (the material's process survives
        the xbf: ``cad.engine.document``). What the integration refuses once it has read the document -- an
        option of another process -- and an id the engine does not hold are the command line's mistakes, exit 2,
        here and through the integration's environment alike."""
        import os

        with tempfile.TemporaryDirectory(prefix="cad-dfm-declared-") as folder:
            script = Path(folder) / "plate.py"
            script.write_text(DECLARED, encoding="utf-8")
            built = engine_daemon.run([sys.executable, str(script)], cwd=folder,
                                      env={**os.environ, "PYTHONPATH": str(SRC)})
            self.assertEqual(built.returncode, 0, built.stderr)
            ident = built.stdout.strip().splitlines()[-1]
            code, out, _ = _run("model", ident, "--json")
            payload = json.loads(out)
            self.assertNotIn("error", payload)
            self.assertEqual((code, payload["measurements"]["process"]), (1, "cnc"))
            codes = {f["code"] for f in payload["findings"]}
            self.assertTrue({"process_declared", "material_declared", "cnc.internal_corner_sharp"} <= codes, codes)
            unheld = "01234567-89ab-cdef-0123-456789abcdef"
            cases = (((ident, "--pull", "z"), "invalid_argument", "--pull is not cnc's"),
                     ((unheld, "--process", "cnc"), "not_found", f"no document {unheld} is held"))
            answers = {"here": [_run("model", *argv, "--json") for argv, _, _ in cases]}
            with mock.patch.object(integration_env, "carries", return_value=False), \
                    mock.patch.object(integration_env, "environment", return_value=sys.executable):
                answers["there"] = [_run("model", *argv, "--json") for argv, _, _ in cases]
            for where, answered in answers.items():
                for (argv, reason, words), (code, out, _) in zip(cases, answered, strict=True):
                    with self.subTest(where=where, argv=argv):
                        self.assertEqual((code, json.loads(out)["reason"]), (2, reason))
                        self.assertIn(words, json.loads(out)["error"])


if __name__ == "__main__":
    unittest.main()
