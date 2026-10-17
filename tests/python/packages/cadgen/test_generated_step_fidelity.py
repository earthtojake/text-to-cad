"""A generated model's tree carries its colors and nothing source-derived.

Generators author per-occurrence colors, and the tree records each one on its
occurrence. Everything source-derived (pose, mates, provenance) lives in the
sidecar and the model record, never in the tree.
"""

from __future__ import annotations

import json
import shutil
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen.catalog import result_view_dir  # noqa: E402
from tests.python.support.cad_test_roots import ClassCadRoots, IsolatedCadRoots  # noqa: E402

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
    # The generated package is built ONCE for the class: every test reads a COPY
    # of it in its own store, none rebuilds it.
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._class_roots = ClassCadRoots(prefix="cadfid-seed-")
        cls._seed_dir = cls._class_roots.cad_root / "seed"
        cls._seed_dir.mkdir()
        generator = cls._seed_dir / "colored.py"
        generator.write_text(COLORED_ASSEMBLY_GENERATOR, encoding="utf-8")
        # Built the ONE way a generated document is: by running its model.
        from cadgen.generation import generate_step_targets

        if generate_step_targets([str(generator)]) != 0 or not (cls._seed_dir / "colored.step").is_file():
            raise RuntimeError("the seed model wrote no colored.step")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._class_roots.cleanup()
        super().tearDownClass()

    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadfid-")
        self._tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadfid-")
        self.temp_root = Path(self._tempdir.name)
        self._class_roots.copy_store_into(self._isolated_roots)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _build_generated_package(self) -> tuple[Path, Path]:
        """The seed build's script, document and sidecar, copied beside this test's store."""
        for name in ("colored.py", "colored.step", "colored.step.json"):
            source = self._seed_dir / name
            if source.is_file():
                shutil.copyfile(source, self.temp_root / name)
        return self.temp_root / "colored.py", self.temp_root / "colored.step"

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

        # Provenance is the model RECORD behind the document, keyed by the path the
        # model wrote; the copied store carries it under the seed's path.
        provenance = read_source_provenance(self._seed_dir / "colored.step") or {}
        self.assertEqual(provenance.get("sourceKind"), "python")


if __name__ == "__main__":
    unittest.main()
