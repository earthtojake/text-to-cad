"""A ready spare has loaded the kernel; importing its supervisor has not."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
import unittest


class WorkerPrewarm(unittest.TestCase):
    def test_kernel_is_loaded_before_ready_but_not_at_namespace_import(self):
        # A fresh interpreter prevents this suite's earlier geometry tests from
        # making a parser-only prewarm appear to have loaded the kernel.
        program = textwrap.dedent("""
            import sys
            from cadgen.daemon import worker
            assert "build123d" not in sys.modules
            assert "OCP.BRep" not in sys.modules
            original_emit = worker._emit
            def checked_emit(frame):
                if "ready" in frame:
                    assert "build123d" in sys.modules, "ready before build123d import"
                    assert "OCP.BRep" in sys.modules, "ready before kernel import"
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


if __name__ == "__main__":
    unittest.main()
