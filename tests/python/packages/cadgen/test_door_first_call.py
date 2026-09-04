"""A door's FIRST look at a new document compiles it and answers -- in one call.

The tom-cad migration found that `cadgen step inspect refs X.step` on a document
whose bytes had no tree failed once ("Build finished but no tree exists", with a
"regenerate" instruction) and succeeded on the second call. The door resolved
the tree's view path BEFORE compiling -- from a lookup that answered "no tree" --
and then checked that placeholder after the compile. It also told the user to
run something, which a door never does (STORE.md §9: doors never refuse).

Real CLIs, real transient builds, a temp store: the only way to see the first
call as the user does. The same fixture pins the run result's shape: `kind` is
read off the tree (a linked assembly says so even when its return was inferred
as a part) and no source grammar (`sourceRef`, `cadPath`) rides beside
`document` and `tree`.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT
from tests.python.support.tmp_root import temporary_directory

PIN = """
    from cadgen import step
    from cadgen import build123d as bd


    @step
    def pin():
        return bd.Cylinder(radius=2.0, height=12.0)


    if __name__ == "__main__":
        pin()
"""

ARM = """
    from cadgen import step
    from cadgen import build123d as bd
    from pin import pin


    @step
    def arm():
        p = pin()
        return bd.Compound(children=[bd.Box(40, 8, 4), bd.Pos(-15, 0, 2) * p, bd.Pos(15, 0, 2) * p], label="arm")


    if __name__ == "__main__":
        arm()
"""


def _run(*argv: str, cwd: Path, cache: Path) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        p for p in [str(REPO_ROOT / "packages" / "cadgen" / "src"), env.get("PYTHONPATH", "")] if p
    )
    env["CADGEN_CACHE_DIR"] = str(cache)
    env["CADGEN_DAEMON"] = "0"
    env.pop("CADGEN_DAEMON_CHILD", None)
    return subprocess.run(
        [sys.executable, *argv], cwd=str(cwd), env=env, capture_output=True, text=True, timeout=600
    )


class DoorFirstCall(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = temporary_directory(prefix="door-first-call-")
        cls.root = Path(cls._tmp.name) / "proj"
        (cls.root / "src").mkdir(parents=True)
        cls.cache = Path(cls._tmp.name) / "store"
        for name, text in (("pin.py", PIN), ("arm.py", ARM)):
            (cls.root / "src" / name).write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
        cls.runs = {}
        for name in ("pin", "arm"):
            result = _run(f"src/{name}.py", "--json", cwd=cls.root, cache=cls.cache)
            assert result.returncode == 0, result.stderr
            cls.runs[name] = json.loads(result.stdout.strip().splitlines()[-1])

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_the_first_inspect_of_a_new_document_compiles_it_and_answers(self) -> None:
        # New BYTES (a header edit), so the store has no tree for this file yet.
        original = (self.root / "src" / "pin.step").read_text(encoding="utf-8")
        copy = self.root / "src" / "pin_copy.step"
        copy.write_text(original.replace("Open CASCADE Model", "Open CASCADE Model X", 1), encoding="utf-8")

        # A RELATIVE path, from the project root (on macOS a temp dir sits under the
        # /tmp -> /private/tmp symlink): the path is resolved once at the door.
        result = _run(
            "-m", "cadgen.cli", "step", "inspect", "refs", "src/pin_copy.step", "--facts",
            cwd=self.root, cache=self.cache,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip())
        self.assertTrue(payload["ok"], payload)
        token = payload["tokens"][0]
        self.assertEqual("src/pin_copy.step", token["document"])
        self.assertEqual("part", token["summary"]["kind"])
        self.assertEqual(1, token["summary"]["occurrenceCount"])
        self.assertEqual([], payload.get("errors", []))
        self.assertNotIn("regenerateCommand", json.dumps(payload))
        self.assertNotIn("Regenerate", json.dumps(payload))

    def test_the_run_result_reads_kind_off_the_tree_and_carries_no_source_grammar(self) -> None:
        pin, arm = self.runs["pin"], self.runs["arm"]
        self.assertEqual("part", pin["kind"])
        # arm's return is a Compound the static inference cannot see through; the
        # tree has two links, so the run says assembly -- the same answer inspect gives.
        self.assertEqual("assembly", arm["kind"])
        for payload in (pin, arm):
            self.assertEqual({"ok", "kind", "outcome", "document", "tree"}, set(payload))

    def test_inspect_and_the_run_agree_on_kind(self) -> None:
        result = _run(
            "-m", "cadgen.cli", "step", "inspect", "refs", "src/arm.step", "--facts",
            cwd=self.root, cache=self.cache,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip())
        self.assertEqual(self.runs["arm"]["kind"], payload["tokens"][0]["summary"]["kind"])


if __name__ == "__main__":
    unittest.main()
