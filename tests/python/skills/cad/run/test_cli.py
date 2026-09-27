"""The direct-run front door: `python <model>.py` (cadgen.cli._run_model).

The gen CLI is retired (library-first); a model script dispatches its own argv
through the @step/@dxf decorator into this runner. These tests pin the argv
contract and the teaching errors that route agents to the migration doc.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
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


TWO_MODELS = (
    "from cadgen import step\n"
    "@step\n"
    "def left():\n"
    "    raise AssertionError('left() must not be built')\n"
    "@step\n"
    "def right():\n"
    "    raise AssertionError('right() must not be built')\n"
    "if __name__ == '__main__':\n"
    "    left()\n"
)


class TheUsersFlagsEndInTheirOwnProcess(unittest.TestCase):
    """`--help` and a usage error are answered by the process the user started,
    BEFORE any handoff -- so they behave the same warm and cold. Handed to the
    daemon, `--help` came back as a job that exited 0 having built nothing, and the
    wait for its source result raised a traceback (exit 1)."""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cadrun-")
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        # A private WARM endpoint nobody is listening on: reaching the client
        # would start a daemon here, and the key file it writes is the evidence.
        self._state = tempfile.TemporaryDirectory(prefix="cgr-", dir=None if os.name == "nt" else "/tmp")
        self.addCleanup(self._state.cleanup)
        self.state = Path(self._state.name)

    def _run(self, script: Path, *flags: str) -> subprocess.CompletedProcess:
        src = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
        env = dict(os.environ)
        env.pop("CADGEN_DAEMON_CHILD", None)
        env.update({
            "CADGEN_DAEMON": "1",
            "CADGEN_DAEMON_STATE_DIR": str(self.state),
            "CADGEN_DAEMON_SOCKET": (
                rf"\\.\pipe\cadgen-run-{os.getpid()}" if os.name == "nt" else str(self.state / "d.sock")
            ),
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "PYTHONPATH": os.pathsep.join(filter(None, [str(src), env.get("PYTHONPATH", "")])),
        })
        return subprocess.run(
            [sys.executable, str(script), *flags], cwd=str(self.root), env=env,
            capture_output=True, text=True, timeout=120,
        )

    def _no_daemon_was_started(self) -> bool:
        return not any(name.endswith(".key") for name in os.listdir(self.state))

    def test_help_exits_zero_on_the_warm_path_without_a_handoff(self) -> None:
        script = self.root / "pair.py"
        script.write_text(TWO_MODELS, encoding="utf-8")
        proc = self._run(script, "--help")
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("usage: python pair.py", proc.stdout)
        self.assertTrue(self._no_daemon_was_started(), "--help was handed to the daemon")

    def test_help_shows_the_users_flags_and_nothing_internal(self) -> None:
        script = self.root / "pair.py"
        script.write_text(TWO_MODELS, encoding="utf-8")
        text = self._run(script, "--help").stdout
        usage = text.split("\n\n", 1)[0]
        # The script is how the user got here, never something they pass; --model
        # is the pipeline's routing flag.
        self.assertNotIn("script", usage)
        self.assertNotIn("--model", text)
        # Two different values get two different names, and every flag says what it does.
        self.assertIn("--mesh-tolerance CHORD", text)
        self.assertIn("--mesh-angular-tolerance RADIANS", text)
        self.assertIn("RELATIVE", text)
        for flag in ("--force", "--verbose", "--json"):
            line = next(line for line in text.splitlines() if line.strip().startswith(flag))
            self.assertGreater(len(line.split(None, 1)), 1, f"{flag} has no help text")

    def test_naming_a_model_main_does_not_call_is_a_teaching_error_not_a_build(self) -> None:
        script = self.root / "pair.py"
        script.write_text(TWO_MODELS, encoding="utf-8")
        proc = self._run(script, "--model", "right")
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertNotIn("Traceback", proc.stderr)
        self.assertIn("--model is cadgen's internal routing flag", proc.stderr)
        self.assertIn("call right() in __main__", proc.stderr)
        self.assertTrue(self._no_daemon_was_started(), "the wrong model was handed off to be built")
        self.assertEqual([], sorted(path.name for path in self.root.glob("*.step")))

    def test_an_unknown_flag_is_a_usage_error_before_any_handoff(self) -> None:
        script = self.root / "pair.py"
        script.write_text(TWO_MODELS, encoding="utf-8")
        proc = self._run(script, "--write", "elsewhere.step")
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("unrecognized arguments", proc.stderr)
        self.assertTrue(self._no_daemon_was_started())

    def test_an_absolute_looking_mesh_tolerance_is_refused_before_any_handoff(self) -> None:
        script = self.root / "pair.py"
        script.write_text(TWO_MODELS, encoding="utf-8")
        proc = self._run(script, "--mesh-tolerance", "1")
        self.assertEqual(2, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("RELATIVE", proc.stderr)
        self.assertIn("at most 0.05", proc.stderr)
        self.assertTrue(self._no_daemon_was_started())

    def test_a_declaration_failure_under_json_is_the_doors_envelope(self) -> None:
        script = self.root / "bad.py"
        script.write_text(
            "from cadgen import step\n@step(out=5)\ndef model():\n    return None\n"
            "if __name__ == '__main__':\n    model()\n",
            encoding="utf-8",
        )
        proc = self._run(script, "--json")
        self.assertEqual(1, proc.returncode, proc.stdout + proc.stderr)
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual({"ok", "error"}, set(payload))
        self.assertFalse(payload["ok"])
        self.assertIn("out= must be a non-empty path string", payload["error"])


class TheFailureEnvelope(unittest.TestCase):
    """ONE failure envelope: `python model.py --json` answers a failure exactly as
    a generated door does -- `{"ok": false, "error": ...}` on stdout, exit 1."""

    def test_a_model_run_and_a_door_print_the_same_envelope(self) -> None:
        from cadgen.cli import stl_build

        with tempfile.TemporaryDirectory(prefix="cadrun-") as raw:
            root = Path(raw).resolve()
            script = root / "plain.py"
            script.write_text("print('not a model')\n", encoding="utf-8")
            run_out, door_out = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(run_out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, runner.run_model_argv([str(script), "--json"]))
            with contextlib.redirect_stdout(door_out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(1, stl_build.main([str(root / "missing.step"), "--json"]))
        run_payload = json.loads(run_out.getvalue().strip().splitlines()[-1])
        door_payload = json.loads(door_out.getvalue().strip().splitlines()[-1])
        self.assertEqual({"ok", "error"}, set(run_payload))
        self.assertEqual(set(door_payload), set(run_payload))
        self.assertFalse(run_payload["ok"])
        self.assertIn("declares no CAD model", run_payload["error"])

    def test_without_json_the_failure_stays_on_stderr(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadrun-") as raw:
            script = Path(raw).resolve() / "plain.py"
            script.write_text("print('not a model')\n", encoding="utf-8")
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                self.assertEqual(1, runner.run_model_argv([str(script)]))
        self.assertEqual("", out.getvalue())
        self.assertIn("FAILED: ValueError: plain.py declares no CAD model", err.getvalue())


if __name__ == "__main__":
    unittest.main()
