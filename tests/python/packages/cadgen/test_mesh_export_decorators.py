"""@stl/@glb/@threemf: declared mesh exports produced by the model run.

The decorators are metadata-attachers lowered into EntrySpec.mesh_exports;
production runs through the ONE mesh engine the `cadgen stl|3mf|glb build`
doors use, gated by the shared content-keyed ledger. Contracts pinned here:
stacking order is behavior-neutral (AST scanning sees the whole decorator
list), duplicates and @dxf misuse fail loudly, bare declarations land beside
the STEP artifact, script runs produce/heal declared exports without rebuilding
the model, and the format door byte-matches the script run, shares its ledger,
and writes nothing outside its own format.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

REPO = Path(__file__).resolve().parents[4]
PYTHON = sys.executable

MODEL = textwrap.dedent("""\
    from cadgen import build123d as bd
    from cadgen import glb, step, stl, threemf


    SIZE = 12.0


    @step(out="../STEP/widget.step")
    @stl(out="../STL/widget.stl")
    @glb
    @threemf(out="../3MF/widget.3mf", mesh_tolerance=5e-3)
    def widget():
        body = bd.Box(SIZE, SIZE / 2, 3)
        body -= bd.Pos(0, 0, 0) * bd.Cylinder(2, 10)
        return body


    if __name__ == "__main__":
        widget()
    """)


class MeshExportMetadataTest(unittest.TestCase):
    def _parse(self, body: str):
        from cadgen.metadata import parse_generator_metadata

        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "model.py"
            script.write_text(body, encoding="utf-8")
            return parse_generator_metadata(script)

    def test_declarations_parse_and_order_is_neutral(self) -> None:
        below = self._parse(MODEL)
        above = self._parse(
            MODEL.replace(
                '@step(out="../STEP/widget.step")\n@stl(out="../STL/widget.stl")',
                '@stl(out="../STL/widget.stl")\n@step(out="../STEP/widget.step")',
            )
        )
        for metadata in (below, above):
            # Order neutrality covers the MODEL format too, not just the mesh
            # declarations: @stl above @step must not be mis-taken as the
            # model (the parser bug that hid behind mesh-only assertions).
            self.assertEqual("step", metadata.format)
            self.assertEqual(metadata.out_target, "../STEP/widget.step")
            declared = {d.fmt: d for d in metadata.mesh_exports}
            self.assertEqual(set(declared), {"stl", "glb", "3mf"})
            self.assertEqual(declared["stl"].out, "../STL/widget.stl")
            self.assertIsNone(declared["glb"].out)
            self.assertEqual(declared["3mf"].mesh_tolerance, 5e-3)

    def test_a_mesh_decorator_alone_declares_a_model_with_no_step_output(self) -> None:
        # No @step at all: still a model (format "step" -- the same tree and
        # record), whose .step is not among its outputs.
        metadata = self._parse(MODEL.replace('@step(out="../STEP/widget.step")\n', ""))
        self.assertEqual("step", metadata.format)
        self.assertFalse(metadata.step_output)
        self.assertIsNone(metadata.out_target)
        self.assertEqual({d.fmt for d in metadata.mesh_exports}, {"stl", "glb", "3mf"})
        self.assertTrue(self._parse(MODEL).step_output)

    def test_variants_parse_but_ambiguous_duplicates_fail(self) -> None:
        # Same format at DISTINCT targets is a variant, not a duplicate.
        variants = self._parse(textwrap.dedent("""\
            from cadgen import build123d as bd
            from cadgen import step, stl

            @step
            @stl(out="a_draft.stl", mesh_tolerance=8e-3)
            @stl(out="a_print.stl", mesh_tolerance=4e-4)
            def part():
                return bd.Box(1, 1, 1)


            if __name__ == "__main__":
                part()
            """))
        self.assertEqual([d.out for d in variants.mesh_exports],
                         ["a_draft.stl", "a_print.stl"])
        # Two bare declarations collide at the sibling default.
        with self.assertRaises(ValueError):
            self._parse(MODEL.replace("@glb\n", "@glb\n@glb\n"))
        # Two identical out= targets collide outright.
        with self.assertRaises(ValueError):
            self._parse(MODEL.replace(
                '@stl(out="../STL/widget.stl")',
                '@stl(out="../STL/widget.stl")\n@stl(out="../STL/widget.stl")',
            ))

    def test_dxf_misuse_fails_in_either_order(self) -> None:
        """A mesh export on a drawing is rejected however it is stacked.

        Order neutrality is the point of the AST scan, so the misuse guard has to
        be order-neutral too. Only `@dxf` above `@stl` was pinned; the reversed
        order was verified by hand and left unpinned, which is exactly how the
        `ast.Name` model-format bug survived on the other side of this file."""
        for above, below in (("@dxf", "@stl"), ("@stl", "@dxf")):
            with self.subTest(order=f"{above} above {below}"):
                with self.assertRaises(ValueError):
                    self._parse(
                        "from cadgen import dxf, stl\n\n"
                        f"{above}\n{below}\n"
                        "def drawing():\n"
                        "    from cadgen import build123d as bd\n"
                        "    return bd.Rectangle(10, 5)\n"
                    )

    def test_runtime_decorators_converge_both_orders(self) -> None:
        from cadgen.authoring import step as step_deco, stl as stl_deco

        def below():
            return None

        from cadgen.authoring import _REGISTRY, registered_model
        from cadgen.store.index import model_ref

        this_file = Path(__file__).resolve()
        self.addCleanup(_REGISTRY.pop, model_ref(this_file, "below"), None)
        self.addCleanup(_REGISTRY.pop, model_ref(this_file, "above"), None)

        stl_deco(out="a.stl")(below)
        step_deco(below)
        model = registered_model(this_file, "below")
        self.assertIsNotNone(model)
        self.assertEqual({d.fmt for d in model.mesh_exports}, {"stl"})

        # A file may hold several models: the other stacking order registers a
        # second one beside the first, each under its own name.
        def above():
            return None

        step_deco(above)
        stl_deco(out="b.stl")(above)
        model = registered_model(this_file, "above")
        self.assertEqual({d.fmt for d in model.mesh_exports}, {"stl"})


class MeshExportProductionTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="mesh-export-decl-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        (self.project / "src").mkdir()
        (self.project / "src" / "widget.py").write_text(MODEL, encoding="utf-8")
        self.env = dict(os.environ)
        self.env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
            "CADGEN_CACHE_DIR": str(self.project / "store"),
            "PYTHONPATH": str(REPO / "packages/cadgen/src"),
        })

    def _run(self, *argv: str) -> subprocess.CompletedProcess:
        proc = subprocess.run(
            [PYTHON, *argv], cwd=str(self.project), env=self.env,
            capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return proc

    def test_script_run_produces_heals_and_matches_cli(self) -> None:
        first = self._run("src/widget.py")
        for rel in ("STEP/widget.step", "STL/widget.stl", "STEP/widget.glb", "3MF/widget.3mf"):
            self.assertTrue((self.project / rel).is_file(), rel)
        self.assertIn("wrote STL", first.stderr)

        # True no-op: nothing rewritten.
        second = self._run("src/widget.py")
        self.assertNotIn("wrote", second.stdout)

        # Healing is per-export: delete one, only it comes back.
        (self.project / "STL" / "widget.stl").unlink()
        heal = self._run("src/widget.py")
        self.assertIn("wrote STL", heal.stderr)
        self.assertNotIn("wrote GLB", heal.stderr)

        # DOOR parity: a bare `cadgen stl build` on the DOCUMENT reads no
        # declaration — it writes the sibling default beside the document once,
        # and the shared ledger makes the next bare run a no-op; an explicit OUT
        # is byte-identical to what the run wrote.
        door = "from cadgen.cli.stl_build import main; raise SystemExit(main())"
        sibling = self._run("-c", door, "STEP/widget.step", "--verbose")
        self.assertIn("wrote STL", sibling.stdout)
        self.assertTrue((self.project / "STEP" / "widget.stl").is_file())
        skip = self._run("-c", door, "STEP/widget.step", "--verbose")
        self.assertNotIn("tessellate", skip.stderr + skip.stdout)
        self.assertIn("current STL", skip.stdout)
        explicit = self.project / "parity.stl"
        self._run("-c", door, "STEP/widget.step", str(explicit))
        self.assertEqual(
            explicit.read_bytes(),
            (self.project / "STL" / "widget.stl").read_bytes(),
            "the door and the script run must write byte-identical STL",
        )

        # --force re-exports past the ledger but does NOT rebuild the model:
        # the bytes are the same because the geometry is.
        sibling_path = self.project / "STEP" / "widget.stl"
        before = sibling_path.read_bytes()
        forced = self._run("-c", door, "STEP/widget.step", "--force", "--verbose")
        self.assertIn("wrote STL", forced.stdout)
        self.assertNotIn("run step model", forced.stderr)
        self.assertEqual(before, sibling_path.read_bytes())

        # A door writes ONLY its own format: nothing here touches the .step or
        # the sibling declarations of the other two formats.
        glb_before = (self.project / "STEP" / "widget.glb").read_bytes()
        step_before = (self.project / "STEP" / "widget.step").read_bytes()
        self._run("-c", door, "STEP/widget.step", "--force")
        self.assertEqual(glb_before, (self.project / "STEP" / "widget.glb").read_bytes())
        self.assertEqual(step_before, (self.project / "STEP" / "widget.step").read_bytes())

    def test_a_declared_export_the_exporter_could_not_write_leaves_the_model_stale(self) -> None:
        # Regression: a build whose mesh export FAILED still published a record
        # listing only the STEP and its sidecar, so the next gate said "current"
        # and the declared STL was missing forever (seen on a checkout with no
        # node_modules). Every declared output is listed from the first publish,
        # sha-less until written, and an unwritten one reads as stale.
        import json

        broken = dict(self.env, CADGEN_NODE=str(self.project / "no-such-node"))
        failed = subprocess.run(
            [PYTHON, "src/widget.py"], cwd=str(self.project), env=broken,
            capture_output=True, text=True, timeout=600,
        )
        self.assertNotEqual(failed.returncode, 0, failed.stdout + failed.stderr)
        self.assertTrue((self.project / "STEP" / "widget.step").is_file())
        self.assertFalse((self.project / "STL" / "widget.stl").exists())

        why = subprocess.run(
            [PYTHON, "-m", "cadgen.cli", "store", "why", "src/widget.py", "--json"],
            cwd=str(self.project), env=self.env, capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(why.returncode, 1, why.stdout + why.stderr)
        verdict = json.loads(why.stdout.strip().splitlines()[-1])
        self.assertTrue(verdict["stale"])
        clause5 = next(c for c in verdict["clauses"] if c["clause"] == 5)
        unwritten = {Path(o["path"]).name: o["why"] for o in clause5["outputs"] if o["stale"]}
        self.assertEqual(unwritten, {"widget.stl": "never written", "widget.glb": "never written", "widget.3mf": "never written"})

        # With the exporter back, the gate's verdict drives the run: the meshes are written.
        healed = self._run("src/widget.py")
        self.assertIn("wrote STL", healed.stderr)
        for rel in ("STL/widget.stl", "STEP/widget.glb", "3MF/widget.3mf"):
            self.assertTrue((self.project / rel).is_file(), rel)
        again = self._run("src/widget.py")
        self.assertIn("current", again.stdout)

    def test_a_mesh_only_model_builds_its_meshes_and_no_step(self) -> None:
        # Regression: @stl with no @step used to be a SILENT NO-OP (the pending
        # declaration never registered; the static parser said "no model"). It is
        # a model -- tree, record, job -- whose outputs are its meshes; no .step.
        from unittest import mock

        source = MODEL.replace('@step(out="../STEP/widget.step")\n', "").replace("widget", "blank")
        (self.project / "src" / "blank.py").write_text(source, encoding="utf-8")
        first = self._run("src/blank.py")
        for rel in ("STL/blank.stl", "3MF/blank.3mf", "src/blank.glb"):
            self.assertTrue((self.project / rel).is_file(), rel)
        self.assertIn("wrote STL", first.stderr)
        for rel in ("src/blank.step", "STEP/blank.step", "src/blank.step.json"):
            self.assertFalse((self.project / rel).exists(), f"{rel} must not be written")

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.project / "store")}):
            from cadgen.store.gate import stale
            from cadgen.store.records import read_record

            record = read_record(self.project / "src" / "blank.py") or {}
            self.assertTrue(record.get("tree"), "a mesh-only model has a tree like any model")
            self.assertFalse(any(p.endswith(".step") for p in record.get("outputs") or {}))
            self.assertFalse(stale(self.project / "src" / "blank.py").stale)

        # True no-op on rerun, and healing per export like any declared output.
        second = self._run("src/blank.py")
        self.assertNotIn("wrote", second.stdout)
        (self.project / "STL" / "blank.stl").unlink()
        heal = self._run("src/blank.py")
        self.assertIn("wrote STL", heal.stderr)
        self.assertNotIn("wrote GLB", heal.stderr)

    def test_a_bare_door_writes_one_mesh_beside_the_document(self) -> None:
        # A door reads no declarations. Two @stl variants belong to the RUN
        # (python src/widget.py writes both); a bare door on the document writes
        # exactly one STL, the sibling default, and the ledger makes the second
        # bare run a no-op.
        (self.project / "src" / "widget.py").write_text(
            MODEL.replace(
                '@stl(out="../STL/widget.stl")',
                '@stl(out="../STL/widget_draft.stl", mesh_tolerance=2e-2)\n'
                '@stl(out="../STL/widget_print.stl", mesh_tolerance=2e-4)',
            ),
            encoding="utf-8",
        )
        self._run("src/widget.py")
        draft = self.project / "STL" / "widget_draft.stl"
        printed = self.project / "STL" / "widget_print.stl"
        self.assertTrue(draft.is_file() and printed.is_file(), "the run writes its declared variants")
        self.assertFalse((self.project / "STEP" / "widget.step.json").exists(), "no kinematics, no sidecar")

        wrote = self._run("-c", "from cadgen.cli.stl_build import main; raise SystemExit(main())",
                          "STEP/widget.step")
        sibling = self.project / "STEP" / "widget.stl"
        self.assertTrue(sibling.is_file(), wrote.stdout + wrote.stderr)
        self.assertEqual(1, wrote.stdout.count("wrote STL"), wrote.stdout)

        again = self._run("-c", "from cadgen.cli.stl_build import main; raise SystemExit(main())",
                          "STEP/widget.step")
        self.assertEqual(1, again.stdout.count("current STL"), again.stdout)


if __name__ == "__main__":
    unittest.main()
