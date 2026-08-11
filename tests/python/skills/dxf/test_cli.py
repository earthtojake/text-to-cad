import subprocess
import sys
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("skills/dxf/scripts")

from gen import cli as gen


class DxfGenCliTests(unittest.TestCase):
    def test_requires_explicit_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            gen.main([])
        self.assertEqual(2, cm.exception.code)

    def test_passes_targets_in_order(self) -> None:
        with mock.patch.object(gen, "generate_dxf_targets", return_value=0) as generate:
            self.assertEqual(0, gen.main(["drawings/second.py", "drawings/first.py"]))

        generate.assert_called_once_with(
            ["drawings/second.py", "drawings/first.py"],
            output=None, write_dxf=False, force=False, verbose=False,
        )

    def test_passes_verbose_flag(self) -> None:
        with mock.patch.object(gen, "generate_dxf_targets", return_value=0) as generate:
            self.assertEqual(0, gen.main(["drawings/part.py", "--verbose"]))

        generate.assert_called_once_with(
            ["drawings/part.py"], output=None, write_dxf=False, force=False, verbose=True
        )

    def test_passes_output_flag(self) -> None:
        with mock.patch.object(gen, "generate_dxf_targets", return_value=0) as generate:
            self.assertEqual(0, gen.main(["drawings/part.py", "-o", "DXF/part.dxf"]))

        generate.assert_called_once_with(
            ["drawings/part.py"], output="DXF/part.dxf", write_dxf=False, force=False, verbose=False
        )

    def test_passes_write_and_force_flags(self) -> None:
        with mock.patch.object(gen, "generate_dxf_targets", return_value=0) as generate:
            self.assertEqual(0, gen.main(["drawings/part.py", "--write", "--force"]))

        generate.assert_called_once_with(
            ["drawings/part.py"], output=None, write_dxf=True, force=True, verbose=False
        )

    def test_output_flag_rejects_multiple_targets(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            gen.main(["drawings/first.py", "drawings/second.py", "-o", "DXF/first.dxf"])
        self.assertEqual(2, cm.exception.code)

    def test_scripts_gen_directory_invokes_cli(self) -> None:
        skill_root = repo_path("skills/dxf")
        result = subprocess.run(
            [sys.executable, "scripts/gen", "--help"],
            cwd=skill_root,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual("", result.stderr)
        self.assertEqual(0, result.returncode)
        self.assertIn("usage: scripts/gen", result.stdout)
        self.assertIn("--output", result.stdout)

    def test_cli_import_does_not_import_heavy_cad_modules(self) -> None:
        skill_root = repo_path("skills/dxf")
        code = (
            "import sys; sys.path.insert(0, 'scripts'); import gen.cli; "
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
        self.assertEqual(["False", "False"], result.stdout.strip().splitlines())


if __name__ == "__main__":
    unittest.main()
