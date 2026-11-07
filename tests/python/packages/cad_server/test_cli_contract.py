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


def _cad(argv: list[str]) -> tuple[object, str, str]:
    """``cad ARGV`` run in this process (``cli.main``): its exit status -- a command line its parser refuses
    exits, as argparse's do --, its stdout and its stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code: object = cli.main(argv)
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


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
                                   "confirmation_required": 2, "declined": 1, "engine_unavailable": 1, "failed": 1,
                                   "internal_error": 1, "canceled": 130})
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


class Consent(unittest.TestCase):
    """A command that destroys asks a person at a terminal, and where no one can be asked does nothing without
    --yes, naming the command with it (``cad_server._internal.consent``)."""

    def test_a_yes_a_question_or_the_command_that_says_yes(self) -> None:
        from cad_server._internal import consent

        self.assertEqual(consent.retry("cad delete", ["a b", "--yes", "--json"]), "cad delete 'a b' --json --yes")
        consent.confirm("deleting 1 document", "Delete it?", yes=True, as_json=True, command="unused")
        with mock.patch.object(consent, "interactive", return_value=False), self.assertRaises(Failure) as asked:
            consent.confirm("deleting 1 document", "Delete it?", yes=False, as_json=False, command="cad delete X --yes")
        self.assertEqual(document(asked.exception), {
            "ok": False, "reason": "confirmation_required", "userActionRequired": True, "next": ["cad delete X --yes"],
            "error": "deleting 1 document needs a yes, and no one can be asked here (no terminal, or --json): nothing "
                     "was changed; `cad delete X --yes` says yes"})
        for answer, goes_on in (("y\n", True), ("YES\n", True), ("n\n", False), ("\n", False), ("", False)):
            with self.subTest(answer=answer), mock.patch.object(consent, "interactive", return_value=True), \
                    mock.patch.object(sys, "stdin", io.StringIO(answer)), contextlib.redirect_stderr(io.StringIO()) as err:
                try:
                    consent.confirm("deleting 1 document", "Delete it?", yes=False, as_json=False, command="x",
                                    preview=["the plan"])
                    went = True
                except Failure as failure:
                    self.assertEqual((failure.reason, failure.status), ("declined", 1))
                    went = False
                self.assertEqual(went, goes_on)
                self.assertEqual(err.getvalue(), "the plan\nDelete it? (y/N) ")

    def test_no_one_is_asked_under_json_or_in_ci(self) -> None:
        from cad_server._internal import consent

        class Terminal(io.StringIO):
            def isatty(self) -> bool:
                return True

        with mock.patch.object(sys, "stdin", Terminal()), mock.patch.object(sys, "stderr", Terminal()):
            with mock.patch.dict(os.environ, {"CI": ""}):
                self.assertTrue(consent.interactive())
                self.assertFalse(consent.interactive(as_json=True))
            with mock.patch.dict(os.environ, {"CI": "true"}):
                self.assertFalse(consent.interactive())


class TheDispatcher(unittest.TestCase):
    def test_a_crash_under_json_is_its_document_and_no_traceback(self) -> None:
        with mock.patch.object(cli, "_run_module", side_effect=RuntimeError("boom")), \
                mock.patch.object(cli, "_report"), mock.patch.object(cli, "_tell"):
            code, out, err = _cad(["status", "--json"])
            self.assertEqual((code, err), (1, ""))
            self.assertEqual(json.loads(out), {"ok": False, "error": "RuntimeError: boom", "reason": "internal_error"})
            with self.assertRaises(RuntimeError):  # without --json, its traceback the person's
                _cad(["status"])

    def test_a_failure_s_words_are_on_stderr_and_stdout_keeps_the_answers(self) -> None:
        # A choice that could not be kept is the work's failure (exit 1), said on stderr as every command's is.
        from cad_server import analytics, auto_updates

        with mock.patch.object(analytics, "choose", return_value={"saved": False}), mock.patch.object(cli, "_tell"):
            code, out, err = _cad(["telemetry", "on"])
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("cad telemetry: could not save the choice: the state directory ("), err)
        with mock.patch.object(auto_updates, "change", side_effect=PermissionError(13, "Permission denied")), \
                mock.patch.object(cli, "_tell"):
            code, out, err = _cad(["update", "auto", "off"])
        self.assertEqual((code, out), (1, ""))
        self.assertTrue(err.startswith("cad update auto: could not save the choice: ") and
                        err.endswith("(Permission denied). Automatic updates are unchanged.\n"), err)

    def test_an_interrupt_is_canceled_with_the_shell_s_status(self) -> None:
        with mock.patch.object(cli, "_main", side_effect=KeyboardInterrupt):
            self.assertEqual(_cad(["status"]), (130, "", "cad: canceled\n"))
            code, out, _err = _cad(["status", "--json"])
            self.assertEqual((code, json.loads(out)["reason"]), (130, "canceled"))


class MissingInputs(unittest.TestCase):
    """A file the command line names that is not there is its mistake whichever option names it, as the
    operation's own file is: exit 2, ``not_found``, said before anything runs or renders."""

    def test_a_file_an_option_names_that_is_not_there(self) -> None:
        from cad.engine.snapshot import NoSuchFile, SnapshotRefused

        refused = NoSuchFile("--job gone.json: no such file")
        self.assertIsInstance(refused, SnapshotRefused)  # still the snapshot's refusal for its callers
        self.assertEqual((classify(refused).reason, classify(refused).status), ("not_found", 2))
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "robot.srdf").write_text('<robot name="r"/>\n', encoding="utf-8")
            (root / "part.stl").write_text("solid t\nendsolid t\n", encoding="utf-8")
            (root / "board.kicad_sch").write_text("(kicad_sch (version 20231120))\n", encoding="utf-8")
            gone, out = str(root / "gone.json"), str(root / "out.png")
            for argv, said in (
                    (["srdf", "validate", str(root / "robot.srdf"), "--urdf", str(root / "gone.urdf")],
                     f"--urdf {root / 'gone.urdf'}: no such file"),
                    (["stl", "snapshot", str(root / "part.stl"), out, "--annotation", gone], f"--annotation {gone}: no such file"),
                    (["stl", "snapshot", "--job", gone], f"--job {gone}: no such file"),
                    (["kicad_sch", "snapshot", str(root / "board.kicad_sch"), out, "--sheet", "/", "--display", gone],
                     f"--display {gone}: no such file")):
                with self.subTest(argv=argv[:2]), mock.patch.object(cli, "_tell"):
                    code, stdout, stderr = _cad([*argv, "--json"])
                    self.assertEqual((code, stderr), (2, ""))
                    self.assertEqual(json.loads(stdout), {"ok": False, "error": said, "reason": "not_found"})
            self.assertFalse(os.path.exists(out), "nothing was drawn")
            code, stdout, _ = _cad(["kicad_sch", "snapshot", str(root / "board.kicad_sch"), out, "--border", "--display",
                                    "{not json", "--json"])
            self.assertEqual((code, json.loads(stdout)["reason"]), (2, "invalid_argument"))


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
