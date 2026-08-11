import contextlib
import io
import subprocess
import sys
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/cad/scripts")

from export import cli

_OK_PAYLOAD = {"ok": True, "files": [{"format": "stl", "path": "/abs/sample.stl"}]}


class ExportCliTests(unittest.TestCase):
    def test_requires_explicit_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main([])
        self.assertEqual(2, cm.exception.code)

    def test_requires_at_least_one_format(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(stream):
            cli.main(["parts/sample.step.py"])
        self.assertEqual(2, cm.exception.code)
        self.assertIn("at least one export format", stream.getvalue())

    def test_rejects_multiple_targets(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["parts/first.step.py", "parts/second.step.py", "--stl"])
        self.assertEqual(2, cm.exception.code)

    def test_bare_format_flags_request_default_sibling_outputs(self) -> None:
        with mock.patch.object(cli, "export_cad_target", return_value=_OK_PAYLOAD) as export:
            self.assertEqual(0, cli.main(["parts/sample.step.py", "--stl", "--3mf", "--glb"]))

        export.assert_called_once()
        self.assertEqual("parts/sample.step.py", export.call_args.args[0])
        self.assertEqual(
            [("stl", None), ("3mf", None), ("glb", None)],
            export.call_args.args[1],
        )
        self.assertFalse(export.call_args.kwargs["verbose"])

    def test_rejects_step_export(self) -> None:
        # A .step file is written by `scripts/gen --write-step`, never by export.
        with self.assertRaises(SystemExit) as cm:
            cli.main(["parts/sample.step.py", "--step"])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_kind_override(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["imports/sample_part.step", "--stl", "--kind", "assembly"])
        self.assertEqual(2, cm.exception.code)

    def test_explicit_output_paths_pass_through(self) -> None:
        with mock.patch.object(cli, "export_cad_target", return_value=_OK_PAYLOAD) as export:
            self.assertEqual(
                0,
                cli.main(
                    [
                        "imports/sample_part.step",
                        "--stl",
                        "meshes/sample_part.stl",
                        "--3mf",
                        "meshes/sample_part.3mf",
                        "--glb",
                        "meshes/sample_part.glb",
                    ]
                ),
            )

        self.assertEqual(
            [
                ("stl", "meshes/sample_part.stl"),
                ("3mf", "meshes/sample_part.3mf"),
                ("glb", "meshes/sample_part.glb"),
            ],
            export.call_args.args[1],
        )

    def test_passes_mesh_tolerances_and_verbose(self) -> None:
        with mock.patch.object(cli, "export_cad_target", return_value=_OK_PAYLOAD) as export:
            self.assertEqual(
                0,
                cli.main(
                    [
                        "parts/sample.step.py",
                        "--stl",
                        "--mesh-tolerance",
                        "0.2",
                        "--mesh-angular-tolerance",
                        "0.25",
                        "--verbose",
                    ]
                ),
            )

        self.assertEqual(0.2, export.call_args.kwargs["mesh_tolerance"])
        self.assertEqual(0.25, export.call_args.kwargs["mesh_angular_tolerance"])
        self.assertTrue(export.call_args.kwargs["verbose"])

    def test_rejects_invalid_numeric_flag(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["parts/sample.step.py", "--stl", "--mesh-tolerance", "nan"])
        self.assertEqual(2, cm.exception.code)

    def test_value_error_from_export_is_a_usage_error(self) -> None:
        stream = io.StringIO()
        with mock.patch.object(
            cli, "export_cad_target", side_effect=ValueError("--stl output must end with .stl")
        ):
            with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(stream):
                cli.main(["parts/sample.step.py", "--stl", "meshes/sample.bin"])
        self.assertEqual(2, cm.exception.code)
        self.assertIn("--stl output must end with .stl", stream.getvalue())

    def test_prints_written_files(self) -> None:
        stream = io.StringIO()
        with mock.patch.object(cli, "export_cad_target", return_value=_OK_PAYLOAD):
            with contextlib.redirect_stdout(stream):
                self.assertEqual(0, cli.main(["parts/sample.step.py", "--stl"]))
        self.assertIn("wrote STL: /abs/sample.stl", stream.getvalue())

    def test_help_has_current_export_flags(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(stream):
            cli.main(["--help"])
        self.assertEqual(0, cm.exception.code)
        help_text = stream.getvalue()
        self.assertIn("--stl", help_text)
        self.assertIn("--3mf", help_text)
        self.assertIn("--glb", help_text)
        self.assertIn("--mesh-tolerance", help_text)
        self.assertIn("--verbose", help_text)
        self.assertNotIn("--kind", help_text)
        self.assertNotIn("--output", help_text)
        self.assertNotIn("--force", help_text)

    def test_cli_does_not_reserve_common_module_name(self) -> None:
        skill_root = repo_path("skills/cad")
        code = (
            "import sys; sys.path.insert(0, 'scripts'); import export.cli; "
            "print('common' in sys.modules); "
            "print('OCP.OCP' in sys.modules); "
            "print('cadgen._internal.step_scene' in sys.modules)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=skill_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertEqual(["False", "False", "False"], result.stdout.strip().splitlines())


if __name__ == "__main__":
    unittest.main()
