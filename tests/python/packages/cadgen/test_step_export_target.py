from __future__ import annotations

import contextlib
import json
import os
import shutil
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import render as cad_render  # noqa: E402
from cadgen import step_export_target  # noqa: E402
from tests.python.support.cad_test_roots import IsolatedCadRoots  # noqa: E402

# A tiny generated model: model() returns a single labeled solid.
BOX_GENERATOR = """from build123d import Box


from cadgen import step
@step
def model():
    return Box(10.0, 10.0, 10.0)


if __name__ == "__main__":
    model()
"""

# Magic bytes we can assert on; STL (binary) and 3MF (zip) just get a non-empty check.
FORMAT_MAGIC = {
    "glb": b"glTF",
    "step": b"ISO-10303-21",
    "stl": None,
    "3mf": None,
}
FORMATS = ("step", "stl", "3mf", "glb")


class StepExportTargetTests(unittest.TestCase):
    def setUp(self) -> None:
        self._isolated_roots = IsolatedCadRoots(self, prefix="cadexp-")
        self._tempdir = self._isolated_roots.temporary_cad_directory(prefix="tmp-cadexp-")
        self.temp_root = Path(self._tempdir.name)
        self.out_dir = self.temp_root / "out"
        self.out_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)
        self._tempdir.cleanup()

    def _run(self, args: list[str]) -> tuple[int, dict]:
        buffer = StringIO()
        with redirect_stdout(buffer):
            code = step_export_target.main(args)
        json_lines = [line for line in buffer.getvalue().splitlines() if line.strip().startswith("{")]
        payload = json.loads(json_lines[-1]) if json_lines else {}
        return code, payload

    def _assert_export_file(self, out_path: Path, fmt: str) -> None:
        self.assertTrue(out_path.is_file(), f"{fmt} output missing")
        data = out_path.read_bytes()
        self.assertGreater(len(data), 0, f"{fmt} output is empty")
        magic = FORMAT_MAGIC[fmt]
        if magic is not None:
            self.assertTrue(data.startswith(magic), f"{fmt} wrong magic: {data[:16]!r}")

    def _write_box_generator(self) -> Path:
        generator = self.temp_root / "box.py"
        generator.write_text(BOX_GENERATOR, encoding="utf-8")
        return generator

    def test_export_generated_step_py_all_formats(self) -> None:
        generator = self._write_box_generator()
        logical_step = self.temp_root / "box.step"
        for fmt in FORMATS:
            out = self.out_dir / f"box.{fmt}"
            code, payload = self._run([
                "--repo-root", str(Path.cwd()),
                "--step", str(logical_step),
                "--source-path", str(generator),
                "--format", fmt,
                "--out", str(out),
            ])
            self.assertEqual(code, 0, f"{fmt}: {payload}")
            self.assertTrue(payload.get("ok"), f"{fmt}: {payload}")
            self.assertEqual(payload.get("format"), fmt)
            self._assert_export_file(out, fmt)
        # The generated export writes only the requested files; no STEP is left beside the source.
        self.assertFalse((self.temp_root / "box.step").exists())

    def test_export_imported_step_all_formats(self) -> None:
        # Materialize a real STEP from the generator, then export from that on-disk file.
        generator = self._write_box_generator()
        imported_step = self.temp_root / "imported.step"
        code, payload = self._run([
            "--repo-root", str(Path.cwd()),
            "--step", str(self.temp_root / "box.step"),
            "--source-path", str(generator),
            "--format", "step",
            "--out", str(imported_step),
        ])
        self.assertEqual(code, 0, payload)
        self.assertTrue(imported_step.is_file())

        for fmt in FORMATS:
            out = self.out_dir / f"imported.{fmt}"
            code, payload = self._run([
                "--repo-root", str(Path.cwd()),
                "--step", str(imported_step),
                "--format", fmt,
                "--out", str(out),
            ])
            self.assertEqual(code, 0, f"{fmt}: {payload}")
            self.assertTrue(payload.get("ok"), f"{fmt}: {payload}")
            self._assert_export_file(out, fmt)

    def test_missing_imported_step_reports_error(self) -> None:
        code, payload = self._run([
            "--repo-root", str(Path.cwd()),
            "--step", str(self.temp_root / "does_not_exist.step"),
            "--format", "stl",
            "--out", str(self.out_dir / "missing.stl"),
        ])
        self.assertEqual(code, 1)
        self.assertFalse(payload.get("ok"))
        self.assertIn("error", payload)

    def _write_box_document(self) -> Path:
        """A real .step on disk — what the mesh doors take.

        DOCUMENTS-ONLY: `export_cad_target` is the engine behind
        `cadgen stl|3mf|glb build`, which never sees a script.
        """
        generator = self._write_box_generator()
        document = self.temp_root / "box_document.step"
        code, payload = self._run([
            "--repo-root", str(Path.cwd()),
            "--step", str(self.temp_root / "box.step"),
            "--source-path", str(generator),
            "--format", "step",
            "--out", str(document),
        ])
        self.assertEqual(code, 0, payload)
        return document

    def test_export_cad_target_rejects_step_format(self) -> None:
        # The Viewer's Save-dialog path (main(), tested above) still exports STEP; the CAD
        # CAD workflow does not — the model script itself owns .step files.
        document = self._write_box_document()
        with self.assertRaises(ValueError) as cm:
            step_export_target.export_cad_target(document, [("step", None)])
        self.assertIn("Unsupported export format: step", str(cm.exception))

    def test_a_model_script_is_refused_by_naming_the_run(self) -> None:
        # Scripts are RUN; the engine takes the document the run wrote.
        generator = self._write_box_generator()
        with self.assertRaises(ValueError) as cm:
            step_export_target.export_cad_target(generator, [("stl", None)])
        self.assertIn("run it: python", str(cm.exception))

    def test_a_bare_door_writes_the_sibling_default(self) -> None:
        # A door reads no declarations: OUT omitted means the sibling default
        # beside the document, for an import exactly as for a generated model.
        document = self._write_box_document()
        payload = step_export_target.export_cad_target(document, [("stl", None)])
        self.assertTrue(payload["ok"])
        self.assertEqual([str(document.with_suffix(".stl"))], [entry["path"] for entry in payload["files"]])
        self._assert_export_file(document.with_suffix(".stl"), "stl")

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

    def test_mesh_exports_are_byte_deterministic(self) -> None:
        # design/unified-tessellation.md Phase 4: one deterministic code path,
        # so exporting the same model twice yields identical bytes per format.
        document = self._write_box_document()
        digests: dict[str, bytes] = {}
        for round_index in range(2):
            payload = step_export_target.export_cad_target(
                document,
                [
                    (fmt, self.out_dir / f"round{round_index}.{fmt}")
                    for fmt in step_export_target.MESH_EXPORT_FORMATS
                ],
            )
            self.assertTrue(payload["ok"])
            for entry in payload["files"]:
                data = Path(entry["path"]).read_bytes()
                if round_index == 0:
                    digests[entry["format"]] = data
                else:
                    self.assertEqual(
                        digests[entry["format"]],
                        data,
                        f"{entry['format']} export must be byte-identical across runs",
                    )

    def test_explicit_out_takes_native_path_semantics(self) -> None:
        # An explicit OUT is a one-shot ad-hoc export, never persisted, so it
        # resolves like every other cadgen path argument: relative against the
        # PROCESS cwd (not beside the document), absolute as given, ~ expanded.
        # The persisted form is the decorator declaration, which stays
        # script-anchored and is reached through spec.mesh_exports instead.
        logical_step = self.temp_root / "docs" / "box.step"
        cwd = self.temp_root / "elsewhere"
        cwd.mkdir(parents=True, exist_ok=True)
        home = self.temp_root / "home"
        home.mkdir(parents=True, exist_ok=True)

        with contextlib.chdir(cwd):
            relative = step_export_target._resolve_export_output(
                "stl", "out.stl", logical_step=logical_step
            )
            self.assertEqual(relative, (cwd / "out.stl").resolve())
            self.assertNotEqual(relative.parent, logical_step.parent)

            absolute_target = self.out_dir / "absolute.stl"
            self.assertEqual(
                step_export_target._resolve_export_output(
                    "stl", str(absolute_target), logical_step=logical_step
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
                        "stl", "~/tilde.stl", logical_step=logical_step
                    ).resolve(),
                    (home / "tilde.stl").resolve(),
                )

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

    def test_invalid_format_rejected(self) -> None:
        generator = self._write_box_generator()
        with self.assertRaises(SystemExit):
            self._run([
                "--repo-root", str(Path.cwd()),
                "--step", str(self.temp_root / "box.step"),
                "--source-path", str(generator),
                "--format", "iges",
                "--out", str(self.out_dir / "box.iges"),
            ])


if __name__ == "__main__":
    unittest.main()
