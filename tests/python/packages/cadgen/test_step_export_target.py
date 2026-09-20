"""The mesh engine behind `cadgen stl|3mf|glb build`: `export_cad_target`.

It takes a DOCUMENT and writes the meshes it was asked for from the tree behind the
document's bytes. Pinned here against real geometry: what it refuses (a script, a
missing file, a non-mesh format), what it writes, the effective tolerances it
reports, native path semantics for an explicit OUT, and that the temporary view it
hands the Node exporter is gone when the export is over -- written, or failed.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import step_export_target  # noqa: E402
from tests.python.support.cad_test_roots import ClassCadRoots, IsolatedCadRoots  # noqa: E402

# A tiny generated model: model() returns a single labeled solid.
BOX_GENERATOR = """from build123d import Box


from cadgen import step
@step
def model():
    return Box(10.0, 10.0, 10.0)


if __name__ == "__main__":
    model()
"""

# Magic bytes we can assert on; STL (binary) just gets a non-empty check.
FORMAT_MAGIC = {
    "glb": b"glTF",
    "stl": None,
    "3mf": b"PK",
}


class StepExportTargetTests(unittest.TestCase):
    # box.step is built ONCE for the class, the one way a document is written (by
    # running its model script): every test exports from a copy and rebuilds nothing.
    @classmethod
    def setUpClass(cls) -> None:
        from cadgen.generation import generate_step_targets

        super().setUpClass()
        cls._class_roots = ClassCadRoots(prefix="cadexp-seed-")
        cls._seed_dir = cls._class_roots.cad_root / "seed"
        cls._seed_dir.mkdir()
        generator = cls._seed_dir / "box.py"
        generator.write_text(BOX_GENERATOR, encoding="utf-8")
        if generate_step_targets([str(generator)]) != 0 or not (cls._seed_dir / "box.step").is_file():
            raise RuntimeError("the model script wrote no box.step")

    @classmethod
    def tearDownClass(cls) -> None:
        cls._class_roots.cleanup()
        super().tearDownClass()

    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadexp-")
        self._tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadexp-")
        self.temp_root = Path(self._tempdir.name)
        self.out_dir = self.temp_root / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._class_roots.copy_store_into(self._isolated_roots)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _assert_export_file(self, out_path: Path, fmt: str) -> None:
        self.assertTrue(out_path.is_file(), f"{fmt} output missing")
        data = out_path.read_bytes()
        self.assertGreater(len(data), 0, f"{fmt} output is empty")
        magic = FORMAT_MAGIC[fmt]
        if magic is not None:
            self.assertTrue(data.startswith(magic), f"{fmt} wrong magic: {data[:16]!r}")

    def _write_box_document(self) -> Path:
        """A real .step on disk -- what the mesh doors take.

        DOCUMENTS-ONLY: `export_cad_target` is the engine behind
        `cadgen stl|3mf|glb build`, which never sees a script.
        """
        document = self.temp_root / "box_document.step"
        shutil.copyfile(self._seed_dir / "box.step", document)
        return document

    @contextlib.contextmanager
    def _recorded_views(self):
        """Every temporary view directory the engine asked the store for."""
        from cadgen.store import view as store_view

        views: list[Path] = []
        real_export_view = store_view.export_view

        def recording(*args, **kwargs):
            views.append(real_export_view(*args, **kwargs))
            return views[-1]

        with mock.patch.object(store_view, "export_view", side_effect=recording):
            yield views

    def test_a_missing_document_is_refused_by_name(self) -> None:
        missing = self.temp_root / "does_not_exist.step"
        with self.assertRaises(FileNotFoundError) as cm:
            step_export_target.export_cad_target(missing, [("stl", self.out_dir / "missing.stl")])
        self.assertIn("does_not_exist.step", str(cm.exception))
        self.assertFalse((self.out_dir / "missing.stl").exists())

    def test_a_model_script_is_refused_by_naming_the_run(self) -> None:
        # The ENGINE owns the one validation of TARGET (doors.document_target), so a
        # direct caller is refused exactly as a door's user is.
        script = self.temp_root / "box.py"
        script.write_text(BOX_GENERATOR, encoding="utf-8")
        with self.assertRaises(ValueError) as cm:
            step_export_target.export_cad_target(script, [("stl", None)])
        self.assertIn("a model script is a program", str(cm.exception))
        self.assertFalse(script.with_suffix(".stl").exists())

    def test_export_cad_target_rejects_step_format(self) -> None:
        # A format door writes only its own format: the model script (or
        # `cadgen step build`) owns .step files.
        document = self._write_box_document()
        with self.assertRaises(ValueError) as cm:
            step_export_target.export_cad_target(document, [("step", None)])
        self.assertIn("Unsupported export format: step", str(cm.exception))

    def test_an_unknown_format_is_refused_by_naming_the_formats(self) -> None:
        document = self._write_box_document()
        with self.assertRaises(ValueError) as cm:
            step_export_target.export_cad_target(document, [("iges", self.out_dir / "box.iges")])
        self.assertIn("Supported formats: stl, 3mf, glb", str(cm.exception))

    def test_export_cad_target_writes_mesh_formats(self) -> None:
        document = self._write_box_document()
        payload = step_export_target.export_cad_target(
            document,
            [
                (fmt, self.out_dir / f"box.{fmt}")
                for fmt in step_export_target.MESH_EXPORT_FORMATS
            ],
        )
        self.assertTrue(payload["ok"])
        for entry in payload["files"]:
            self._assert_export_file(Path(entry["path"]), entry["format"])
            # The result reports the EFFECTIVE pair: no tolerance was asked for, so
            # these are the tessellator's defaults -- numbers, never null.
            self.assertEqual(1.5e-3, entry["meshTolerance"])
            self.assertEqual(0.35, entry["meshAngularTolerance"])

    def test_an_asked_for_tolerance_is_the_one_reported(self) -> None:
        document = self._write_box_document()
        payload = step_export_target.export_cad_target(
            document, [("stl", self.out_dir / "coarse.stl")], mesh_tolerance=5e-3
        )
        self.assertEqual(5e-3, payload["files"][0]["meshTolerance"])
        self.assertEqual(0.35, payload["files"][0]["meshAngularTolerance"])

    def test_the_temporary_view_is_removed_after_an_export(self) -> None:
        # The Node exporter reads a temporary VIEW of the tree. It is removed when
        # the export is done -- never at interpreter exit, which a recycled or
        # killed daemon worker never reaches.
        document = self._write_box_document()
        with self._recorded_views() as views:
            step_export_target.export_cad_target(document, [("stl", self.out_dir / "box.stl")])
        self.assertEqual(1, len(views))
        self.assertFalse(views[0].exists(), "the export left its view directory behind")
        self._assert_export_file(self.out_dir / "box.stl", "stl")

    def test_the_temporary_view_is_removed_when_the_ledger_skips_the_export(self) -> None:
        document = self._write_box_document()
        out = self.out_dir / "box.stl"
        step_export_target.export_cad_target(document, [("stl", out)])
        with self._recorded_views() as views:
            payload = step_export_target.export_cad_target(document, [("stl", out)])
        self.assertTrue(payload["files"][0]["skipped"])
        self.assertTrue(views)
        self.assertEqual([], [view for view in views if view.exists()])

    def test_the_temporary_view_is_removed_when_the_export_raises(self) -> None:
        document = self._write_box_document()

        def exporter_fails(package_dir, *args, **kwargs):
            self.assertTrue(Path(package_dir).is_dir(), "the view exists while the exporter runs")
            raise RuntimeError("mesh export failed for stl: node fell over")

        with self._recorded_views() as views, \
                mock.patch.object(step_export_target, "run_mesh_exporter", side_effect=exporter_fails), \
                self.assertRaisesRegex(RuntimeError, "node fell over"):
            step_export_target.export_cad_target(document, [("stl", self.out_dir / "boom.stl")])
        self.assertEqual(1, len(views))
        self.assertFalse(views[0].exists(), "a failed export left its view directory behind")

    def test_explicit_out_takes_native_path_semantics(self) -> None:
        # An explicit OUT is a one-shot ad-hoc export, never persisted, so it
        # resolves like every other cadgen path argument: relative against the
        # PROCESS cwd (not beside the document), absolute as given, ~ expanded.
        # The persisted form is the decorator declaration, which stays
        # script-anchored and is honoured by the model's own run, never by a door.
        logical_step = self.temp_root / "docs" / "box.step"
        cwd = self.temp_root / "elsewhere"
        cwd.mkdir(parents=True, exist_ok=True)
        home = self.temp_root / "home"
        home.mkdir(parents=True, exist_ok=True)

        with contextlib.chdir(cwd):
            relative = step_export_target._resolve_export_output(
                "stl", "out.stl", document=logical_step
            )
            self.assertEqual(relative, (cwd / "out.stl").resolve())
            self.assertNotEqual(relative.parent, logical_step.parent)

            absolute_target = self.out_dir / "absolute.stl"
            self.assertEqual(
                step_export_target._resolve_export_output(
                    "stl", str(absolute_target), document=logical_step
                ),
                absolute_target.resolve(),
            )

            # Both spellings of "the home directory": ``~`` expansion reads
            # HOME on POSIX and USERPROFILE (then HOMEDRIVE+HOMEPATH) on
            # Windows, so a HOME-only sandbox silently expanded to the real
            # user profile there. Both sides are resolved before comparing:
            # Windows hands back 8.3 short components (``RUNNER~1``) in some
            # environment values and the long form everywhere else.
            drive, tail = os.path.splitdrive(str(home))
            sandbox_home = {
                "HOME": str(home),
                "USERPROFILE": str(home),
                "HOMEDRIVE": drive,
                "HOMEPATH": tail,
            }
            with mock.patch.dict(os.environ, sandbox_home, clear=False):
                self.assertEqual(
                    step_export_target._resolve_export_output(
                        "stl", "~/tilde.stl", document=logical_step
                    ).resolve(),
                    (home / "tilde.stl").resolve(),
                )

    def test_an_out_with_the_wrong_suffix_is_refused_before_any_work(self) -> None:
        document = self._write_box_document()
        with self._recorded_views() as views, self.assertRaisesRegex(ValueError, "stl OUT must end with .stl"):
            step_export_target.export_cad_target(document, [("stl", self.out_dir / "box.bin")])
        self.assertEqual([], views)

    def test_a_relative_out_lands_in_the_process_cwd(self) -> None:
        # The live door-level pin for the rule above: the document is in one
        # directory, the process is in another, and the file appears where the
        # process is.
        document = self._write_box_document()
        cwd = self.temp_root / "run_from_here"
        cwd.mkdir(parents=True, exist_ok=True)
        with contextlib.chdir(cwd):
            payload = step_export_target.export_cad_target(document, [("stl", "cwd_relative.stl")])
        self.assertTrue(payload["ok"])
        self.assertEqual(
            Path(payload["files"][0]["path"]), (cwd / "cwd_relative.stl").resolve()
        )
        self._assert_export_file(cwd / "cwd_relative.stl", "stl")
        self.assertFalse((document.parent / "cwd_relative.stl").exists())

    def test_color_hex_encodes_linear_to_srgb(self) -> None:
        # A model's Color is LINEAR; --default-color is an sRGB hex. 0 and 1 are
        # fixed points of the transfer function, so only midtones can tell a
        # correct encoding from no encoding at all.
        self.assertEqual(step_export_target._color_hex((1.0, 0.0, 0.0, 1.0)), "#ff0000")
        self.assertEqual(step_export_target._color_hex((0.5, 0.5, 0.5, 1.0)), "#bcbcbc")
        self.assertEqual(step_export_target._color_hex((0.2, 0.5, 0.8, 1.0)), "#7cbce7")
        # Out-of-range channels clamp; non-numeric input has no usable colour.
        self.assertEqual(step_export_target._color_hex((2.0, -1.0, 0.0)), "#ff0000")
        self.assertIsNone(step_export_target._color_hex(None))
        self.assertIsNone(step_export_target._color_hex(("red", "green", "blue")))


if __name__ == "__main__":
    unittest.main()
