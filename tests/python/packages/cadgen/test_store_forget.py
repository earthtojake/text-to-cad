"""``cadgen store forget``: the surgical reset between ``--force`` and ``rm -rf``.

Forgetting a model drops its record and nothing else, so ``store why`` says
``no record`` and the next run rebuilds it. Forgetting a document drops the
tree entry for its bytes (and the record that wrote it), so the next door call
compiles it again -- and answers, in one call. A target the store never heard
of is nothing to forget, exit 0. Real CLIs, transient builds, a temp store.
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


class StoreForget(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="store-forget-")
        self.root = Path(self._tmp.name) / "proj"
        (self.root / "src").mkdir(parents=True)
        self.cache = Path(self._tmp.name) / "store"
        (self.root / "src" / "pin.py").write_text(textwrap.dedent(PIN).lstrip(), encoding="utf-8")
        result = _run("src/pin.py", cwd=self.root, cache=self.cache)
        assert result.returncode == 0, result.stderr

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _store(self, *argv: str) -> subprocess.CompletedProcess:
        return _run("-m", "cadgen.cli", "store", *argv, cwd=self.root, cache=self.cache)

    def test_forgetting_a_model_drops_its_record_only(self) -> None:
        self.assertIn("verdict current", self._store("why", "src/pin.py").stdout)
        dry = self._store("forget", "src/pin.py", "--dry-run")
        self.assertEqual(0, dry.returncode, dry.stderr)
        self.assertIn("would forget record", dry.stdout)
        self.assertIn("verdict current", self._store("why", "src/pin.py").stdout, "a dry run forgets nothing")

        result = self._store("forget", "src/pin.py")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("forgot record", result.stdout)
        why = self._store("why", "src/pin.py")
        self.assertEqual(1, why.returncode)
        self.assertIn("verdict STALE  (no record)", why.stdout)
        # The tree object is still there: only gc deletes objects.
        objects = [p for p in (self.cache / "objects").rglob("*") if p.is_file()]
        self.assertTrue(objects)
        # The next run rebuilds and the model is current again.
        rebuilt = _run("src/pin.py", cwd=self.root, cache=self.cache)
        self.assertEqual(0, rebuilt.returncode, rebuilt.stderr)
        self.assertIn("verdict current", self._store("why", "src/pin.py").stdout)

    def test_forgetting_a_document_makes_the_next_door_call_compile_it(self) -> None:
        result = self._store("forget", "src/pin.step", "--json")
        self.assertEqual(0, result.returncode, result.stderr)
        payload = json.loads(result.stdout.strip())
        kinds = sorted(item["kind"] for item in payload["targets"][0]["forgot"])
        self.assertEqual(["document", "output", "record"], kinds)
        self.assertFalse(any((self.cache / "index" / "document").iterdir()))
        # The door compiles the bytes again and answers in one call.
        inspect = _run(
            "-m", "cadgen.cli", "step", "inspect", "refs", "src/pin.step", "--facts",
            cwd=self.root, cache=self.cache,
        )
        self.assertEqual(0, inspect.returncode, inspect.stdout + inspect.stderr)
        answer = json.loads(inspect.stdout.strip())
        self.assertTrue(answer["ok"], answer)
        self.assertEqual("part", answer["tokens"][0]["summary"]["kind"])
        self.assertTrue(any((self.cache / "index" / "document").iterdir()))

    def test_an_unknown_target_is_nothing_to_forget(self) -> None:
        result = self._store("forget", "src/never_built.py", "STEP/nowhere.step")
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual(
            ["nothing to forget: src/never_built.py", "nothing to forget: STEP/nowhere.step"],
            result.stdout.strip().splitlines(),
        )


if __name__ == "__main__":
    unittest.main()
