import contextlib
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/cad/scripts")

from artifact import cli

_OK_PAYLOAD = {"ok": True, "packagePath": "/abs/__cadgen__/models/sample.step"}


class ArtifactCliTests(unittest.TestCase):
    def test_requires_explicit_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main([])
        self.assertEqual(2, cm.exception.code)

    def test_imported_step_target_builds_from_step_file(self) -> None:
        with mock.patch.object(cli, "build_step_artifact", return_value=_OK_PAYLOAD) as build:
            self.assertEqual(0, cli.main(["imports/sample_part.step"]))

        build.assert_called_once()
        kwargs = build.call_args.kwargs
        self.assertEqual(Path("imports/sample_part.step"), kwargs["step"])
        self.assertIsNone(kwargs["source_path"])
        self.assertIsNone(kwargs["kind"])
        self.assertFalse(kwargs["force"])

    def test_stp_target_builds_from_step_file(self) -> None:
        with mock.patch.object(cli, "build_step_artifact", return_value=_OK_PAYLOAD) as build:
            self.assertEqual(0, cli.main(["imports/sample_part.stp"]))

        self.assertEqual(Path("imports/sample_part.stp"), build.call_args.kwargs["step"])

    def test_generator_target_selects_generator_mode(self) -> None:
        with mock.patch.object(cli, "build_step_artifact", return_value=_OK_PAYLOAD) as build:
            self.assertEqual(0, cli.main(["parts/sample.step.py"]))

        kwargs = build.call_args.kwargs
        self.assertEqual(Path("parts/sample.step"), kwargs["step"])
        self.assertEqual(Path("parts/sample.step.py"), kwargs["source_path"])

    def test_plain_python_target_maps_to_sibling_step(self) -> None:
        with mock.patch.object(cli, "build_step_artifact", return_value=_OK_PAYLOAD) as build:
            self.assertEqual(0, cli.main(["parts/sample.py"]))

        kwargs = build.call_args.kwargs
        self.assertEqual(Path("parts/sample.step"), kwargs["step"])
        self.assertEqual(Path("parts/sample.py"), kwargs["source_path"])

    def test_passes_kind_force_and_mesh_flags(self) -> None:
        with mock.patch.object(cli, "build_step_artifact", return_value=_OK_PAYLOAD) as build:
            self.assertEqual(
                0,
                cli.main(
                    [
                        "imports/sample_part.step",
                        "--kind",
                        "assembly",
                        "--force",
                        "--mesh-tolerance",
                        "0.2",
                        "--mesh-angular-tolerance",
                        "0.25",
                        "--verbose",
                    ]
                ),
            )

        kwargs = build.call_args.kwargs
        self.assertEqual("assembly", kwargs["kind"])
        self.assertTrue(kwargs["force"])
        self.assertEqual(0.2, kwargs["mesh_tolerance"])
        self.assertEqual(0.25, kwargs["mesh_angular_tolerance"])
        self.assertTrue(kwargs["verbose"])

    def test_rejects_unsupported_target_suffix(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["parts/sample.stl"])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_invalid_numeric_flag(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["imports/sample_part.step", "--mesh-tolerance", "nan"])
        self.assertEqual(2, cm.exception.code)

    def test_prints_payload_json(self) -> None:
        stream = io.StringIO()
        with mock.patch.object(cli, "build_step_artifact", return_value=_OK_PAYLOAD):
            with contextlib.redirect_stdout(stream):
                self.assertEqual(0, cli.main(["imports/sample_part.step"]))
        self.assertEqual(_OK_PAYLOAD, json.loads(stream.getvalue()))

    def test_cli_does_not_reserve_common_module_name(self) -> None:
        skill_root = repo_path("skills/cad")
        code = (
            "import sys; sys.path.insert(0, 'scripts'); import artifact.cli; "
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
