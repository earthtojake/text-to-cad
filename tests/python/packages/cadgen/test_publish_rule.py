"""No locks: concurrent builds both run, and the disk ends at the current source.

Real processes on the transient executor (``CADGEN_DAEMON=0``), which is the unbrokered
mode -- the one where the publish rule and atomic writes are all that stand between two
builders of one model. Also the parent/child snapshot-isolation story: a child rebuilt
while its parent is mid-body leaves the parent built against its pin and flagged stale.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import REPO_ROOT, add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

PART = """\
from cadgen import step
from cadgen import build123d as bd


@step
def widget():
    return bd.Box({size}, 8.0, 4.0)


if __name__ == "__main__":
    widget()
"""

LEAF = """\
from cadgen import step
from cadgen import build123d as bd


@step
def leaf():
    return bd.Cylinder(radius={radius}, height=5.0)


if __name__ == "__main__":
    leaf()
"""

PARENT = """\
from cadgen import step
from cadgen import build123d as bd

from leaf import leaf


@step
def parent():
    pin = leaf()
    pin.faces()  # forces: the child's tree is PINNED here, before the long body
    import os, time
    if {sleep} > 0:
        # Handshake with the test instead of racing its clock: say the pin is taken
        # (`pinned` beside this script), then wait for `go` -- the test rebuilds the
        # child in between. The same order on a slow runner and a fast one.
        here = os.path.dirname(os.path.abspath(__file__))
        open(os.path.join(here, "pinned"), "w").close()
        go = os.path.join(here, "go")
        deadline = time.monotonic() + 300
        while not os.path.exists(go) and time.monotonic() < deadline:
            time.sleep(0.05)
    return bd.Compound(children=[bd.Box(20, 20, 2), bd.Pos(0, 0, 5) * pin], label="parent")


if __name__ == "__main__":
    parent()
"""


class PublishRuleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = temporary_directory(prefix="cadgen-publish-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ)
        self.env.update({
            "CADGEN_DAEMON": "0",
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON_STATE_DIR": str(self.root / "state"),
        })
        self.env.pop("CADGEN_ROOT_ID", None)
        self.env.pop("CADGEN_DAEMON_CHILD", None)
        # The model scripts run from a temp dir: a relative PYTHONPATH entry would resolve
        # there and the scripts would import whatever cadgen is installed, not this one.
        self.env["PYTHONPATH"] = os.pathsep.join(
            [str(REPO_ROOT / "packages" / "cadgen" / "src")]
            + [os.path.abspath(p) for p in self.env.get("PYTHONPATH", "").split(os.pathsep) if p]
        )
        # The gate and the records this test reads in-process must look at the same store.
        patcher = mock.patch.dict(os.environ, {k: self.env[k] for k in ("CADGEN_CACHE_DIR", "CADGEN_DAEMON_STATE_DIR")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def _start(self, script: Path) -> subprocess.Popen:
        return subprocess.Popen(
            [sys.executable, script.name, "--json"], cwd=str(self.root), env=self.env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def _run(self, script: Path) -> dict:
        proc = self._start(script)
        out, err = proc.communicate(timeout=600)
        # Under --json the failure envelope is on STDOUT; stderr is only the build tree.
        self.assertEqual(proc.returncode, 0, out + err)
        return json.loads(out.strip().splitlines()[-1]) | {"stderr": err}

    def test_two_builds_of_one_model_both_run_and_the_disk_ends_current(self):
        # Both builds run the SAME source, started back to back so they publish the same
        # record, entries and document at about the same moment: the byte-identical race
        # STORE.md §7 calls idempotent. (Each worker imports the script when it gets there,
        # so an edit between the starts would not reliably give the first an older source;
        # the stale-build rejection is decide()'s, pinned in test_store.)
        script = self.root / "widget.py"
        script.write_text(PART.format(size=11.0), encoding="utf-8")
        first = self._start(script)
        second = self._start(script)
        outputs = []
        for proc in (first, second):
            out, err = proc.communicate(timeout=600)
            self.assertEqual(proc.returncode, 0, out + err)
            outputs.append(json.loads(out.strip().splitlines()[-1])["outcome"])
        self.assertTrue(all(o in {"built", "skipped-peer"} for o in outputs), outputs)
        self.assertIn("built", outputs)
        # Whatever order they finished in, a rerun sees the newer source as current:
        # the record on disk describes the sources as they are now.
        self.assertEqual(self._run(script)["outcome"], "current")
        from cadgen.store.gate import stale

        self.assertFalse(stale(script).stale)

    def test_reading_back_a_step_a_peer_is_replacing_waits_it_out(self):
        # The race above, pinned without a second process: Windows refuses an open of a
        # file another build is renaming over with EACCES and no winerror, and the
        # publish's read-back of the .step must wait that out rather than fail the save.
        import errno
        import hashlib

        from cadgen._internal import atomic_replace, generation

        step = self.root / "widget.step"
        step.write_bytes(b"ISO-10303-21;\n")
        real_open = Path.open
        refused = []

        def peer_renaming(path, mode="r", *args, **kwargs):
            if Path(path) == step and not refused:
                refused.append(path)
                raise PermissionError(errno.EACCES, "Permission denied")
            return real_open(path, mode, *args, **kwargs)

        with mock.patch.object(atomic_replace, "_OPEN_REFUSAL_IS_ERRNO_ONLY", True), \
                mock.patch.object(Path, "open", peer_renaming), mock.patch("time.sleep"):
            digest, _sidecar = generation._document_pair_state(step)
        self.assertTrue(refused)
        self.assertEqual(hashlib.sha256(b"ISO-10303-21;\n").hexdigest(), digest)

    def test_a_child_edited_mid_parent_build_leaves_the_parent_flagged_stale(self):
        leaf = self.root / "leaf.py"
        parent = self.root / "parent.py"
        leaf.write_text(LEAF.format(radius=2.0), encoding="utf-8")
        parent.write_text(PARENT.format(sleep=6.0), encoding="utf-8")
        self._run(leaf)  # the child is current when the parent starts
        running = self._start(parent)
        # Wait until the parent's body holds the child's pin: it drops `pinned`
        # beside its script once `leaf()` has been forced, then waits for `go`.
        pinned = self.root / "pinned"
        deadline = time.monotonic() + 300
        while not pinned.exists() and time.monotonic() < deadline:
            if running.poll() is not None:
                break
            time.sleep(0.05)
        self.assertTrue(pinned.exists(), "the parent never reported its pin")
        # Rebuild the child against the parent's back, then release the parent.
        leaf.write_text(LEAF.format(radius=3.0), encoding="utf-8")
        self._run(leaf)
        (self.root / "go").write_text("", encoding="utf-8")
        out, err = running.communicate(timeout=600)
        self.assertEqual(running.returncode, 0, out + err)
        result = json.loads(out.strip().splitlines()[-1])
        self.assertEqual(result["outcome"], "built")
        transitions = [json.loads(line) for line in err.splitlines() if line.startswith("{")]
        done = [t for t in transitions if t["model"] == str(parent) and t["state"] == "done"]
        self.assertTrue(done, err)
        self.assertIn("stale", done[-1], "the tree did not say the parent is already stale")
        # The notice is the gate's phrase, not a repr of the method that makes it.
        self.assertIn("child result moved", done[-1]["stale"], done[-1])
        from cadgen.store.gate import stale

        self.assertTrue(stale(parent).stale, "the parent built against its pin and must read stale now")
        self.assertEqual(self._run(parent)["outcome"], "built")
        self.assertFalse(stale(parent).stale)


if __name__ == "__main__":
    unittest.main()
