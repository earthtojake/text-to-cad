"""The catalog over an adversarial fixture, fenced against regression.

This began life as a byte-for-byte comparison of the Python catalog against the
Node catalog it replaced — the strongest checkpoint available during the port,
because it compared two implementations rather than an implementation against
an opinion. Both halves agreed exactly, and then the JS half was deleted at the
cut, so the oracle is gone.

What survives is the expensive part: a fixture that reaches branches a real
corpus does not — descriptors that are directories, arrays, or the wrong kind;
sidecars that are arrays, empty objects, explicit nulls or malformed; SRDF
pairing that is ambiguous, cross-directory or hidden; symlinks that loop,
dangle, alias and escape; the depth cap; and a sort corpus of punctuation,
case, accents, expansions, fullwidth digits and an astral character.

So the comparison became a SNAPSHOT. The golden below was captured from the
Python scanner at the moment it was still verified identical to Node, and it
pins the two things a hand-written assertion cannot: the exact ORDER of the
whole catalog (the collation model's output, and the highest-risk piece of the
port) and the exact per-entry shape decisions. It records file, kind, and which
optional keys are present — deliberately not the URLs or hashes, which carry
mtime tokens and temp paths that vary per run and would make this flaky rather
than strict.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from cadgen.viewer.backend import LocalAssetBackend
from cadgen.viewer.scanner import scan_cad_directory
from tests.python.support.store_fixtures import seed_result

# Characters NTFS refuses in a filename. POSIX writes every fixture name below;
# Windows skips exactly the names its filesystem cannot represent, and the
# golden comparison drops those rows on Windows only. The names stay in the
# fixture and the golden — they are the point of the coverage on POSIX.
_NTFS_FORBIDDEN = set('*?"<>|:') | {chr(code) for code in range(32)}


def _name_can_exist_here(name: str) -> bool:
    if os.name != "nt":
        return True
    return not (_NTFS_FORBIDDEN & set(name))


def _build_fixture(root: str, cache: str) -> None:
    os.makedirs(cache, exist_ok=True)
    os.environ["CADGEN_CACHE_DIR"] = cache

    def write(rel, text):
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Bytes, never text mode, so the content is identical on every
        # platform instead of gaining \r\n on Windows.
        Path(path).write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))
        return path

    def package(rel, descriptor, *, raw=None, as_dir=False):
        """Seed ``root/<rel>``'s result. A descriptor that is not a result
        (raw text, a directory, a foreign kind) seeds NOTHING: in the store a
        result is a tree or it does not exist, so those rows read as unbuilt."""
        if raw is not None or as_dir or not isinstance(descriptor, dict):
            return
        if descriptor.get("kind") != "assembly-package":
            return
        seed_result(Path(root, rel), descriptor)

    valid = {"kind": "assembly-package", "components": {"c0": {"surf": "c0.surf"}}}

    # --- descriptor variants ---------------------------------------------
    write("a_part.step", "part\n")
    package("a_part.step", valid)
    write("b_assembly.step", "assembly\n")
    package("b_assembly.step", {"kind": "assembly-package", "entryKind": "  ASSEMBLY  "})
    write("c_root.step", "root\n")
    package("c_root.step", {"kind": "assembly-package", "assembly": {"root": {"x": 1}}})
    write("d_root_string.step", "rootstr\n")
    package("d_root_string.step", {"kind": "assembly-package", "assembly": {"root": "x"}})
    write("l_dir_descriptor.step", "dird\n")
    package("l_dir_descriptor.step", None, as_dir=True)
    write("m_bad_descriptor.step", "badd\n")
    package("m_bad_descriptor.step", None, raw="{ nope")
    write("n_array_descriptor.step", "arrd\n")
    package("n_array_descriptor.step", None, raw="[1,2,3]")
    write("o_no_package.step", "nopkg\n")
    # The render module beside a document: authored, discovered by name.
    write("r_render_module.step", "render\n")
    write("r_render_module.step.js", "export const clips = {};\n")
    package("r_render_module.step", valid)

    # --- sidecar variants -------------------------------------------------
    for name, sidecar in (
        ("e_kin", json.dumps({"schemaVersion": 5, "kinematics": {"joints": []}})),
        ("f_anim", json.dumps({"animation": {"text": "x"}})),
        ("g_array", "[1,2]"),
        ("h_empty_kin", json.dumps({"kinematics": {}})),
        ("i_nulls", json.dumps({"kinematics": None, "animation": None})),
        ("j_bad", "{ not json"),
        ("q_scalar", '"hello"'),
    ):
        write(f"{name}.step", f"{name}\n")
        write(f"{name}.step.json", sidecar)
        package(f"{name}.step", valid)
    # A sidecar with a WRONG descriptor kind publishes neither url.
    write("k_wrong_kind.step", "wrong\n")
    write("k_wrong_kind.step.json", json.dumps({"kinematics": {"a": 1}}))
    package("k_wrong_kind.step", {"kind": "not-a-package"})
    # Uppercase suffix: the sidecar name follows the artifact's whole name.
    write("p_upper.STP", "upper\n")
    write("p_upper.STP.json", json.dumps({"kinematics": {"j": 1}}))
    package("p_upper.STP", valid)

    # --- non-STEP assets and non-entries ---------------------------------
    for name, body in (
        ("mesh.stl", "solid x\nendsolid x\n"),
        ("empty.stl", ""),
        ("model.3mf", "3mf"),
        ("scene.glb", "glTF"),
        ("outline.dxf", "0\nSECTION\n"),
        ("world.sdf", "<sdf/>"),
        ("gyroid.implicit.js", "export default 1;"),
        ("loose.params.js", "export default 2;"),
        ("model.py", "print(1)"),
        ("secrets.json", '{"token":"x"}'),
    ):
        write(name, body)

    # --- URDF / SRDF pairing ---------------------------------------------
    write("robots/arm.urdf", '<?xml version="1.0"?><robot name="arm"><link name="l"/></robot>')
    write("robots/other.urdf", '<robot name="other"/>')
    write("robots/arm.srdf", '<?xml version="1.0"?><!-- c --><!DOCTYPE robot><robot name="arm"/>')
    write("ambig/one.urdf", '<robot name="dup"/>')
    write("ambig/two.urdf", '<robot name="dup"/>')
    write("ambig/dup.srdf", '<robot name="dup"/>')
    write("noname/x.urdf", "<robot/>")
    write("noname/x.srdf", "<robot/>")
    write("hiddenurdf/.arm.urdf", '<robot name="hid"/>')
    write("hiddenurdf/hid.srdf", '<robot name="hid"/>')
    write("split/deep/far.urdf", '<robot name="far"/>')
    write("split/far.srdf", '<robot name="far"/>')
    write("quoted/q.urdf", "<robot  name = 'q'  version=\"1\" />")
    write("quoted/q.srdf", "<robot name='q'/>")
    write("mojibake/m.urdf", b'<robot name="m\xff\xfe"/>')
    write("mojibake/m.srdf", b'<robot name="m\xff\xfe"/>')
    write("bom/b.urdf", "﻿<robot name=\"b\"/>")
    write("bom/b.srdf", "﻿<robot name=\"b\"/>")

    # --- collation and URL-encoding stress -------------------------------
    for name in (
        "_x.step", "001.stl", "1.stl", "2 x.stl", "2x.stl", "9.stl", "10.stl", "12.stl",
        "A.stl", "à.stl", "B.stl", "e.stl", "é.stl", "ünicode.stl",
        "v2.9.stl", "v2.10.stl", "v10.1.stl", "x_1.stl", "x-1.stl", "Z.stl",
        "가.stl", "日本語.stl", "a b(c)*d~e._-!'.stl",
        "1­2.stl", "ß.stl", "Ⅻ.stl", "Ａ.stl", "１.stl",
        "\U0001f642.stl",
    ):
        if not _name_can_exist_here(name):
            continue
        write(os.path.join("sortcases", name), f"content of {name}\n")

    # --- walk rules -------------------------------------------------------
    for skipped in ("dist", "build", "node_modules", "__pycache__", "coverage", "viewer", "__cadgen__"):
        write(os.path.join(skipped, "x.stl"), "skipped")
    write("Kept/kept.stl", "kept")
    write(".dotfile.step", "hidden")
    write(".hidden/secret.step", "hidden dir")
    write("sub/.git/config.stl", "git")

    # --- symlinks ---------------------------------------------------------
    base = os.path.dirname(root)
    os.makedirs(os.path.join(base, "library_real"))
    Path(base, "library_real", "part.step").write_text("lib\n", encoding="utf-8")
    os.symlink(os.path.join(base, "library_real"), os.path.join(root, "library"))
    write("looproot/model.stl", "loop model")
    os.symlink(".", os.path.join(root, "looproot", "loop"))
    os.symlink(os.path.join(base, "nonexistent.stl"), os.path.join(root, "dangling.stl"))
    os.makedirs(os.path.join(base, "outside"))
    Path(base, "outside", "secret.step").write_text("outside\n", encoding="utf-8")
    os.symlink(os.path.join(base, "outside", "secret.step"), os.path.join(root, "escape.step"))
    os.makedirs(os.path.join(root, "aliased", "real"))
    write("aliased/real/part.stl", "aliased")
    os.symlink(os.path.join(root, "aliased", "real"), os.path.join(root, "aliased", "Alink"))
    os.symlink(os.path.join(root, "aliased", "real"), os.path.join(root, "aliased", "zlink"))

    # --- depth cap --------------------------------------------------------
    current = os.path.join(root, "deep")
    for level in range(70):
        current = os.path.join(current, f"d{level}")
        os.makedirs(current)
        Path(current, f"f{level}.stl").write_text(f"level {level}\n", encoding="utf-8")


def _shape(entries) -> list:
    """The stable half of each entry: identity, kind, and which keys are present.

    URLs and hashes are excluded on purpose. They carry ``?v=`` mtime tokens and
    absolute temp paths, so pinning them would make this flaky rather than
    strict — and they are covered by their own byte-exact tests in
    test_parity.py and test_scanner.py.
    """
    shaped = []
    for entry in entries:
        shaped.append(
            [
                entry["file"],
                entry["kind"],
                "hash" if entry.get("hash") else "",
                "sourceUrl" if "sourceUrl" in entry else "",
                "poseUrl" if "poseUrl" in entry else "",
                "renderModuleUrl" if "renderModuleUrl" in entry else "",
                sorted((entry.get("relations") or {}).keys()),
            ]
        )
    return shaped


GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "catalog_shape.json"


class CatalogShapeSnapshot(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.root = os.path.join(cls.tmp, "root")
        cls.cache = os.path.join(cls.tmp, "cache")
        os.makedirs(cls.root)
        cls._previous_cache = os.environ.get("CADGEN_CACHE_DIR")
        _build_fixture(cls.root, cls.cache)

    @classmethod
    def tearDownClass(cls):
        if cls._previous_cache is None:
            os.environ.pop("CADGEN_CACHE_DIR", None)
        else:
            os.environ["CADGEN_CACHE_DIR"] = cls._previous_cache
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_the_catalog_matches_the_golden_shape(self):
        actual = _shape(scan_cad_directory(self.root)["entries"])
        expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        # The golden is captured on POSIX; on Windows the fixture cannot write
        # names NTFS forbids, so exactly those rows are dropped from the
        # expectation. Everything else — order included — is still pinned.
        expected = [
            row for row in expected if _name_can_exist_here(row[0].rsplit("/", 1)[-1])
        ]
        if actual == expected:
            return
        actual_files = [row[0] for row in actual]
        expected_files = [row[0] for row in expected]
        if actual_files != expected_files:
            self.fail(
                "entry ORDER or membership changed:\n"
                f"  missing: {sorted(set(expected_files) - set(actual_files))}\n"
                f"  added:   {sorted(set(actual_files) - set(expected_files))}\n"
                f"  golden order: {expected_files}\n"
                f"  actual order: {actual_files}"
            )
        for left, right in zip(expected, actual):
            if left != right:
                self.fail(f"entry {left[0]!r} changed shape:\n  golden: {left}\n  actual: {right}")

    def test_the_absolutized_catalog_keeps_the_same_order_and_membership(self):
        # absolutizeEntry rewrites urls and adds rootRelativeFile/assetFile; it
        # must not reorder, drop or add anything.
        raw = scan_cad_directory(self.root)["entries"]
        absolutized = LocalAssetBackend(self.root).read_catalog()["entries"]
        self.assertEqual(
            [e["rootRelativeFile"] for e in absolutized],
            [e["file"] for e in raw],
            "absolutization changed the catalog's order or membership",
        )

    def test_the_fixture_actually_reaches_the_interesting_branches(self):
        # A snapshot over a tree that exercises nothing passes vacuously.
        entries = scan_cad_directory(self.root)["entries"]
        self.assertGreater(len(entries), 100)
        self.assertGreaterEqual(sum(1 for e in entries if e["kind"] == "assembly"), 2)
        self.assertGreaterEqual(sum(1 for e in entries if "poseUrl" in e), 3)
        self.assertGreaterEqual(sum(1 for e in entries if "renderModuleUrl" in e), 1)
        self.assertGreaterEqual(sum(1 for e in entries if "sourceUrl" in e), 6)
        self.assertGreaterEqual(sum(1 for e in entries if "relations" in e), 4)
        self.assertGreaterEqual(sum(1 for e in entries if e["hash"] == ""), 4)
        self.assertTrue(any(e["file"].startswith("library/") for e in entries))
        self.assertTrue(any(e["file"].startswith("deep/") for e in entries))

    @unittest.skipIf(
        os.name == "nt",
        "NTFS forbids '*' in filenames, so the punctuation sort case cannot exist on Windows",
    )
    def test_the_punctuation_stress_name_is_present_on_posix(self):
        # Guards the Windows-only golden filter above from ever masking this
        # name where the platform CAN represent it.
        files = [e["file"] for e in scan_cad_directory(self.root)["entries"]]
        self.assertIn("sortcases/a b(c)*d~e._-!'.stl", files)


if __name__ == "__main__":
    unittest.main()
