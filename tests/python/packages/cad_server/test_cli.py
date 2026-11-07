"""The ``cad`` console-script dispatcher.

The behaviour worth pinning is not the argument parsing — each subcommand owns that — but
the dispatch contract: every registered command resolves to a real ``main(argv)``, and
getting to the help text or an error never imports the CAD stack.
"""

import contextlib
import importlib
import io
import json
import subprocess
import sys
import unittest

from cad_server import cli

HEAVY = ("OCP", "build123d", "ezdxf", "shapely")


class Registry(unittest.TestCase):
    def test_every_registered_command_resolves_to_a_callable_main(self):
        self.assertTrue(cli._COMMANDS, "the registry must not be empty")
        for name, (module_name, help_text) in cli._COMMANDS.items():
            with self.subTest(command=name):
                module = importlib.import_module(module_name)
                self.assertTrue(
                    callable(getattr(module, "main", None)),
                    f"{module_name} must expose a callable main() for 'cad {name}'",
                )
                self.assertTrue(help_text.strip(), f"{name} needs help text")

    def test_the_viewer_verbs_are_registered_and_lazy(self):
        # The CAD Viewer's backend is cad_server.viewer, reached through the front
        # door as a launcher for the shared engine. Registered by dotted module
        # name like everything else, so `cad --help` imports none of it.
        for name in ("viewer",):
            self.assertIn(name, cli._COMMANDS)
            module_name, _ = cli._COMMANDS[name]
            self.assertTrue(module_name.startswith("cad_server.cli.viewer"), module_name)


class Dispatch(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_no_args_prints_usage_and_succeeds(self):
        code, out, _ = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("usage: cad", out)
        self.assertIn("snapshot", out)

    def test_help_flags_print_usage(self):
        for flag in ("-h", "--help", "help"):
            with self.subTest(flag=flag):
                code, out, _ = self._run([flag])
                self.assertEqual(code, 0)
                self.assertIn("usage: cad", out)

    def test_version_flag_reports_the_distribution_version(self):
        from cad_server import __version__

        from unittest import mock

        from cad_server._internal import installations

        with mock.patch.dict("os.environ", {installations.NAME_ENV: ""}), \
                mock.patch.object(installations, "editable", return_value=False):
            code, out, _ = self._run(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), f"cad {__version__}")

    def test_version_flag_names_a_development_installation_by_its_own_version(self):
        # Two installations are told apart: a dev install says its stamped name, as doctor's header does.
        from unittest import mock

        from cad_server._internal import installations

        with mock.patch.dict("os.environ", {installations.NAME_ENV: "0.8.0-dev.20261025032350"}):
            code, out, _ = self._run(["--version"])
        self.assertEqual((code, out.strip()), (0, "cad 0.8.0-dev.20261025032350"))

    def test_doctor_adopts_the_earlier_state_folder_before_its_notice_writes_this_one(self):
        # `doctor` registers, as `setup` does (which says no notice); any other command adopts nothing. Help
        # does neither, and an answer in JSON says no notice.
        from unittest import mock

        from cad.engine import places

        for argv, expected in ((["doctor"], ["adopt", "tell"]), (["status"], ["tell"]), (["doctor", "--help"], []),
                               (["status", "-h"], []), (["help", "doctor"], []), (["xbf", "export", "--help"], []),
                               (["xbf", "help"], []), (["status", "--json"], []), (["run", "a.py", "--help"], [])):
            with self.subTest(argv=argv):
                calls = []
                with mock.patch.object(places, "adopt_earlier", side_effect=lambda: calls.append("adopt") or []), \
                        mock.patch.object(cli, "_tell", side_effect=lambda: calls.append("tell")), \
                        mock.patch.object(cli, "_run", return_value=0):
                    self.assertEqual(self._run(argv)[0], 0)
                self.assertEqual(calls, expected)

    def test_help_leaves_the_state_folder_as_it_was(self):
        """Help, at any depth and by any of its three spellings, writes nothing -- no notice, no settings --
        and says nothing but the help; an answer in JSON says no notice either. A person's run (the last) is
        told, so the notice is live here and the state folder is where it would land."""
        import os
        import tempfile

        from tests.python.support.paths import add_sources

        with tempfile.TemporaryDirectory() as folder:
            state = os.path.join(folder, "state")
            env = {key: value for key, value in os.environ.items()
                   if key not in ("CI", "DO_NOT_TRACK", "CAD_TELEMETRY", "CAD_TELEMETRY_NOTICE")}
            env.update({"PYTHONPATH": str(add_sources()), "CAD_STATE_DIR": state,
                        "CAD_CACHE_DIR": os.path.join(folder, "cache"), "CAD_ENGINE_DIR": os.path.join(folder, "e"),
                        "CAD_LAUNCHER_DIR": os.path.join(folder, "bin"),
                        "CAD_INSTALL_CHANNEL": "test"})  # a plugin's channel: a checkout's tells no one

            def run(*argv):
                return subprocess.run([sys.executable, "-m", "cad_server.cli", *argv], cwd=folder, env=env,
                                      capture_output=True, text=True, timeout=120)

            for argv in (["doctor", "--help"], ["help", "doctor"], ["status", "-h"], ["xbf", "export", "--help"],
                         ["help", "step"], ["status", "--json"]):
                with self.subTest(argv=argv):
                    done = run(*argv)
                    self.assertEqual((done.returncode, done.stderr), (0, ""))
                    self.assertFalse(os.path.exists(state), os.listdir(state) if os.path.exists(state) else None)
            done = run("status")
            self.assertEqual(done.returncode, 0, done.stderr)
            self.assertIn("text-to-cad now sends usage stats", done.stderr)
            self.assertTrue(os.path.isfile(os.path.join(state, "settings.json")))

    def test_status_names_the_engine_s_installation(self):
        from cad_server.engine.cli import status_text

        text = status_text({"pid": 7, "up": 5, "workers": [], "installation": "0.8.0-dev.20261025032350"})
        self.assertTrue(text.startswith("engine server 7 (cad-server 0.8.0-dev.20261025032350), up "), text)

    def test_status_says_a_worker_s_retirement_by_its_script_and_a_render_process_s_by_its_document(self):
        import time

        from cad_server.engine.cli import status_text

        now = time.time()
        text = status_text({"pid": 7, "up": 5, "workers": [], "retired": [
            {"document": "/w/part.xbf", "pid": 9, "requests": 3, "reason": "RSS", "at": now},
            {"script": "/w/tube.py", "pid": 8, "builds": 2, "reason": "LRU", "at": now}]})
        self.assertRegex(text, r"retired: part\.xbf's renderer \(RSS\) \d+s ago · tube\.py \(LRU\) \d+s ago")

    def test_unknown_command_exits_two_and_names_it_on_stderr(self):
        # Named, with where the commands are listed: never the whole usage.
        code, out, err = self._run(["nope"])
        self.assertEqual((code, out), (2, ""))
        self.assertEqual(err, "cad: unknown command 'nope'; 'cad --help' lists the commands\n")
        # At most one suggestion, never run; under --json the same failure as the contract's one document.
        code, out, err = self._run(["stats", "--json"])
        self.assertEqual((code, err), (2, ""))
        self.assertEqual(json.loads(out), {"ok": False, "reason": "usage", "error": "unknown command 'stats' (did you "
                                           "mean 'status'?); 'cad --help' lists the commands"})

    def test_subcommand_argv_is_forwarded_untouched(self):
        """The dispatcher must not consume or reorder a subcommand's own flags."""
        seen = {}

        class FakeModule:
            @staticmethod
            def main(argv):
                seen["argv"] = argv
                return 7

        original = cli.importlib.import_module
        cli.importlib.import_module = lambda name: FakeModule
        self.addCleanup(setattr, cli.importlib, "import_module", original)
        code, _, _ = self._run(["doctor", "--port", "3245", "--", "-x"])
        self.assertEqual(code, 7)
        self.assertEqual(seen["argv"], ["--port", "3245", "--", "-x"])


class LazyImports(unittest.TestCase):
    """Help and error paths must stay cheap.

    Run in a subprocess: the CAD stack is almost certainly already imported in this test
    process, so an in-process check would pass no matter what the dispatcher does.
    """

    def _heavy_after(self, argv):
        code = (
            "import sys;"
            "from cad_server import cli;"
            f"cli.main({argv!r});"
            # A sentinel prefix, because the usage text itself lands on stdout too.
            f"print('HEAVY:' + ','.join(m for m in {HEAVY!r} if m in sys.modules))"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        marked = [ln for ln in proc.stdout.splitlines() if ln.startswith("HEAVY:")]
        self.assertEqual(len(marked), 1, proc.stdout)
        return marked[0][len("HEAVY:"):]

    def test_help_does_not_import_the_cad_stack(self):
        self.assertEqual(self._heavy_after(["--help"]), "")

    def test_unknown_command_does_not_import_the_cad_stack(self):
        self.assertEqual(self._heavy_after(["nope"]), "")


if __name__ == "__main__":
    unittest.main()
