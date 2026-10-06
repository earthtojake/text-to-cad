"""The cloud runner's contract (apps/cloud/runner/run.py): what a sandboxed job writes back.

Each test makes a job folder in a fresh temporary directory (request.json + workspace/),
runs the runner the way a sandbox provider does, and reads result.json and the progress
lines. The runner gives every job its own cadgen store inside the job folder.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import repo_path

RUNNER = repo_path("apps/cloud/runner/run.py")

BOX = textwrap.dedent(
    """
    from pathlib import Path

    from cadgen import build123d as bd
    from cadgen import step


    @step(out="../STEP/box.step")
    def box():
        body = bd.Box(20, 10, 5)
        body.label = "box"
        return body


    if __name__ == "__main__":
        Path(__file__).parent.joinpath("../junk.exe").write_bytes(b"not CAD")
        box()
    """
)

BAD = textwrap.dedent(
    """
    from cadgen import build123d as bd
    from cadgen import step


    @step(out="../STEP/bad.step")
    def bad():
        body = bd.Box(1, 1, 1)
        raise ValueError("this part is impossible")


    if __name__ == "__main__":
        bad()
    """
)


def run_job(request: dict, files: dict[str, str | bytes], *, timeout: float = 240) -> tuple[dict, list[dict], Path]:
    root = Path(tempfile.mkdtemp(prefix="t2c-runner-test-"))
    workspace = root / "workspace"
    workspace.mkdir()
    for name, content in files.items():
        target = workspace / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")
    (root / "request.json").write_text(json.dumps(request), encoding="utf-8")
    completed = subprocess.run(
        [sys.executable, str(RUNNER), str(root)], cwd=workspace, capture_output=True, text=True, timeout=timeout,
    )
    events = [json.loads(line) for line in completed.stdout.splitlines() if line.startswith("{")]
    result_path = root / "result.json"
    if not result_path.is_file():
        raise AssertionError(f"no result.json; stderr:\n{completed.stderr}")
    return json.loads(result_path.read_text(encoding="utf-8")), events, root


class RunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.roots: list[Path] = []

    def tearDown(self) -> None:
        import shutil

        for root in self.roots:
            shutil.rmtree(root, ignore_errors=True)

    def job(self, request: dict, files: dict, **kwargs) -> tuple[dict, list[dict], Path]:
        result, events, root = run_job(request, files, **kwargs)
        self.roots.append(root)
        return result, events, root

    def test_build_keeps_cad_outputs_and_relays_progress(self) -> None:
        result, events, root = self.job(
            {"kind": "build", "entry": ["src/box.py"], "timeoutSeconds": 240, "vcpus": 1, "thumbnail": False},
            {"src/box.py": BOX},
        )
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["outputs"], ["STEP/box.step"])
        self.assertEqual(result["dropped"], ["junk.exe"])
        self.assertEqual(result["primary"], "STEP/box.step")
        # Every collected file is described by size and digest, relative to the job folder.
        listed = {entry["path"]: entry for entry in result["files"]}
        step = listed["workspace/STEP/box.step"]
        self.assertEqual(step["bytes"], (root / "workspace/STEP/box.step").stat().st_size)
        progress = [event for event in events if event["type"] == "progress" and event.get("model")]
        self.assertTrue(progress)
        self.assertEqual({event["model"] for event in progress}, {"src/box.py"})
        self.assertIn(progress[-1]["state"], {"done", "current"})
        # The viewer export is recorded when this cadgen has it, and reported missing otherwise.
        self.assertTrue(result["export"] == "out/export" or result["exportError"] == "export unavailable", result["exportError"])
        self.assertFalse(result["flags"]["network"])

    def test_a_build_without_entries_publishes_the_files_it_was_sent(self) -> None:
        stl = "solid t\nfacet normal 0 0 1\nouter loop\nvertex 0 0 0\nvertex 1 0 0\nvertex 0 1 0\nendloop\nendfacet\nendsolid t\n"
        result, _events, _root = self.job(
            {"kind": "build", "entry": [], "timeoutSeconds": 120, "thumbnail": False},
            {"meshes/part.stl": stl, "README.md": "# part"},
        )
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual((result["outputs"], result["primary"]), ([], "meshes/part.stl"))
        self.assertFalse([step for step in result["steps"] if step["name"].startswith("python")])
        self.assertTrue(result["export"] == "out/export" or result["exportError"] == "export unavailable", result["exportError"])

    def test_the_primary_file_is_the_entry_step_then_the_shallowest_step_then_any_view(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location("cloud_runner", RUNNER)
        runner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(runner)
        self.assertEqual(runner.pick_primary(["STEP/a.step", "STEP/box.step", "box.stl"], ["src/box.py"]), "STEP/box.step")
        self.assertEqual(runner.pick_primary(["deep/er/x.step", "STEP/z.step", "a.glb"], ["src/box.py"]), "STEP/z.step")
        self.assertEqual(runner.pick_primary(["meshes/b.stl", "a.glb"], []), "a.glb")
        self.assertIsNone(runner.pick_primary([], ["src/box.py"]))

    def test_failed_model_names_its_file_and_line(self) -> None:
        result, _events, _root = self.job(
            {"kind": "build", "entry": ["src/bad.py"], "timeoutSeconds": 240, "vcpus": 1}, {"src/bad.py": BAD},
        )
        self.assertFalse(result["ok"])
        error = result["error"]
        self.assertIn("this part is impossible", error["message"])
        self.assertEqual((error["file"], error["line"], error["kind"]), ("src/bad.py", 9, "model"))
        self.assertEqual(result["outputs"], [])

    def test_symlinks_are_never_outputs(self) -> None:
        script = textwrap.dedent(
            """
            import os
            os.makedirs("data", exist_ok=True)
            open("data/notes.txt", "w").write("kept")
            os.symlink(os.path.abspath(__file__), "data/link.txt")
            """
        )
        result, _events, _root = self.job({"kind": "build", "entry": ["make.py"], "timeoutSeconds": 60}, {"make.py": script})
        self.assertTrue(result["ok"], result["error"])
        self.assertEqual(result["outputs"], ["data/notes.txt"])

    def test_inspection_returns_output_images_and_the_network_flag(self) -> None:
        code = textwrap.dedent(
            """
            import os, socket, sys
            print("hello from", os.getcwd().split(os.sep)[-1])
            os.makedirs("tmp", exist_ok=True)
            with open("tmp/view.png", "wb") as handle:
                handle.write(b"\\x89PNG\\r\\n\\x1a\\n" + bytes(16))
            sock = socket.socket()
            sys.audit("socket.connect", sock, ("192.0.2.1", 9))
            sys.audit("socket.connect", sock, ("127.0.0.1", 9))
            raise SystemExit(3)
            """
        )
        result, _events, _root = self.job({"kind": "inspect", "code": code, "timeoutSeconds": 60}, {"model.txt": "x"})
        self.assertFalse(result["ok"])
        self.assertEqual(result["exitCode"], 3)
        self.assertEqual(result["stdout"].strip(), "hello from workspace")
        self.assertEqual(result["images"], ["workspace/tmp/view.png"])
        self.assertTrue(result["flags"]["network"])

    def test_inspection_errors_point_into_the_script(self) -> None:
        result, _events, _root = self.job({"kind": "inspect", "code": "x = 1\nraise RuntimeError('nope')\n", "timeoutSeconds": 60}, {})
        self.assertEqual(result["error"]["message"], "RuntimeError: nope")
        self.assertEqual((result["error"]["file"], result["error"]["line"]), ("inspect.py", 2))

    def test_snapshot_refuses_unknown_arguments_before_running_anything(self) -> None:
        result, _events, _root = self.job(
            {"kind": "snapshot", "file": "STEP/a.step", "args": ["--job", "evil.json"], "timeoutSeconds": 60},
            {"STEP/a.step": "ISO-10303-21;"},
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["kind"], "runner")
        self.assertIn("--job", result["error"]["message"])
        self.assertEqual(result["steps"], [])

    @unittest.skipIf(os.name != "posix", "process-group kill is POSIX; sandboxes are Linux")
    def test_a_job_past_its_timeout_is_killed_and_reported(self) -> None:
        result, _events, _root = self.job(
            {"kind": "build", "entry": ["slow.py"], "timeoutSeconds": 5}, {"slow.py": "import time\ntime.sleep(120)\n"}, timeout=60,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"]["kind"], "timeout")
        self.assertEqual(result["steps"][0]["timedOut"], True)


if __name__ == "__main__":
    unittest.main()
