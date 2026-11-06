"""A library verb that needs the CAD kernel runs where the kernel is: in this process when the installation
carries it, else in the base's Python, its arguments and its outcome one JSON line each way."""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import SOURCE_PATH, add_repo_path

add_repo_path("packages/cad/src")

from cad._internal import kernel_run  # noqa: E402
from cad.results import ValidationIssue, ValidationResult  # noqa: E402
from cad_server._internal import base, kernel_verb  # noqa: E402

VERB = ("cad.urdf", "validate")
PROG = "cad urdf validate"


def in_base(python: str = sys.executable) -> mock._patch:
    return mock.patch.object(base, "ensure", return_value=base.Environment(python, sys.prefix, False))


class InKernelTest(unittest.TestCase):
    def test_the_command_takes_the_verbs_own_options(self):
        import cad.urdf

        verb = kernel_verb.in_kernel(VERB, prog=PROG)
        self.assertIs(verb.__wrapped__, cad.urdf.validate)
        self.assertEqual(verb.__doc__, cad.urdf.validate.__doc__)

    def test_an_installation_that_carries_the_kernel_runs_the_verb_here(self):
        found = ValidationResult(ok=True, path=Path("robot.urdf"))
        with mock.patch("cad.urdf.validate", return_value=found) as validate, \
                mock.patch.object(base, "ensure", return_value=base.Environment(sys.executable, sys.prefix, True)), \
                mock.patch.object(kernel_verb.subprocess, "run") as run:
            self.assertIs(kernel_verb.in_kernel(VERB, prog=PROG)(Path("robot.urdf")), found)
        validate.assert_called_once_with(Path("robot.urdf"))
        run.assert_not_called()

    def test_else_the_bases_python_runs_it_and_its_result_comes_back_as_its_type(self):
        with tempfile.TemporaryDirectory() as tmp, in_base(), mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}):
            missing = Path(tmp) / "missing.urdf"
            result = kernel_verb.in_kernel(VERB, prog=PROG)(missing, strict=True)
        self.assertIsInstance(result, ValidationResult)
        self.assertFalse(result.ok)
        self.assertEqual(result.path, missing.resolve())
        self.assertIsInstance(result.issues, tuple)
        self.assertIsInstance(result.issues[0], ValidationIssue)
        self.assertIn("file not found", result.issues[0].message)

    def test_a_result_keeps_its_types_paths_and_tuples(self):
        validated = ValidationResult(ok=False, path=Path("/w/robot.urdf"), summary="2 links",
                                     issues=(ValidationIssue("error", "no root", element="base", code="E1"),))
        answer = json.loads(json.dumps(kernel_run.encode(validated)))
        self.assertEqual(kernel_run.decode(ValidationResult, answer), validated)

    def test_an_error_the_verb_raises_comes_back_as_its_own(self):
        answer = mock.Mock(returncode=0, stdout=json.dumps({"raised": {"module": "builtins", "type": "ValueError",
                                                                       "message": "packages: no such folder"}}))
        with in_base("/nowhere/python"), mock.patch.object(kernel_verb.subprocess, "run", return_value=answer):
            with self.assertRaisesRegex(ValueError, r"^packages: no such folder$"):
                kernel_verb.in_kernel(VERB, prog=PROG)(Path("robot.urdf"))

    def test_an_error_this_process_cannot_make_is_a_runtime_error_naming_it(self):
        # An exception only the kernel's environment has (the server's core has no OCP).
        raised = kernel_verb.raised({"module": "kernel_only.errors", "type": "Failure",
                                     "message": "BRep_API: command not done"})
        self.assertIsInstance(raised, RuntimeError)
        self.assertEqual(str(raised), "Failure: BRep_API: command not done")

    def test_an_error_is_made_again_from_its_arguments(self):
        missing = kernel_verb.raised({"module": "builtins", "type": "FileNotFoundError", "message": "gone",
                                      "args": [2, "No such file or directory", "/w/part.step"]})
        self.assertIsInstance(missing, FileNotFoundError)
        self.assertEqual((missing.errno, missing.filename), (2, "/w/part.step"))
        self.assertEqual(str(kernel_verb.raised({"module": "builtins", "type": "KeyError", "message": "'x'",
                                                 "args": ["x"]})), "'x'")

    def test_the_kernels_traceback_comes_back_as_a_note(self):
        raised = kernel_verb.raised({"module": "builtins", "type": "ValueError", "message": "bad",
                                     "traceback": "Traceback (most recent call last):\n  ...\nValueError: bad\n"})
        self.assertEqual(raised.__notes__, ["raised in the CAD kernel's environment:\n"
                                            "Traceback (most recent call last):\n  ...\nValueError: bad"])

    def test_a_bug_in_the_library_is_reported_as_a_told_crash(self):
        frames = [{"file": "/base/cad/cam.py", "function": "plan", "line": 7}]
        answer = mock.Mock(returncode=0, stdout=json.dumps({"raised": {
            "module": "builtins", "type": "TypeError", "message": "bad", "args": ["bad"], "frames": frames}}))
        crash = {"where": "command", "type": "TypeError"}
        with in_base("/nowhere/python"), mock.patch.object(kernel_verb.subprocess, "run", return_value=answer), \
                mock.patch("cad_server.analytics.told_signature", return_value=crash) as told, \
                mock.patch("cad_server.analytics.hand_over") as hand_over:
            with self.assertRaises(TypeError):
                kernel_verb.in_kernel(VERB, prog=PROG)(Path("robot.urdf"))
        told.assert_called_once_with({"type": "TypeError", "frames": frames}, "command")
        hand_over.assert_called_once_with({"crashes": [crash]})

    def test_a_runner_that_fails_is_an_error_naming_the_verb(self):
        failed = mock.Mock(returncode=1, stdout="")
        with in_base("/nowhere/python"), mock.patch.object(kernel_verb.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, r"did not run cad\.urdf\.validate \(exit code 1\)"):
                kernel_verb.in_kernel(VERB, prog=PROG)(Path("robot.urdf"))


class RunnerTest(unittest.TestCase):
    def run_runner(self, verb: str, keywords: dict) -> subprocess.CompletedProcess:
        """The runner in a process of its own, as the base runs it, with ``cad.urdf.validate`` replaced by ``verb``."""
        program = "\n".join((
            "import os, sys", "from pathlib import Path", "import cad.urdf", "from cad.results import ValidationResult",
            "from cad._internal import kernel_run", textwrap.dedent(verb), "cad.urdf.validate = validate",
            "sys.exit(kernel_run.main(['cad.urdf', 'validate']))"))
        return subprocess.run([sys.executable, "-P", "-c", program], input=json.dumps(keywords), capture_output=True,
                              text=True, env={**os.environ, "PYTHONPATH": SOURCE_PATH}, check=False)

    def test_the_verbs_arguments_arrive_as_their_types_and_what_it_prints_goes_to_stderr(self):
        done = self.run_runner("""
            def validate(path: Path, *, strict: bool = False) -> ValidationResult:
                print("checking")
                os.write(1, b"*** ERR StepReaderData ***\\n")  # as the kernel's C++ prints, past Python's stdout
                return ValidationResult(ok=strict and isinstance(path, Path), path=path)
        """, {"path": "robot.urdf", "strict": True})
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), {"returned": {"ok": True, "path": "robot.urdf", "issues": [],
                                                                "summary": ""}})
        self.assertIn("checking", done.stderr)
        self.assertIn("*** ERR StepReaderData ***", done.stderr)

    def test_an_error_goes_out_as_its_type_arguments_frames_and_traceback(self):
        done = self.run_runner("""
            def validate(path: Path) -> ValidationResult:
                raise KeyError("x")
        """, {"path": "robot.urdf"})
        raised = json.loads(done.stdout)["raised"]
        self.assertEqual({key: raised[key] for key in ("module", "type", "message", "args")},
                         {"module": "builtins", "type": "KeyError", "message": "'x'", "args": ["x"]})
        self.assertEqual(raised["frames"][-1]["function"], "validate")
        self.assertTrue(raised["traceback"].rstrip().endswith("KeyError: 'x'"))

    def test_it_runs_only_a_cad_module(self):
        code_out_err = io.StringIO()
        with contextlib.redirect_stderr(code_out_err):
            code = kernel_run.main(["os", "system"])
        self.assertEqual(code, 2)
        self.assertIn("usage:", code_out_err.getvalue())


if __name__ == "__main__":
    unittest.main()
