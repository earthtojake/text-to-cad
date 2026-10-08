"""A ready spare has loaded the kernel and resolved the identities every saved
build stamps; importing its supervisor has done neither."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import unittest


class WorkerPrewarm(unittest.TestCase):
    def test_kernel_and_identities_are_ready_before_ready_but_not_at_namespace_import(self):
        # A fresh interpreter prevents this suite's earlier geometry tests from
        # making a parser-only prewarm appear to have loaded the kernel.
        program = textwrap.dedent("""
            import sys
            from cadgen.daemon import worker
            assert "build123d" not in sys.modules
            assert "OCP.BRep" not in sys.modules
            import cadgen
            from cadgen.store import surfaces
            resolved = set()
            real_kernel, real_version = surfaces.kernel_versions, cadgen._resolve_version
            surfaces.kernel_versions = lambda: (resolved.add("kernel"), real_kernel())[1]
            cadgen._resolve_version = lambda: (resolved.add("cadgen"), real_version())[1]
            original_emit = worker._emit
            def checked_emit(frame):
                if "ready" in frame:
                    assert "build123d" in sys.modules, "ready before build123d import"
                    assert "OCP.BRep" in sys.modules, "ready before kernel import"
                    assert resolved == {"kernel", "cadgen"}, f"ready before the writer identities: {resolved}"
                original_emit(frame)
            worker._emit = checked_emit
            raise SystemExit(worker.serve())
        """)
        completed = subprocess.run(
            [sys.executable, "-c", program], input="", text=True,
            capture_output=True, timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        frames = [json.loads(line) for line in completed.stdout.splitlines() if line]
        self.assertEqual(len(frames), 1, frames)
        self.assertGreater(frames[0]["ready"], 0)


class WorkerScratchSweep(unittest.TestCase):
    """A starting worker removes what killed processes left in the temp folder -- served
    views, exported views, trace logs -- and never a live process's
    (``cadgen._internal.temp_leftovers``)."""

    def test_the_sweep_takes_dead_and_old_scratch_only(self):
        import os
        import tempfile
        import time
        from pathlib import Path

        from cadgen._internal import temp_leftovers

        exited = subprocess.Popen([sys.executable, "-c", "pass"])
        exited.wait()
        dead, live = exited.pid, os.getpid()
        with tempfile.TemporaryDirectory(prefix="scratch-sweep-") as tmp:
            root = Path(tmp)

            def folder(name):
                path = root / name
                path.mkdir(parents=True)
                (path / "assembly.json").write_text("{}", encoding="utf-8")
                return path

            def file(name):
                path = root / name
                path.write_text("log", encoding="utf-8")
                return path

            gone = [folder(f"cadgen-views/{dead}"), folder(f"cadgen-view-{dead}-ab12cd34"),
                    file(f"cadgen-trace-{dead}-ab12cd34.log"),
                    folder("cadgen-view-o1dname_"), file("cadgen-trace-o1dname_.log"),
                    # A folder an earlier sweep condemned and was killed deleting.
                    folder(f"cadgen-swept-{dead}-cadgen-view-o1dname2")]
            kept = [folder(f"cadgen-views/{live}"), folder("cadgen-views/not-a-pid"),
                    folder(f"cadgen-view-{live}-ef56gh78"), file(f"cadgen-trace-{live}-ef56gh78.log"),
                    folder("cadgen-view-newname_"), file("cadgen-trace-newname_.log"),
                    folder("cadgen-viewer-info"), file("cadgen-bind-x1y2"), folder("cadgen-test-store.ab12"),
                    # A live sweeper's condemned folder is its own to finish.
                    folder(f"cadgen-swept-{live}-cadgen-view-busyname")]
            old = time.time() - 2 * temp_leftovers.UNNAMED_AGE_SECONDS
            for path in (root / "cadgen-view-o1dname_", root / "cadgen-trace-o1dname_.log"):
                os.utime(path, (old, old))
            removed = temp_leftovers.sweep(root)
            self.assertEqual(sorted(removed), sorted(str(path) for path in gone))
            self.assertEqual([path for path in gone if path.exists()], [])
            self.assertEqual([path for path in kept if not path.exists()], [])
            # What this sweep condemned it also deleted.
            self.assertEqual(sorted(path.name for path in root.glob("cadgen-swept-*")),
                             [f"cadgen-swept-{live}-cadgen-view-busyname"])

    def test_scratch_is_named_after_its_process(self):
        import os
        from pathlib import Path

        from cadgen._internal import filetrace

        with filetrace.capture():
            log = Path(filetrace._LOG).name
        self.assertTrue(log.startswith(f"cadgen-trace-{os.getpid()}-"), log)

    def test_a_starting_worker_sweeps_before_it_is_ready(self):
        program = textwrap.dedent("""
            from cadgen._internal import temp_leftovers
            from cadgen.daemon import worker
            swept = []
            temp_leftovers.sweep_in_background = lambda: swept.append(True)
            original_emit = worker._emit
            def checked_emit(frame):
                if "ready" in frame:
                    assert swept == [True], "ready before the scratch sweep started"
                original_emit(frame)
            worker._emit = checked_emit
            raise SystemExit(worker.serve())
        """)
        completed = subprocess.run(
            [sys.executable, "-c", program], input="", text=True,
            capture_output=True, timeout=90,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)


if __name__ == "__main__":
    unittest.main()
