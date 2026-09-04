"""The direct-run front door: `python <model>.py` (cadgen.cli._run_model).

The gen CLI is retired (library-first); a model script dispatches its own argv
through the @step/@dxf decorator into this runner. These tests pin the argv
contract and the teaching errors that route agents to the migration doc.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages", "cadgen", "src")

from cadgen.cli import _run_model as runner  # noqa: E402

STEP_MODEL = (
    "from cadgen import step\n"
    "@step\n"
    "def model():\n"
    "    return object()\n"
)
DXF_MODEL = (
    "from cadgen import dxf\n"
    "@dxf\n"
    "def drawing():\n"
    "    return {'document': object()}\n"
)


class RunModelArgvTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadrun-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()

    def _write(self, name: str, text: str) -> Path:
        path = self.root / name
        path.write_text(text, encoding="utf-8")
        return path

    def test_requires_an_existing_script(self) -> None:
        with self.assertRaises(SystemExit) as caught:
            runner.run_model_argv([str(self.root / "missing.py")])
        self.assertEqual(2, caught.exception.code)

    def test_step_models_pair_the_sibling_artifact_and_forward_flags(self) -> None:
        script = self._write("bracket.py", STEP_MODEL)
        with mock.patch("cadgen.generation.generate_step_targets", return_value=0) as generate:
            self.assertEqual(
                0,
                runner.run_model_argv([str(script), "--force", "--json"]),
            )
        generate.assert_called_once()
        self.assertEqual([str(script)], generate.call_args.args[0])
        self.assertTrue(generate.call_args.kwargs["force"])
        self.assertTrue(generate.call_args.kwargs["json_output"])
        self.assertFalse(generate.call_args.kwargs["step_options"].has_metadata)

    def test_out_kwarg_is_the_declared_output(self) -> None:
        script = self._write(
            "bracket.py",
            STEP_MODEL.replace("@step", "@step(out='exports/bracket.step')"),
        )
        with mock.patch("cadgen.generation.generate_step_targets", return_value=0) as generate:
            runner.run_model_argv([str(script)])
        self.assertEqual(
            [str(script)],
            generate.call_args.args[0],
        )

    def test_dxf_models_route_to_the_drawing_pipeline(self) -> None:
        script = self._write("plate.py", DXF_MODEL)
        with mock.patch("cadgen.generation.generate_dxf_targets", return_value=0) as generate:
            self.assertEqual(0, runner.run_model_argv([str(script), "--force"]))
        generate.assert_called_once()
        self.assertEqual([str(script)], generate.call_args.args[0])
        self.assertTrue(generate.call_args.kwargs["force"])

    def test_a_script_without_a_model_is_a_clean_error(self) -> None:
        script = self._write("plain.py", "print('not a model')\n")
        code = runner.run_model_argv([str(script)])
        self.assertEqual(1, code)

    def test_an_undecorated_function_is_simply_not_a_model(self) -> None:
        """No retired-name recognition: a plain function named anything at all
        is not a declaration, and the current-contract error says so."""
        script = self._write("old.py", "def gen_step():\n    return object()\n")
        import contextlib
        import io

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = runner.run_model_argv([str(script)])
        self.assertEqual(1, code)
        message = stderr.getvalue()
        self.assertIn("declares no CAD model", message)
        self.assertIn("@step", message)
        self.assertNotIn("migrat", message)

    def test_a_double_suffixed_filename_is_an_ordinary_model_script(self) -> None:
        """Filenames carry no special meaning: `.step.py` is just a .py file.

        The fixture returns a non-shape, so the run reaches — and fails at —
        the ORDINARY geometry contract, which is the proof that the name was
        never inspected."""
        script = self._write("old.step.py", STEP_MODEL)
        import contextlib
        import io

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            code = runner.run_model_argv([str(script)])
        self.assertEqual(1, code)
        message = stderr.getvalue()
        self.assertIn("must return a build123d Shape", message)
        self.assertNotIn("naming", message)


if __name__ == "__main__":
    unittest.main()
