import contextlib
import io
import subprocess
import sys
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/cad/scripts")

from gen import cli


class GenCliTests(unittest.TestCase):
    def test_requires_explicit_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main([])
        self.assertEqual(2, cm.exception.code)

    def test_passes_targets_in_order(self) -> None:
        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            self.assertEqual(0, cli.main(["parts/second.step.py", "parts/first.step.py"]))

        generate.assert_called_once()
        self.assertEqual(["parts/second.step.py", "parts/first.step.py"], generate.call_args.args[0])
        self.assertFalse(generate.call_args.kwargs["step_options"].has_metadata)
        self.assertFalse(generate.call_args.kwargs["force"])
        self.assertFalse(generate.call_args.kwargs["verbose"])

    def test_json_is_off_by_default_and_forwarded_when_asked(self) -> None:
        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            cli.main(["parts/sample.step.py"])
        self.assertFalse(generate.call_args.kwargs["json_output"])

        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            cli.main(["parts/sample.step.py", "--json"])
        self.assertTrue(generate.call_args.kwargs["json_output"])

    def test_a_generator_failure_is_reported_not_tracebacked(self) -> None:
        # An uncaught generator exception used to reach the interpreter and print ~60
        # lines of runtime frames. The CLI is the boundary that turns it into a report.
        boom = ValueError("bad radius")
        stderr = io.StringIO()
        with mock.patch.object(cli, "generate_step_targets", side_effect=boom):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(1, cli.main(["parts/sample.step.py"]))
        self.assertIn("FAILED: ValueError: bad radius", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())

    def test_verbose_still_gets_the_full_traceback(self) -> None:
        stderr = io.StringIO()
        with mock.patch.object(cli, "generate_step_targets", side_effect=ValueError("bad radius")):
            with contextlib.redirect_stderr(stderr):
                self.assertEqual(1, cli.main(["parts/sample.step.py", "--verbose"]))
        self.assertIn("Traceback", stderr.getvalue())

    def test_passes_force_and_verbose_flags(self) -> None:
        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            self.assertEqual(0, cli.main(["parts/sample.step.py", "--force", "--verbose"]))

        self.assertTrue(generate.call_args.kwargs["force"])
        self.assertTrue(generate.call_args.kwargs["verbose"])

    def test_passes_mesh_tolerances(self) -> None:
        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            self.assertEqual(
                0,
                cli.main(
                    [
                        "parts/sample.step.py",
                        "--mesh-tolerance",
                        "0.2",
                        "--mesh-angular-tolerance",
                        "0.25",
                    ]
                ),
            )

        options = generate.call_args.kwargs["step_options"]
        self.assertEqual(0.2, options.mesh_tolerance)
        self.assertEqual(0.25, options.mesh_angular_tolerance)

    def test_write_defaults_to_sibling_outputs_per_target(self) -> None:
        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            self.assertEqual(
                0, cli.main(["parts/first.step.py", "parts/second.py", "--write"])
            )

        self.assertEqual(
            ["parts/first.step.py=parts/first.step", "parts/second.py=parts/second.step"],
            generate.call_args.args[0],
        )

    def test_write_with_explicit_path_single_target(self) -> None:
        with mock.patch.object(cli, "generate_step_targets", return_value=0) as generate:
            self.assertEqual(
                0, cli.main(["parts/sample.step.py", "--write", "out/custom.step"])
            )

        self.assertEqual(["parts/sample.step.py=out/custom.step"], generate.call_args.args[0])

    def test_write_with_explicit_path_rejects_multiple_targets(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(stream):
            cli.main(["parts/first.step.py", "parts/second.step.py", "--write", "out/custom.step"])
        self.assertEqual(2, cm.exception.code)
        self.assertIn("exactly one target", stream.getvalue())

    def test_rejects_direct_step_target(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(stream):
            cli.main(["imports/sample_part.step"])
        self.assertEqual(2, cm.exception.code)
        self.assertIn("scripts/export", stream.getvalue())

    def test_rejects_direct_stp_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["imports/sample_part.stp"])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_source_output_pairs(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stderr(stream):
            cli.main(["parts/sample.step.py=out/sample.step"])
        self.assertEqual(2, cm.exception.code)
        self.assertIn("scripts/export", stream.getvalue())

    def test_rejects_non_python_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["parts/sample.stl"])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_removed_export_flags(self) -> None:
        for flag_args in (
            ["--stl", "out/sample.stl"],
            ["--3mf", "out/sample.3mf"],
            ["--glb", "out/sample.glb"],
            ["--step", "out/sample.step"],
            ["-o", "out/sample.step"],
            ["--output", "out/sample.step"],
            ["--kind", "part"],
        ):
            with self.subTest(flag=flag_args[0]), self.assertRaises(SystemExit) as cm:
                cli.main(["parts/sample.step.py", *flag_args])
            self.assertEqual(2, cm.exception.code)

    def test_rejects_invalid_numeric_flag(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["parts/sample.step.py", "--mesh-tolerance", "nan"])
        self.assertEqual(2, cm.exception.code)

    def test_help_has_current_gen_flags_only(self) -> None:
        stream = io.StringIO()
        with self.assertRaises(SystemExit) as cm, contextlib.redirect_stdout(stream):
            cli.main(["--help"])
        self.assertEqual(0, cm.exception.code)
        help_text = stream.getvalue()
        self.assertIn("--force", help_text)
        self.assertIn("--write", help_text)
        self.assertIn("--mesh-tolerance", help_text)
        self.assertIn("--mesh-angular-tolerance", help_text)
        self.assertIn("--verbose", help_text)
        self.assertNotIn("--kind", help_text)
        self.assertNotIn("--stl", help_text)
        self.assertNotIn("--3mf", help_text)
        self.assertNotIn("--glb", help_text)
        self.assertNotIn("--output", help_text)

    def test_cli_does_not_reserve_common_module_name(self) -> None:
        skill_root = repo_path("skills/cad")
        code = (
            "import sys; sys.path.insert(0, 'scripts'); import gen.cli; "
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
