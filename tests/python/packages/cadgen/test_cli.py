"""The ``cadgen`` console-script dispatcher.

The behaviour worth pinning is not the argument parsing — each subcommand owns that — but
the dispatch contract: every registered command resolves to a real ``main(argv)``, and
getting to the help text or an error never imports the CAD stack.
"""

import contextlib
import importlib
import io
import subprocess
import sys
import unittest

from cadgen import cli

HEAVY = ("OCP", "build123d", "ezdxf", "shapely")


class Registry(unittest.TestCase):
    def test_every_registered_command_resolves_to_a_callable_main(self):
        self.assertTrue(cli._COMMANDS, "the registry must not be empty")
        for name, (module_name, help_text) in cli._COMMANDS.items():
            with self.subTest(command=name):
                module = importlib.import_module(module_name)
                self.assertTrue(
                    callable(getattr(module, "main", None)),
                    f"{module_name} must expose a callable main() for 'cadgen {name}'",
                )
                self.assertTrue(help_text.strip(), f"{name} needs help text")

    def test_the_viewer_verbs_are_registered_and_lazy(self):
        # The CAD Viewer's backend is cadgen.viewer, reached through the front
        # door as one serve verb plus the two manager verbs. Registered by dotted
        # module name like everything else, so `cadgen --help` imports none of it.
        for name in ("viewer", "viewer list", "viewer stop"):
            self.assertIn(name, cli._COMMANDS)
            module_name, _ = cli._COMMANDS[name]
            self.assertTrue(module_name.startswith("cadgen.cli.viewer"), module_name)


class Dispatch(unittest.TestCase):
    def _run(self, argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_no_args_prints_usage_and_succeeds(self):
        code, out, _ = self._run([])
        self.assertEqual(code, 0)
        self.assertIn("usage: cadgen", out)
        self.assertIn("snapshot", out)

    def test_help_flags_print_usage(self):
        for flag in ("-h", "--help", "help"):
            with self.subTest(flag=flag):
                code, out, _ = self._run([flag])
                self.assertEqual(code, 0)
                self.assertIn("usage: cadgen", out)

    def test_version_flag_reports_the_distribution_version(self):
        from cadgen import __version__

        code, out, _ = self._run(["--version"])
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), f"cadgen {__version__}")

    def test_unknown_command_exits_two_and_names_it_on_stderr(self):
        code, _, err = self._run(["nope"])
        self.assertEqual(code, 2)
        self.assertIn("nope", err)
        self.assertIn("usage: cadgen", err)

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
        code, _, _ = self._run(["snapshot", "--port", "3245", "--", "-x"])
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
            "from cadgen import cli;"
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
