"""A library verb that needs the CAD kernel runs where the kernel is: in this process when the installation
carries it, else in the base's Python, its arguments and its outcome one JSON line each way."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
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

    def test_a_runner_that_fails_is_an_error_naming_the_verb(self):
        failed = mock.Mock(returncode=1, stdout="")
        with in_base("/nowhere/python"), mock.patch.object(kernel_verb.subprocess, "run", return_value=failed):
            with self.assertRaisesRegex(RuntimeError, r"did not run cad\.urdf\.validate \(exit code 1\)"):
                kernel_verb.in_kernel(VERB, prog=PROG)(Path("robot.urdf"))


class RunnerTest(unittest.TestCase):
    def run_main(self, argv: list[str], keywords: dict) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "stdin", io.StringIO(json.dumps(keywords))), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = kernel_run.main(argv)
        return code, out.getvalue(), err.getvalue()

    def test_the_verbs_arguments_arrive_as_their_types_and_what_it_prints_goes_to_stderr(self):
        def validate(path: Path, *, strict: bool = False) -> ValidationResult:
            print("checking")
            return ValidationResult(ok=strict and isinstance(path, Path), path=path)

        with mock.patch("cad.urdf.validate", validate):
            code, out, err = self.run_main(["cad.urdf", "validate"], {"path": "robot.urdf", "strict": True})
        self.assertEqual((code, err), (0, "checking\n"))
        self.assertEqual(json.loads(out), {"returned": {"ok": True, "path": "robot.urdf", "issues": [], "summary": ""}})

    def test_an_error_goes_out_as_its_type_and_message(self):
        def validate(path: Path) -> ValidationResult:
            raise ValueError("packages: no such folder")

        with mock.patch("cad.urdf.validate", validate):
            code, out, _ = self.run_main(["cad.urdf", "validate"], {"path": "robot.urdf"})
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), {"raised": {"module": "builtins", "type": "ValueError",
                                                      "message": "packages: no such folder"}})

    def test_it_runs_only_the_librarys_verbs(self):
        code, out, err = self.run_main(["os", "system"], {"command": "true"})
        self.assertEqual((code, out), (2, ""))
        self.assertIn("usage:", err)


if __name__ == "__main__":
    unittest.main()
