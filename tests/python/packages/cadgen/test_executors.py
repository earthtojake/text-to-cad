"""The transient executor: a real subprocess per job, events back as lines.

``CADGEN_DAEMON=0`` is the path tests and CI run, so it is tested with real workers on a
real (temporary) store. What it must do: build into the store the caller's environment
names, report the model's transitions back through the event sink tagged with the root
id, capture a failed child's output for the error, and never block the caller until
``wait()``.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen.daemon import executors  # noqa: E402

PART = """\
from cadgen import step
from cadgen import build123d as bd


@step
def {name}():
    return bd.Box({size}, 4.0, 2.0)


if __name__ == "__main__":
    {name}()
"""

BROKEN = """\
from cadgen import step


@step
def broken():
    raise ValueError("the body is wrong on purpose")


if __name__ == "__main__":
    broken()
"""


class TransientExecutor(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_directory(prefix="cadgen-executors-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = self.root / "store"
        self.state = self.root / "state"
        env = {"CADGEN_DAEMON": "0", "CADGEN_CACHE_DIR": str(self.store), "CADGEN_DAEMON_STATE_DIR": str(self.state)}
        patcher = mock.patch.dict(os.environ, env)
        patcher.start()
        self.addCleanup(patcher.stop)
        os.environ.pop("CADGEN_ROOT_ID", None)
        os.environ.pop("CADGEN_DAEMON_CHILD", None)
        self.events: list[dict] = []
        executors.set_event_sink(self.events.append)
        self.addCleanup(executors.set_event_sink, None)

    def _model(self, name: str, source: str) -> Path:
        path = self.root / f"{name}.py"
        path.write_text(source, encoding="utf-8")
        return path

    def test_a_job_builds_into_the_store_the_environment_names(self):
        model = self._model("plate", PART.format(name="plate", size=10.0))
        job = executors.submit(model, root_id="root-1")
        self.assertFalse(job.done, "submit must return before the build finishes")
        self.assertEqual(job.wait(timeout=300), 0, job.output())
        from cadgen.store.records import read_record

        record = read_record(model)
        self.assertIsNotNone(record, "the record did not land in CADGEN_CACHE_DIR's store")
        self.assertTrue(record["tree"])
        self.assertTrue((self.store / "index" / "model").is_dir())
        self.assertTrue((self.root / "plate.step").is_file())

    def test_events_come_back_tagged_with_the_root_id_and_the_parent(self):
        model = self._model("bar", PART.format(name="bar", size=6.0))
        job = executors.submit(model, root_id="root-7", parent=Path("/models/parent.py"))
        self.assertEqual(job.wait(timeout=300), 0, job.output())
        states = [(e["model"], e["state"]) for e in self.events]
        self.assertEqual(states[0], (str(model), "submitted"))
        self.assertEqual(self.events[0]["parent"], "/models/parent.py")
        self.assertIn((str(model), "building"), states)
        self.assertEqual(states[-1], (str(model), "done"))
        roots = {e.get("root") for e in self.events[1:]}
        self.assertEqual(roots, {"root-7"}, "a child's events were not tagged with the root's id")
        # The child's own stderr is captured for the error path, never mixed into events.
        self.assertNotIn("CADGEN_EVENT", job.output())

    def test_a_failed_job_reports_failed_and_keeps_its_output(self):
        model = self._model("broken", BROKEN)
        job = executors.submit(model, root_id="root-2")
        self.assertNotEqual(job.wait(timeout=300), 0)
        self.assertIn("FAILED", job.output())
        self.assertIn("broken.py", job.output())
        self.assertEqual(self.events[-1]["state"], "failed")
        self.assertEqual(self.events[-1]["model"], str(model))

    def test_a_store_root_argument_overrides_the_environment(self):
        other = self.root / "other-store"
        model = self._model("disc", PART.format(name="disc", size=3.0))
        job = executors.submit(model, store_root=other, root_id="root-3")
        self.assertEqual(job.wait(timeout=300), 0, job.output())
        self.assertTrue((other / "index" / "model").is_dir(), "the job built into the wrong store")
        self.assertFalse((self.store / "index" / "model").exists())

    def test_use_daemon_is_false_when_opted_out(self):
        self.assertFalse(executors.use_daemon())

    def test_an_event_line_round_trips(self):
        line = executors.EVENT_LINE_PREFIX + '{"model": "/m/a.py", "state": "done"}\n'
        self.assertEqual(executors._event_line(line), {"model": "/m/a.py", "state": "done"})
        self.assertIsNone(executors._event_line("plain stderr chatter\n"))
        self.assertIsNone(executors._event_line(executors.EVENT_LINE_PREFIX + "not json\n"))


if __name__ == "__main__":
    unittest.main()
