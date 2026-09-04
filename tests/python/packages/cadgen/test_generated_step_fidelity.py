"""The assembled .step is the document: it must carry the model's colors, and
it must carry NOTHING else — no cadgen metadata, no link back to source code.

Regression suite for the planetary-pilot color loss (2026-08-30):
``assemble_step_from_package`` read colors only from the COMPONENT entry,
while generators author per-occurrence colors — every such model's .step was
written colorless, so any import of it was colorless too. Colors are baked
into the STEP; everything source-derived (pose, mates, provenance) lives in
the tree's source sidecar and is deliberately NOT in the file, so importing
a bare generated .step yields a plain imported package (renders, no pose) and
running the model script restores the rest.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import step_artifact_cli  # noqa: E402
from cadgen._internal.step_assemble import assemble_step_from_package  # noqa: E402
from cadgen.catalog import result_view_dir  # noqa: E402
from tests.python.support.cad_test_roots import IsolatedCadRoots  # noqa: E402

# Two occurrences of DISTINCT parts with per-occurrence colors and a
# kinematics block — the planetary pilot's shape of metadata, minimized.
COLORED_ASSEMBLY_GENERATOR = """from build123d import Box, Color, Compound, Location

import cadgen
from cadgen import step


@step(kinematics={
    "mates": [cadgen.revolute("drive", parent="#left", child="#right",
                              origin=(20, 0, 0), direction=(0, 0, 1),
                              limits=(0, 360))],
})
def model():
    left = Box(10.0, 10.0, 10.0)
    left.label = "left"
    left.color = Color(1.0, 0.0, 0.0, 1.0)
    right = Box(6.0, 6.0, 6.0).moved(Location((20.0, 0.0, 0.0)))
    right.label = "right"
    right.color = Color(0.0, 0.0, 1.0, 1.0)
    return Compound(children=[left, right])


if __name__ == "__main__":
    model()
"""


class GeneratedStepFidelityTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadfid-")
        self._tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadfid-")
        self.temp_root = Path(self._tempdir.name)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _build_generated_package(self) -> tuple[Path, Path]:
        generator = self.temp_root / "colored.py"
        generator.write_text(COLORED_ASSEMBLY_GENERATOR, encoding="utf-8")
        logical_step = self.temp_root / "colored.step"
        payload = step_artifact_cli.build_step_artifact(
            repo_root=Path.cwd(),
            step=logical_step,
            source_path=generator,
        )
        self.assertTrue(payload.get("ok"), payload)
        return generator, logical_step

    def _descriptor(self, step_path: Path) -> dict:
        return json.loads(
            (result_view_dir(step_path) / "assembly.json").read_text(encoding="utf-8")
        )

    def test_generated_descriptor_records_occurrence_colors_and_pose(self) -> None:
        _, logical_step = self._build_generated_package()
        descriptor = self._descriptor(logical_step)
        occurrences = descriptor.get("occurrences") or []
        self.assertEqual(len(occurrences), 2)
        colored = [o for o in occurrences if isinstance(o.get("color"), list)]
        self.assertEqual(len(colored), 2, occurrences)
        # Source-derived state rides the sidecar, never the descriptor: the
        # kinematics lives in the .step.json sidecar, and its existence is the
        # generated marker (the descriptor carries no sourceKind at all).
        self.assertNotIn("pose", descriptor)
        self.assertNotIn("paramsPath", descriptor)
        self.assertNotIn("sourceKind", descriptor)
        from cadgen._internal.source_sidecar import read_source_sidecar

        sidecar = read_source_sidecar(logical_step)
        self.assertIsInstance(sidecar, dict)
        block = sidecar.get("kinematics")
        self.assertIsInstance(block, dict)
        self.assertEqual(block["mates"][0]["name"], "drive")
        # Provenance moved to the records tier (schema 5): the sidecar beside
        # the artifact carries declarations only, never a source tie.
        self.assertNotIn("sourceKind", sidecar)
        self.assertNotIn("sourcePath", sidecar)
        from cadgen._internal.source_sidecar import read_source_provenance

        provenance = read_source_provenance(logical_step) or {}
        self.assertEqual(provenance.get("sourceKind"), "python")

    def test_assembled_step_carries_occurrence_colors(self) -> None:
        _, logical_step = self._build_generated_package()
        out = self.temp_root / "out" / "colored.step"
        out.parent.mkdir(parents=True, exist_ok=True)
        assemble_step_from_package(result_view_dir(logical_step), out)
        text = out.read_text(encoding="utf-8", errors="ignore")
        self.assertIn(
            "COLOUR",
            text,
            "assembled STEP must carry the occurrence colors the descriptor records",
        )

    def test_generate_and_import_produce_one_descriptor_schema(self) -> None:
        """The Phase-2 invariant: assembly.json is a pure function of the STEP
        bytes plus schema versions, whichever producer wrote it. Generating a
        model and importing its own exported STEP must yield descriptors with
        the SAME key set, the same identity fields, and equivalent geometry.

        Deliberately NOT byte-identity: the STEP text round-trip is not
        BREP-byte-preserving (component cids and adaptive-mesh stats may
        differ), so byte-unification is a Phase-3 decision, not this gate.
        """
        _, logical_step = self._build_generated_package()
        generated = self._descriptor(logical_step)

        exported_dir = self.temp_root / "roundtrip"
        exported_dir.mkdir()
        exported = exported_dir / "colored.step"
        assemble_step_from_package(result_view_dir(logical_step), exported)
        payload = step_artifact_cli.build_step_artifact(
            repo_root=Path.cwd(),
            step=exported,
        )
        self.assertTrue(payload.get("ok"), payload)
        imported = self._descriptor(exported)

        # Schema purity: one key set, no source-derived keys on either side.
        self.assertEqual(sorted(generated.keys()), sorted(imported.keys()))
        for banned in (
            "sourceKind", "sourcePath", "sourceHash", "sourceClosureHash",
            "sourceClosureFiles", "pose", "generatedAt",
        ):
            self.assertNotIn(banned, generated)
            self.assertNotIn(banned, imported)

        # Identity fields agree.
        for key in ("kind", "entryKind", "units", "rootName"):
            self.assertEqual(generated.get(key), imported.get(key), key)

        # Geometric equivalence: same occurrence structure and bounds (cids
        # and mesh stats are allowed to differ across the round trip).
        self.assertEqual(
            len(generated.get("occurrences") or []),
            len(imported.get("occurrences") or []),
        )
        self.assertEqual(
            sorted(o.get("name") for o in generated["occurrences"]),
            sorted(o.get("name") for o in imported["occurrences"]),
        )
        for axis in ("min", "max"):
            for got, expected in zip(imported["bbox"][axis], generated["bbox"][axis]):
                self.assertAlmostEqual(got, expected, places=3)

    def test_written_step_carries_no_cadgen_metadata(self) -> None:
        # The written file is a plain artifact: no cadgen: properties, no
        # source path, no source hash — under any circumstances.
        _, logical_step = self._build_generated_package()
        exported_dir = self.temp_root / "clean"
        exported_dir.mkdir()
        exported = exported_dir / "colored.step"
        assemble_step_from_package(result_view_dir(logical_step), exported)
        text = exported.read_text(encoding="utf-8", errors="ignore")
        self.assertNotIn("cadgen:", text)
        self.assertNotIn("colored.py", text)

    def test_import_of_generated_step_preserves_colors(self) -> None:
        # A bare generated STEP is simply importable (nothing in the file says
        # otherwise) — and thanks to the colored assembly, the derived package
        # keeps the geometry colors. Pose/mates live in the sidecar, so they
        # are absent until the model script runs again.
        _, logical_step = self._build_generated_package()
        exported_dir = self.temp_root / "imported"
        exported_dir.mkdir()
        exported = exported_dir / "colored.step"
        assemble_step_from_package(result_view_dir(logical_step), exported)

        payload = step_artifact_cli.build_step_artifact(
            repo_root=Path.cwd(),
            step=exported,
        )
        self.assertTrue(payload.get("ok"), payload)
        descriptor = self._descriptor(exported)
        self.assertNotIn("sourceKind", descriptor)
        from cadgen._internal.source_sidecar import model_is_generated

        self.assertFalse(
            model_is_generated(exported),
            "an import must not leave a source sidecar behind",
        )
        occurrences = descriptor.get("occurrences") or []
        colored = [o for o in occurrences if isinstance(o.get("color"), list)]
        self.assertEqual(
            len(colored),
            len(occurrences),
            f"re-import must keep the STEP's colors: {occurrences}",
        )


if __name__ == "__main__":
    unittest.main()
