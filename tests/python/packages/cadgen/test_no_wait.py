"""``python model.py --no-wait``: the command answers once every model's result is recorded
and the files are written after (STORE.md §3, *Exports*; §9).

With no daemon the result lines come before the exports and the process still writes every
file before it exits; through the daemon the client returns on the worker's release and the
worker finishes the files before its next job.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import generated_cad_directory
from tests.python.support.warm_daemon import served, warm_entries

add_repo_path("packages/cadgen/src")

from cadgen.daemon import executors  # noqa: E402

CHILD = """\
from cadgen import step
from cadgen import build123d as bd


@step
def child():
    return bd.Box(4.0, 3.0, 2.0)
"""

PARENT = """\
from cadgen import step
from cadgen import build123d as bd
from child import child


@step
def parent():
    return bd.Compound(children=[bd.Pos(8, 0, 0) * child(), bd.Box(2, 2, 2)], label="parent")


if __name__ == "__main__":
    parent()
"""


class NoWait(unittest.TestCase):
    def setUp(self):
        temporary = generated_cad_directory(prefix="no-wait-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        (self.root / "child.py").write_text(CHILD, encoding="utf-8")
        self.parent = self.root / "parent.py"
        self.parent.write_text(PARENT, encoding="utf-8")
        self.store = self.root / "store"

    def test_the_flag_is_forwarded_as_the_user_typed_it(self):
        from cadgen.cli._run_model import check_user_flags

        self.assertEqual(check_user_flags(["--json", "--no-wait"], prog="python parent.py", called="parent"),
                         ["--json", "--no-wait"])

    def test_with_no_daemon_the_result_comes_before_the_files_and_the_files_still_come(self):
        from cadgen.cli._run_model import run_model_argv

        events: list[dict] = []
        executors.set_event_sink(events.append)
        self.addCleanup(executors.set_event_sink, None)
        released: list[int] = []
        executors.set_release_sink(released.append)
        self.addCleanup(executors.set_release_sink, None)

        class Stdout(io.StringIO):
            def write(self, text):
                if text.startswith('{"ok":'):
                    saved_first.append(len([e for e in events if e.get("saved")]))
                return super().write(text)

        saved_first: list[int] = []
        out, err = Stdout(), io.StringIO()
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store), "CADGEN_DAEMON": "0"}), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = run_model_argv([str(self.parent), "--json", "--no-wait"])
        self.assertEqual(code, 0, err.getvalue())
        self.assertEqual(saved_first, [0], "the result line came before any file was written")
        self.assertEqual(released, [0], "the caller was released once, with the command's code")
        self.assertEqual(len([e for e in events if e.get("saved")]), 2, "both files were written before the process returned")
        for name in ("child", "parent"):
            self.assertTrue((self.root / f"{name}.step").is_file(), name)

    def test_through_the_daemon_the_client_returns_on_its_release_and_the_worker_writes_the_files(self):
        from cadgen.store.records import read_record

        env = {**os.environ, **warm_entries(), "CADGEN_CACHE_DIR": str(self.store),
               "PYTHONPATH": os.pathsep.join(filter(None, [str(REPO_ROOT / "packages" / "cadgen" / "src"),
                                                           os.environ.get("PYTHONPATH", "")]))}
        env.pop("CADGEN_DAEMON_CHILD", None)
        completed = subprocess.run([sys.executable, "parent.py", "--json", "--no-wait"], cwd=str(self.root), env=env,
                                   capture_output=True, text=True, timeout=600)
        self.assertEqual(completed.returncode, 0, completed.stderr[-3000:])
        (line,) = [line for line in completed.stdout.splitlines() if line.startswith('{"ok":')]
        self.assertEqual(json.loads(line)["outcome"], "built")
        # The worker finishes the files after the client has gone: await its job's end.
        deadline = time.monotonic() + 300
        while not served(self.root.name):
            self.assertLess(time.monotonic(), deadline, "the worker never finished the job it released its client from")
            time.sleep(0.2)
        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store)}):
            for name in ("child", "parent"):
                step = self.root / f"{name}.step"
                self.assertTrue(step.is_file(), name)
                record = read_record(self.root / f"{name}.py")
                self.assertEqual(record["outputs"][str(step)]["sha256"], hashlib.sha256(step.read_bytes()).hexdigest(), name)


if __name__ == "__main__":
    unittest.main()
