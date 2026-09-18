"""The first Python read compiles missing document bytes and answers in one call.

Use real subprocess scripts and an isolated cache, including a linked
assembly and a malformed document. No source discovery or rendering is needed.
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

    def _read(self, path: str, *refs: str):
        code = """
import json, sys
from cadgen import read_scene
scene = read_scene(sys.argv[1])
leaves = list(scene.leaves())
print(json.dumps({
    "hash": scene.document_hash,
    "leaves": len(leaves),
    "leaf_refs": [o.ref for o in leaves],
    "faces": sum(len(list(o.entities("face"))) for o in leaves),
    "refs": [scene.resolve(ref).ref for ref in sys.argv[2:]],
}))
"""
        return _run("-c", code, path, *refs, cwd=self.root, cache=self.cache)

    def test_the_first_read_of_new_document_bytes_compiles_and_answers(self) -> None:
        original = (self.root / "src" / "pin.step").read_text(encoding="utf-8")
        copy = self.root / "src" / "pin_copy.step"
        replaced = original.replace("HEADER;", "HEADER;\n/* fresh document bytes */", 1)
        self.assertNotEqual(original, replaced)
        copy.write_text(replaced, encoding="utf-8")
        result = self._read("src/pin_copy.step", "#f1")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip())
        self.assertEqual(payload["leaves"], 1)
        self.assertEqual(payload["faces"], 3)
        self.assertEqual(payload["refs"], [payload["leaf_refs"][0] + ".f1"])
        import hashlib
        self.assertEqual(payload["hash"], hashlib.sha256(copy.read_bytes()).hexdigest())

    def test_the_run_result_reads_kind_off_tree_without_source_grammar(self) -> None:
        pin, arm = self.runs["pin"], self.runs["arm"]
        self.assertEqual("part", pin["kind"])
        self.assertEqual("assembly", arm["kind"])
        for payload in (pin, arm):
            self.assertEqual({"ok", "kind", "outcome", "document", "tree"}, set(payload))

    def test_linked_assembly_round_trips_its_occurrences(self) -> None:
        result = self._read("src/arm.step")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout.strip())
        self.assertEqual(payload["leaves"], 3)
        self.assertEqual(payload["faces"], 12)

    def test_document_is_read_without_discovering_adjacent_scripts(self) -> None:
        broken = self.root / "src" / "broken.py"
        broken.write_text("raise AssertionError('must never execute')\n", encoding="utf-8")
        try:
            result = self._read("src/pin.step")
        finally:
            broken.unlink()
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        self.assertNotIn("broken.py", result.stderr)
        self.assertEqual(json.loads(result.stdout)["leaves"], 1)

    def test_part_resolves_bare_and_file_prefixed_entity_refs(self) -> None:
        result = self._read("src/pin.step", "#f1", "src/pin.step#e1", "pin.step#o1")
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        leaf = payload["leaf_refs"][0]
        self.assertEqual(payload["refs"], [leaf + ".f1", leaf + ".e1", "#o1"])

    def test_kernel_diagnostics_do_not_corrupt_script_stdout(self) -> None:
        bad = self.root / "src" / "bad.step"
        bad.write_text("ISO-10303-21;\nHEADER;\nENDSEC;\nDATA;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
        try:
            result = self._read("src/bad.step")
        finally:
            bad.unlink()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
