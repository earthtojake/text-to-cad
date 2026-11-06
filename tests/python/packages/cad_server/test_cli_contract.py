"""The ``cad`` command's one failure contract, and the one parser every command reads its options by.

A failure's class sets its exit status, the same with ``--json`` and without: 2 for the command line and
its input, 1 for the work, 130 for an interrupt. Under ``--json`` every failure is ONE JSON document on
stdout -- ``{"ok": false, "error", "reason"}`` -- and nothing else is written there, with no traceback; the
skills read it. Every parser is the factory's (``cad_server._internal.cli_parser``): no abbreviation of an
option is read, and a mistake gets at most one suggestion.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_sources

SRC = add_sources()

from cad_server import cli  # noqa: E402
from cad_server._internal.cli_errors import REASONS, Failure, classify, document  # noqa: E402
from cad_server._internal.cli_parser import Parser, parser  # noqa: E402

PACKAGE = Path(cli.__file__).resolve().parents[1]


def _parse(made: Parser, argv: list[str]) -> tuple[object, str, str]:
    """``made.parse_args(argv)``: what it read, or the status it exited with; its stdout; its stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            found: object = made.parse_args(argv)
        except SystemExit as exited:
            found = exited.code
    return found, out.getvalue(), err.getvalue()


def _sample(**options) -> Parser:
    made = parser("cad sample", **options)
    made.add_argument("source")
    made.add_argument("--json", action="store_true")
    made.add_argument("--prune", action="store_true")
    return made


class TheReasons(unittest.TestCase):
    def test_each_reason_has_one_class(self) -> None:
        # The table an agent branches on: a reason is added, never renamed, and its class sets the status.
        self.assertEqual(REASONS, {"usage": 2, "invalid_argument": 2, "wrong_type": 2, "not_found": 2,
                                   "engine_unavailable": 1, "failed": 1, "internal_error": 1, "canceled": 130})
        with self.assertRaises(ValueError):
            Failure("words", "no_such_reason")

    def test_an_exception_is_classified_by_its_class(self) -> None:
        class NotHeld(ValueError):
            pass

        NotHeld.__module__ = "cad.engine.serve"
        cases = {ConnectionError("no engine"): ("engine_unavailable", 1), NotHeld("not held"): ("not_found", 2),
                 KeyboardInterrupt(): ("canceled", 130), RuntimeError("boom"): ("failed", 1),
                 Failure("refused", "wrong_type"): ("wrong_type", 2)}
        for error, (reason, status) in cases.items():
            with self.subTest(error=type(error).__name__):
                found = classify(error)
                self.assertEqual((found.reason, found.status), (reason, status))

    def test_the_document_carries_what_a_person_must_do(self) -> None:
        self.assertEqual(document(Failure("asked", "usage", next=["cad status --json"], user_action=True)),
                         {"ok": False, "error": "asked", "reason": "usage", "userActionRequired": True,
                          "next": ["cad status --json"]})
        self.assertEqual(document(Failure("boom")), {"ok": False, "error": "boom", "reason": "failed"})


class TheParser(unittest.TestCase):
    def test_no_abbreviation_is_read_and_one_option_is_suggested(self) -> None:
        for given, meant in (("--js", "--json"), ("--p", "--prune"), ("--jsno", "--json")):
            with self.subTest(given=given):
                found, out, err = _parse(_sample(), ["a.step", given])
                self.assertEqual((found, out), (2, ""))
                self.assertTrue(err.endswith(f"cad sample: error: unrecognized arguments: {given} (did you mean "
                                             f"{meant}?)\n"), err)

    def test_a_choice_it_does_not_take_gets_the_closest(self) -> None:
        made = parser("cad sample")
        made.add_argument("--mode", choices=("solid", "shaded"))
        found, _out, err = _parse(made, ["--mode", "solidd"])
        self.assertEqual(found, 2)
        self.assertIn("invalid choice: 'solidd', maybe you meant 'solid'?", err)

    def test_a_usage_error_under_json_is_one_document_on_stdout(self) -> None:
        found, out, err = _parse(_sample(), ["--json"])
        self.assertEqual((found, err), (2, ""))
        self.assertEqual(json.loads(out), {"ok": False, "error": "the following arguments are required: source",
                                           "reason": "usage"})
        found, out, err = _parse(_sample(), [])
        self.assertEqual((found, out), (2, ""))
        self.assertTrue(err.startswith("usage: cad sample") and err.endswith(
            "cad sample: error: the following arguments are required: source\n"), err)

    def test_a_check_s_failure_is_the_command_line_s_with_its_status(self) -> None:
        def check(parsed) -> None:
            raise Failure(f"{parsed.source} is a glb, not a stl", "wrong_type")

        found, out, err = _parse(_sample(checks=[check]), ["part.glb"])
        self.assertEqual((found, out, err), (2, "", "cad sample: part.glb is a glb, not a stl\n"))
        found, out, err = _parse(_sample(checks=[check]), ["part.glb", "--json"])
        self.assertEqual((found, err), (2, ""))
        self.assertEqual(json.loads(out)["reason"], "wrong_type")

    def test_every_parser_of_the_command_is_the_factory_s(self) -> None:
        # No module of the server makes an argparse parser of its own: each is the factory's subclass.
        made = [path.relative_to(PACKAGE).as_posix() for path in sorted(PACKAGE.rglob("*.py"))
                if "_runtime" not in path.relative_to(PACKAGE).parts  # the bundled plugin: skills, not the server
                and re.search(r"\bArgumentParser\(", path.read_text(encoding="utf-8"))]
        self.assertEqual(made, [])
        for name in ("status", "delete", "xbf export", "sdf validate", "kicad_pcb inspect", "setup", "telemetry"):
            with self.subTest(command=name):
                found = cli.build_parser_for(name)
                self.assertIsInstance(found, Parser)
                self.assertFalse(found.allow_abbrev)


class TheDispatcher(unittest.TestCase):
    def _run(self, argv: list[str]) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_a_crash_under_json_is_its_document_and_no_traceback(self) -> None:
        with mock.patch.object(cli, "_run_module", side_effect=RuntimeError("boom")), \
                mock.patch.object(cli, "_report"), mock.patch.object(cli, "_tell"):
            code, out, err = self._run(["status", "--json"])
            self.assertEqual((code, err), (1, ""))
            self.assertEqual(json.loads(out), {"ok": False, "error": "RuntimeError: boom", "reason": "internal_error"})
            with self.assertRaises(RuntimeError):  # without --json, its traceback the person's
                self._run(["status"])

    def test_an_interrupt_is_canceled_with_the_shell_s_status(self) -> None:
        with mock.patch.object(cli, "_main", side_effect=KeyboardInterrupt):
            self.assertEqual(self._run(["status"]), (130, "", "cad: canceled\n"))
            code, out, _err = self._run(["status", "--json"])
            self.assertEqual((code, json.loads(out)["reason"]), (130, "canceled"))


class EndToEnd(unittest.TestCase):
    """The ``cad`` command run as a process: a refusal's document and its status, under ``--json``."""

    def test_a_json_failure_is_one_document_on_stdout_with_its_class_s_status(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            env = {**os.environ, "PYTHONPATH": str(SRC), "CAD_STATE_DIR": os.path.join(folder, "state"),
                   "CAD_CACHE_DIR": os.path.join(folder, "cache"), "CAD_ENGINE_DIR": os.path.join(folder, "engine")}
            for argv, reason in ((["stl", "snapshot", "part.glb", "out.png", "--json"], "wrong_type"),
                                 (["xbf", "export", "--json"], "usage"), (["stats", "--json"], "usage")):
                with self.subTest(argv=argv):
                    done = subprocess.run([sys.executable, "-m", "cad_server.cli", *argv], cwd=folder, env=env,
                                          capture_output=True, text=True, timeout=120)
                    self.assertEqual(done.returncode, 2, done.stderr)
                    lines = done.stdout.splitlines()
                    self.assertEqual(len(lines), 1, done.stdout)
                    found = json.loads(lines[0])
                    self.assertEqual((found["ok"], found["reason"]), (False, reason))
                    self.assertNotIn("Traceback", done.stderr)


if __name__ == "__main__":
    unittest.main()
