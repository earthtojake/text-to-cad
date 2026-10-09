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
    views, exported views, trace logs, STEP import copies -- and never a live process's
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
                    file(f"cadgen-trace-{dead}-ab12cd34.log"), file(f"cadgen-step-import-{dead}-ab12cd34.step"),
                    folder("cadgen-view-o1dname_"), file("cadgen-trace-o1dname_.log"),
                    file("cadgen-step-import-o1dname_.stp"),
                    # A folder an earlier sweep condemned and was killed deleting.
                    folder(f"cadgen-swept-{dead}-cadgen-view-o1dname2")]
            kept = [folder(f"cadgen-views/{live}"), folder("cadgen-views/not-a-pid"),
                    folder(f"cadgen-view-{live}-ef56gh78"), file(f"cadgen-trace-{live}-ef56gh78.log"),
                    file(f"cadgen-step-import-{live}-ef56gh78.step"), file("cadgen-step-import-newname_.step"),
                    folder("cadgen-view-newname_"), file("cadgen-trace-newname_.log"),
                    folder("cadgen-viewer-info"), file("cadgen-bind-x1y2"), folder("cadgen-test-store.ab12"),
                    # A live sweeper's condemned folder is its own to finish.
                    folder(f"cadgen-swept-{live}-cadgen-view-busyname")]
            old = time.time() - 2 * temp_leftovers.UNNAMED_AGE_SECONDS
            for path in (root / "cadgen-view-o1dname_", root / "cadgen-trace-o1dname_.log",
                         root / "cadgen-step-import-o1dname_.stp"):
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

    def test_a_step_import_copy_is_named_after_its_process_and_removed_after_the_parse(self):
        import os
        import tempfile
        from pathlib import Path
        from unittest import mock

        from cadgen._internal import step_scene_package

        copies = []

        def parse(snapshot, *, named):
            copies.append((Path(snapshot), Path(snapshot).is_file()))
            return mock.Mock()

        with tempfile.TemporaryDirectory(prefix="import-copy-") as tmp, \
                mock.patch.object(step_scene_package, "_load_step_scene_text", parse):
            step_scene_package._scene_from_selected_bytes(Path(tmp) / "dial.step", b"ISO-10303-21;")
        [(copy, existed)] = copies
        self.assertTrue(existed)
        self.assertTrue(copy.name.startswith(f"cadgen-step-import-{os.getpid()}-"), copy.name)
        self.assertFalse(copy.exists())


class StageFolderSweep(unittest.TestCase):
    """A build killed while it saves leaves its STEP staging folder beside its output; the
    next build there removes it, and never a live build's or another machine's
    (``temp_leftovers.sweep_stages``)."""

    def test_the_stage_sweep_takes_this_machines_dead_and_old_stages_only(self):
        import os
        import tempfile
        import time
        from pathlib import Path

        from cadgen._internal import temp_leftovers

        exited = subprocess.Popen([sys.executable, "-c", "pass"])
        exited.wait()
        dead, live, host = exited.pid, os.getpid(), temp_leftovers._host()
        other = "0" * 8 if host != "0" * 8 else "1" * 8
        with tempfile.TemporaryDirectory(prefix="stage-sweep-") as tmp:
            root = Path(tmp)

            def stage(name):
                path = root / name
                path.mkdir()
                (path / "part.step").write_text("ISO-10303-21;", encoding="utf-8")
                return path

            gone = [stage(f".cadgen-stage-{dead}-{host}-part-ab12cd34"), stage(".cadgen-stage-part-o1dname_")]
            kept = [stage(f".cadgen-stage-{live}-{host}-part-ef56gh78"), stage(f".cadgen-stage-{dead}-{other}-part-ab12cd34"),
                    stage(".cadgen-stage-part-newname_"), stage("cadgen-stage-not-hidden"), stage("parts")]
            old = time.time() - 2 * temp_leftovers.UNNAMED_AGE_SECONDS
            os.utime(root / ".cadgen-stage-part-o1dname_", (old, old))
            removed = temp_leftovers.sweep_stages(root)
            self.assertEqual(sorted(removed), sorted(str(path) for path in gone))
            self.assertEqual([path for path in gone if path.exists()], [])
            self.assertEqual([path for path in kept if not path.exists()], [])
            self.assertEqual(temp_leftovers.sweep_stages(root / "missing"), [])

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
