"""``cad step cam`` and ``cad xbf cam`` are the library's operation, run where the kernel is: in the command's own
process when its environment holds it, else by the library's runner of one operation (``cad._internal.operation``)
in the installation's base. Here this Python stands in for the base, so the runner's real subprocess reads the part,
and what comes back is the result the operation returned, as its own type; a job's options are refused before any
environment is made. A plan through the same path needs FreeCAD, as every plan here does."""

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

from tests.python.support.cam_fixtures import block_step, class_directory, mill_job, needs_freecad
from tests.python.support.paths import SOURCE_PATH

from cad.results import CamResult  # noqa: E402
from cad_server._internal import base, integration_env  # noqa: E402
from cad_server.cli import step  # noqa: E402


@contextlib.contextmanager
def elsewhere(made: list):
    """The command's environment lacking the kernel, and this Python the one made for it."""

    def environment(integration, told, **_):
        made.append(integration)
        return sys.executable

    with mock.patch.object(integration_env, "carries", return_value=False), \
            mock.patch.object(integration_env, "environment", side_effect=environment), \
            mock.patch.dict(os.environ, {"PYTHONPATH": SOURCE_PATH}):
        yield


def run(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = step.main(argv)
    return code, out.getvalue(), err.getvalue()


class CamElsewhereTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.step = block_step(class_directory(cls))

    def test_what_a_job_can_name_comes_back_through_the_runner_as_its_type(self):
        made: list = []
        with elsewhere(made):
            code, out, _ = run(["cam", str(self.step), "--json"])
        self.assertEqual(code, 0, out)
        self.assertEqual(made, ["build123d"])       # the kernel's environment, the installation's base
        result = CamResult.from_data(json.loads(out.strip().splitlines()[-1]))
        self.assertEqual([80.0, 60.0, 25.0], result.measurements["bbox_mm"]["size"])
        self.assertEqual(4, len(result.holes))
        self.assertEqual((), result.written)
        self.assertTrue(result.human_lines()[0].endswith("80 x 60 x 25 mm"), result.human_lines())

    def test_a_part_that_cannot_be_read_is_a_failed_result_with_its_words(self):
        with tempfile.TemporaryDirectory() as tmp, elsewhere([]):
            broken = Path(tmp) / "broken.step"
            broken.write_text("not a step file", encoding="utf-8")
            code, out, _ = run(["cam", str(broken), "--json"])
        self.assertEqual(code, 1)
        payload = json.loads(out.strip().splitlines()[-1])
        self.assertFalse(payload["ok"])
        (finding,) = payload["findings"]
        self.assertEqual(("error", "job"), (finding["severity"], finding["code"]))
        self.assertIn("broken.step", finding["message"])

    def test_a_plans_options_are_refused_before_any_environment_is_made(self):
        made: list = []
        for argv, said in ((["--out", "r.glb"], "--out is a plan's"),
                           (["--job", "{}"], "give --out RESULT.cam.glb"),
                           (["--job", "{}", "--out", "r.stl"], "must end in .glb")):
            with self.subTest(argv=argv), elsewhere(made):
                code, _, err = run(["cam", str(self.step), *argv])
                self.assertEqual(code, 2)
                self.assertIn(said, err)
        self.assertEqual(made, [])

    @needs_freecad
    def test_a_plan_comes_back_through_the_runner_with_the_files_it_wrote(self):
        with tempfile.TemporaryDirectory() as tmp, elsewhere([]):
            out_glb = Path(tmp) / "CAM" / "block.cam.glb"
            job = json.dumps(mill_job([{"op": "face", "tool": "T1"}]))
            code, out, _ = run(["cam", str(self.step), "--job", job, "--out", str(out_glb), "--json"])
            self.assertEqual(code, 0, out)
            result = CamResult.from_data(json.loads(out.strip().splitlines()[-1]))
            self.assertEqual(out_glb.resolve(), result.glb)
            self.assertTrue(all(path.is_file() for path in result.written), result.written)
            self.assertEqual(out_glb.parent.resolve(), result.written[1].parent)
            self.assertEqual("ready", result.measurements["verdict"]["status"])

    def test_where_the_kernel_is_here_out_names_a_file_that_is_not_there_yet(self):
        written = self.step.with_name("new.cam.glb")
        with mock.patch.object(integration_env, "carries", return_value=True):
            code, out, err = run(["cam", str(self.step), "--job", '{"nope": 1}', "--out", str(written)])
        self.assertEqual(code, 1, err)               # the job's refusal, not a missing file's
        self.assertNotIn("not_found", out + err)
        self.assertIn("not planned", out + err)
        self.assertFalse(written.exists())


class TheEnvironment(unittest.TestCase):
    def test_the_kernels_environment_is_the_installations_base(self):
        environment = base.Environment(sys.executable, sys.prefix, False)
        with mock.patch.object(base, "ensure", return_value=environment) as ensure:
            self.assertEqual(sys.executable, integration_env.environment("build123d", lambda line: None))
        ensure.assert_called_once()

    def test_a_library_call_with_no_kernel_says_which_extra_brings_it(self):
        import cad.step

        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch("cad._internal.cam.part.read_part", side_effect=ModuleNotFoundError("no", name="OCP")):
            part = Path(tmp) / "part.step"
            part.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(ModuleNotFoundError, r"cad\[build123d\]"):
                cad.step.cam(part)


if __name__ == "__main__":
    unittest.main()
