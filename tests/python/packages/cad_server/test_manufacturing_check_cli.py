"""``cad <type> dfm --process cnc|sheet|molding|printing``: a type's manufacturing check, as a command.

The measurements are the library's (``tests/python/packages/cad/test_trimesh_*.py``); this holds the
command: its options, its one result shape, its refusals before anything is read, a STEP measured
on its exact geometry, and the run in the environment of the trimesh integration when the
command's own environment lacks it.
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

    def test_molding_answers_one_json_line_with_its_measurements(self) -> None:
        code, out, _ = _run("stl", str(self.box), "--process", "molding", "--pull", "-z", "--json")
        payload = json.loads(out)
        # A plain box has no draft: the generic rules fail it (exit 1) and say where.
        self.assertEqual(code, 1)
        self.assertEqual(sorted(payload), ["findings", "measurements", "ok", "path", "summary"])
        self.assertFalse(payload["ok"])
        self.assertIn("molding.draft_min", [f["code"] for f in payload["findings"] if f["severity"] == "error"])
        self.assertEqual(payload["measurements"]["draft"]["pull_axis"], [0.0, 0.0, -1.0], "--pull -z reached argparse")
        finding = next(f for f in payload["findings"] if f["code"] == "zero_draft_walls")
        self.assertEqual((finding["severity"], len(finding["location"].split(", "))), ("warning", 3))
        self.assertEqual(pull_value(["p.stl", "--pull", "-z"]), ["p.stl", "--pull=-z"])

    def test_printing_says_its_findings_then_its_summary(self) -> None:
        code, out, _ = _run("stl", str(self.box), "--process", "printing", "--angle-limit", "30")
        self.assertEqual(code, 0)
        self.assertRegex(out.splitlines()[-1], r"^OK .*box\.stl: printing fdm: 6000 mm3, 1 body\(ies\); overhangs under 30 deg")

    def test_a_mistake_is_refused_before_anything_is_read(self) -> None:
        """An option's value it refuses is the command line's mistake, exit 2, named by its flag: a choice
        its parser does not take (``usage``), or a value the check refuses (``invalid_argument``)."""
        for argv, words, reason in (
                ((str(self.box),), "give --process cnc, sheet, molding or printing", "invalid_argument"),
                ((str(self.box), "--process", "casting"), "argument --process: invalid choice: 'casting'", "usage"),
                ((str(self.box), "--process", "molding", "--samples", "9"), "--samples is not molding's",
                 "invalid_argument"),
                ((str(self.box), "--process", "printing", "--pull", "z"), "--pull is not printing's", "invalid_argument"),
                ((str(self.box), "--process", "molding", "--candidates", "--pull", "x"), "ranks every pull",
                 "invalid_argument"),
                ((str(self.box), "--process", "molding", "--pull", "up"), "--pull is an axis", "invalid_argument"),
                ((str(self.box), "--process", "printing", "--samples", "0"), "--samples is a count of at least 1",
                 "invalid_argument"),
                ((str(self.box), "--process", "printing", "--units", "yd"), "argument --units: invalid choice: 'yd'",
                 "usage")):
            with self.subTest(argv=argv):
                code, out, _ = _run("stl", *argv, "--json")
                found = json.loads(out)
                self.assertEqual((code, found["ok"], found["reason"]), (2, False, reason))
                self.assertIn(words, found["error"])
        (self.folder / "box.3mf").write_bytes(b"")
        code, out, _ = _run("threemf", str(self.folder / "box.3mf"), "--process", "printing", "--units", "cm", "--json")
        self.assertEqual(code, 2)
        self.assertIn("a 3MF declares its unit", json.loads(out)["error"])
        code, _, err = _run("stl", str(self.folder / "box.glb"), "--process", "molding")
        self.assertEqual(code, 2)
        self.assertIn("box.glb is a glb, not a stl: use cad glb dfm", err)

    def test_a_usage_error_is_argparses_two_and_a_failed_measurement_one(self) -> None:
        """Exit 1 is a check that failed (a family not measured); a misspelled flag never reads as one, nor
        does a file that is not there."""
        code, _out, err = _run("stl", str(self.box), "--process", "molding", "--not-a-flag")
        self.assertEqual(code, 2)
        self.assertIn("unrecognized arguments: --not-a-flag", err)
        code, out, _ = _run("stl", str(self.folder / "missing.stl"), "--process", "molding", "--json")
        self.assertEqual((code, json.loads(out)["reason"]), (2, "not_found"))

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
        interpreter stands in for it), answering exactly as it does here."""
        argv = (str(self.box), "--process", "molding", "--candidates", "--json")
        _code, here, _ = _run("stl", *argv)
        with mock.patch.object(integration_env, "carries", return_value=False), \
                mock.patch.object(integration_env, "environment", return_value=sys.executable) as made:
            code, there, _ = _run("stl", *argv)
            refused, said, _ = _run("stl", str(self.box), "--process", "molding", "--samples", "3", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(there), json.loads(here))
        self.assertEqual((refused, made.call_count), (2, 1), "a refusal makes no environment")
        self.assertIn("--samples is not molding's", json.loads(said)["error"])

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
            face = cad.model.inspect(ident, sharp[0].location)
            self.assertEqual(face["kind"], "edge" if " edge " in f" {sharp[0].location} " else "face")
            code, out, _ = _run("model", ident, "--process", "cnc", "--json")
            self.assertEqual(code, 1)
            self.assertIn("cnc.internal_corner_sharp", {f["code"] for f in json.loads(out)["findings"]})
            refused, said, _ = _run("xbf", ident, "--process", "cnc", "--json")
            self.assertEqual((refused, json.loads(said)["reason"]), (2, "wrong_type"))
            self.assertIn("use cad model dfm", json.loads(said)["error"])

    def test_a_model_given_no_process_is_checked_for_the_one_its_part_declares(self) -> None:
        """Reads the part's declared process back from the engine's document. DEPENDS ON THE ENGINE ROUND-TRIP:
        the material's process must survive the xbf (``cad.engine.document``); until it does, the loaded part's
        ``material.process`` is None and this fails with "no part declares one"."""
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


if __name__ == "__main__":
    unittest.main()
