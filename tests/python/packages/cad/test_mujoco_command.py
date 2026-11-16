"""``cad run mujoco-studio`` runs ``cad.mujoco._command``: Studio's own command line, the environment's own
script beside its Python, its arguments as given with our two defaults put first where they name neither
(``--gfx=web``, ``--hot_reload=model``), and one line on stderr before Studio's web viewer starts saying it
listens on every interface (MuJoCo 4.0 binds ``::`` with no host to choose). Nothing is launched: the child
is a recorder."""

from __future__ import annotations

import io
import os
import shutil
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

from cad.mujoco import _command  # noqa: E402
from cad.registry import INTEGRATIONS  # noqa: E402


class ArgumentsTest(unittest.TestCase):
    def test_the_defaults_come_first_where_the_arguments_name_neither(self) -> None:
        self.assertEqual(_command.arguments(["--model", "scene.xml"]),
                         ["--gfx=web", "--hot_reload=model", "--model", "scene.xml"])
        self.assertEqual(_command.arguments(["scene.xml"]), ["--gfx=web", "--hot_reload=model", "scene.xml"])

    def test_an_option_the_arguments_name_is_theirs_either_spelling(self) -> None:
        for given in (["--gfx", "vulkan", "s.xml"], ["--gfx=vulkan", "s.xml"]):
            with self.subTest(given=given):
                self.assertEqual(_command.arguments(given), ["--hot_reload=model", *given])
        self.assertEqual(_command.arguments(["--hot_reload=", "--gfx=web", "s.xml"]), ["--hot_reload=", "--gfx=web", "s.xml"])
        # After ``--`` an argument is the model's name, never an option.
        self.assertEqual(_command.arguments(["--", "--gfx=x.xml"]), ["--gfx=web", "--hot_reload=model", "--", "--gfx=x.xml"])


class MainTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="mujoco-command-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)
        (self.folder / "bin").mkdir()
        self.python = self.folder / "bin" / "python"
        self.python.write_text("", encoding="utf-8")
        patch = mock.patch.object(_command.sys, "executable", str(self.python))
        patch.start()
        self.addCleanup(patch.stop)

    def run_(self, *argv: str, script: bool = True) -> tuple[int, str, list]:
        if script:
            (self.folder / "bin" / "mujoco-studio").write_text("", encoding="utf-8")
        child = mock.Mock()
        child.wait.return_value = 3
        err = io.StringIO()
        with mock.patch.object(_command.subprocess, "Popen", return_value=child) as popen, redirect_stderr(err):
            code = _command.main(list(argv))
        return code, err.getvalue(), [call.args[0] for call in popen.call_args_list]

    def test_the_environments_own_script_runs_with_the_arguments_and_its_exit_code_is_the_runs(self) -> None:
        with mock.patch.dict(os.environ, {"PATH": str(self.folder / "elsewhere")}):
            code, err, calls = self.run_("mujoco-studio", "--model", "scene.xml", "--port", "8123")
        script = str(self.folder / "bin" / "mujoco-studio")
        self.assertEqual(calls, [[script, "--gfx=web", "--hot_reload=model", "--model", "scene.xml", "--port", "8123"]])
        self.assertEqual(code, 3, "Studio's exit code is the run's")
        self.assertEqual(_command.program(), Path(script), "the script beside this Python, never one on PATH")

    def test_the_web_viewer_says_first_it_listens_on_every_interface_and_another_does_not(self) -> None:
        _code, err, _calls = self.run_("mujoco-studio", "scene.xml")
        self.assertEqual(err.strip(), _command.EXPOSED)
        self.assertIn("every network interface", err)
        for argv in (("mujoco-studio", "--gfx", "vulkan", "scene.xml"), ("mujoco-studio", "--help")):
            with self.subTest(argv=argv):
                self.assertEqual(self.run_(*argv)[1], "", "no web viewer, nothing said")

    def test_an_environment_without_the_script_says_so_and_runs_nothing(self) -> None:
        code, err, calls = self.run_("mujoco-studio", "scene.xml", script=False)
        self.assertEqual((code, calls), (2, []))
        self.assertIn("cad[mujoco]", err)


class RegistryTest(unittest.TestCase):
    def test_the_integration_declares_the_command_its_extra_installs(self) -> None:
        mujoco = INTEGRATIONS["mujoco"]
        self.assertEqual(mujoco.commands, ("mujoco-studio",))
        self.assertIn("mujoco-studio", mujoco.distributions)
        self.assertIn("mujoco-studio", mujoco.identity)
        from cad._internal.integrations import INTEGRATIONS as REGISTERED, for_command

        self.assertEqual((for_command("mujoco-studio"), for_command("mujoco-studio.exe")), ("mujoco", "mujoco"))
        self.assertEqual(REGISTERED["mujoco"].runner, "cad.mujoco._command")


if __name__ == "__main__":
    unittest.main()
