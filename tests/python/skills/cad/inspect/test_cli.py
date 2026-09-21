"""Retired inspect entry points fail immediately with migration guidance."""
import contextlib
import io
import subprocess
import sys
import unittest
from unittest import mock


class RemovedInspectTests(unittest.TestCase):
    def test_every_old_command_fails_without_routing_to_the_daemon(self):
        from cadgen import cli
        for verb in ("refs", "diff", "frame", "measure", "align", "interfere", "validate", "--help"):
            with self.subTest(verb=verb), contextlib.redirect_stderr(io.StringIO()) as err, mock.patch.object(cli, "_run_via_daemon") as daemon:
                self.assertEqual(cli.main(["step", "inspect", verb, "part.step"]), 2)
                self.assertIn("removed", err.getvalue())
                self.assertIn("read_scene", err.getvalue())
                daemon.assert_not_called()

    def test_module_entry_points_fail_without_loading_the_kernel(self):
        for module in ("cadgen.cli.step_inspect", "cadgen.cli.step_inspect.cli"):
            code = f'''
import runpy, sys
class NoKernel:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {{'OCP', 'build123d'}}:
            raise AssertionError('retired command imported kernel')
sys.meta_path.insert(0, NoKernel())
runpy.run_module({module!r}, run_name='__main__')
'''
            result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            self.assertIn("read_scene", result.stderr)
            self.assertEqual(result.stdout, "")

    def test_retired_imports_name_the_replacement(self):
        for statement in (
            "from cadgen import load_step_scene",
            "from cadgen.step import inspect",
            "from cadgen.step_scene import scene_occurrence_shape",
        ):
            with self.subTest(statement=statement), self.assertRaisesRegex(ImportError, "read_scene"):
                exec(statement, {})

    def test_retired_diagnostic_modules_fail_without_loading_the_kernel(self):
        for module, replacement in (
            ("cadgen.interference", "overlap_volume"),
            ("cadgen.validity", "topology_errors"),
        ):
            with self.subTest(module=module):
                code = f'''
import importlib, sys
class NoKernel:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {{'OCP', 'build123d'}}:
            raise AssertionError('retired diagnostic imported kernel')
sys.meta_path.insert(0, NoKernel())
try:
    importlib.import_module({module!r})
except ImportError as error:
    assert 'removed' in str(error), str(error)
    assert 'cadgen.geometry' in str(error), str(error)
    assert {replacement!r} in str(error), str(error)
else:
    raise AssertionError('retired diagnostic import succeeded')
'''
                result = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_python_api_is_removed_and_help_does_not_advertise_it(self):
        import cadgen
        from cadgen import cli, step
        with self.assertRaisesRegex(ImportError, "read_scene"):
            step.inspect
        with self.assertRaisesRegex(ImportError, "read_scene"):
            cadgen.load_step_scene
        self.assertNotIn("step inspect", cli._usage())
