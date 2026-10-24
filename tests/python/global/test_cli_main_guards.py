"""Every `python -m`-invokable cadgen CLI module must actually run when invoked.

A module that defines a top-level ``main()`` but has no ``__main__`` guard
exits 0 silently under ``python -m`` — the caller gets a success code and no
work (this shipped once: ``cadgen.cli.step_snapshot`` was documented as a
module entrypoint and did nothing). The guard is one line and easy to forget,
so it is policy-checked here rather than re-reviewed each time.

The second check below is the same idea one level up: every command in the
dispatch registry must ANSWER ``--help``.
"""

from __future__ import annotations

import contextlib
import io
import re
import unittest
from pathlib import Path

from cadgen.cli import _COMMANDS
from cadgen.cli import main as dispatch

ROOT = Path(__file__).resolve().parents[3]
CLI_DIR = ROOT / "packages" / "cadgen" / "src" / "cadgen" / "cli"

MAIN_DEF = re.compile(r"^def main\(", re.MULTILINE)
GUARD = re.compile(r"^if __name__ == \"__main__\":", re.MULTILINE)


class CliMainGuardTest(unittest.TestCase):
    def test_every_cli_module_with_a_main_has_the_module_guard(self) -> None:
        missing: list[str] = []
        checked = 0
        for path in sorted(CLI_DIR.rglob("*.py")):
            if path.name == "__main__.py":  # executed directly by -m on the package
                continue
            text = path.read_text(encoding="utf-8")
            if not MAIN_DEF.search(text):
                continue
            checked += 1
            # cli/__init__.py is dispatched through cli/__main__.py, which owns
            # the guard for the package form (`python -m cadgen.cli`).
            if path.name == "__init__.py":
                continue
            if not GUARD.search(text):
                missing.append(str(path.relative_to(ROOT)))
        self.assertGreater(checked, 5, "audit walked no CLI modules — wrong path?")
        self.assertEqual(
            missing,
            [],
            "CLI modules with a main() but no __main__ guard (silent no-op under "
            f"python -m): {missing}",
        )


class RegisteredCommandsAnswerHelpTest(unittest.TestCase):
    """``cadgen <command> --help`` prints help on stdout and exits 0. Every one.

    This is the contract scripts/test/test-installed.sh walks the registry to
    check, and `cadgen server --help` broke it: the server refuses arguments so
    a stray one cannot leave a resident server behind, and --help was swept up
    with the typos -- usage on STDERR, exit 2. Nothing in the suite noticed,
    because the only check ran at the end of the installed-mode pipeline.
    """

    def test_every_registered_command_answers_help(self) -> None:
        failures: list[str] = []
        for command in sorted(_COMMANDS):
            out, err = io.StringIO(), io.StringIO()
            try:
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    code = dispatch([*command.split(), "--help"])
            except SystemExit as exit_:  # argparse's own --help path
                code = exit_.code or 0
            if code != 0:
                failures.append(f"cadgen {command} --help exited {code}: {err.getvalue().strip()[:120]}")
            elif not out.getvalue().strip():
                failures.append(f"cadgen {command} --help printed nothing to stdout")
        self.assertGreater(len(_COMMANDS), 5, "audit walked no commands — empty registry?")
        self.assertEqual(failures, [], "\n".join(failures))


if __name__ == "__main__":
    unittest.main()
