"""Git holds code, never CAD or mesh assets.

A STEP, a mesh or a drawing is made on the spot -- by a test into a temporary folder, by a sample on
request into its project's gitignored output folder -- and never committed: every installer clones the
whole repository, so a heavy binary costs every user on every install, and a generated file only drifts
from the code that makes it. The few that stay are listed below, each with the most bytes it may grow to
and the reason no test or script can make it on the spot.
"""

from __future__ import annotations

import re
import subprocess
import unittest
from collections.abc import Iterable, Mapping

from tests.python.support.paths import REPO_ROOT

CAD_ASSET = re.compile(r"\.(?:step|stp|stl|glb|gltf|3mf|xbf|obj|ply|brep|iges|igs|dae|fbx|usdz?|dxf)$", re.IGNORECASE)

KIB = 1024
TINY = 64 * KIB

# (path, `*` standing for any run of characters but `/`; most bytes; why it is committed). An entry that
# matches no tracked file fails, so the list never outlives what it excuses.
ALLOWED: tuple[tuple[str, int, str], ...] = (
    ("tests/python/packages/cadgen/engine/fixtures/xbf8_materials.xbf", TINY,
     "the 15.9 KiB document written by published cadgen 0.8.0/OCP 7.9; migration tests must read real "
     "old BinXCAF bytes, which the current engine/kernel cannot regenerate"),
    ("apps/docs/public/hero/planetary.glb", 256 * KIB,
     "the docs homepage hero, served as a static file by a site with no backend; to be built by Deploy Docs "
     "from the planetary model instead, which is the owner's call"),
    ("packages/core/src/lib/render/fixtures/*.glb", TINY,
     "the GLBs the core and UI suites open (2-18 KB each); a JS test cannot run the engine that bakes them "
     "(the README beside them says how each was made)"),
    ("packages/core/src/lib/xbf/__fixtures__/arm/arm.glb", TINY,
     "the engine's GLB bake of the arm that xbfMotion.test.js holds the page's motions to; a JS test "
     "cannot run the engine"),
    ("packages/ui/src/renderers/robot/__fixtures__/meshes/*.glb", TINY,
     "the link mesh of the robot renderer's arm.urdf (two named objects, 3.5 KB), written once by a JS "
     "writer the repository no longer keeps; the robot renderer's JS tests open it"),
    ("packages/ui/src/renderers/robot/__fixtures__/primitives/*.glb", TINY,
     "the meshes cadgen makes for the robot fixtures' primitive shapes (named by sha256, ~1.5 KB each); "
     "make_fixtures.py writes them and test_robot_payload.py holds them current, for JS tests that cannot "
     "run the engine"),
    ("packages/ui/src/renderers/dxf/__fixtures__/*.dxf", TINY,
     "the DXF renderer's test drawings; make_fixture.py writes them, and the JS tests that open them "
     "need neither Python nor ezdxf"),
)

OUTPUT_FOLDERS = ("STEP/x.step", "STL/x.stl", "GLB/x.glb", "3MF/x.3mf", "DXF/x.dxf", "XBF/x.xbf")


def _pattern(path: str) -> re.Pattern[str]:
    return re.compile(re.escape(path).replace(r"\*", "[^/]*"))


def violations(tracked: Mapping[str, int], allowed: Iterable[tuple[str, int, str]] = ALLOWED) -> list[str]:
    """What breaks the rule in `tracked` (every tracked path with the bytes it holds): a CAD or mesh file no
    entry excuses, one grown past its entry's cap, and an entry that excuses nothing or says nothing."""
    entries = [(path, _pattern(path), cap, why) for path, cap, why in allowed]
    found = [path for path in sorted(tracked) if CAD_ASSET.search(path)]
    broken = []
    for path, pattern, cap, why in entries:
        if not why.strip():
            broken.append(f"{path}: an allowed file names no reason")
        if not any(pattern.fullmatch(name) for name in found):
            broken.append(f"{path}: allowed, but no tracked file matches it; remove the entry")
    for name in found:
        excused = next(((cap, why) for _path, pattern, cap, why in entries if pattern.fullmatch(name)), None)
        if excused is None:
            broken.append(f"{name}: a CAD or mesh file is tracked; make it at run time in a temporary folder "
                          "(a test) or on request into a gitignored output folder (a sample), or, when no test "
                          "can make a tiny fixture, list it in ALLOWED with its reason")
        elif tracked[name] > excused[0]:
            broken.append(f"{name}: {tracked[name]} bytes, over the {excused[0]} its entry allows")
    return broken


def git(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(["git", *args], cwd=REPO_ROOT, input=stdin, capture_output=True, text=True, check=True).stdout


def tracked_assets() -> dict[str, int]:
    """Every tracked CAD or mesh file with the bytes its blob holds."""
    # -z: git quotes a name with unusual characters otherwise, and a quoted name would slip the extension test.
    rows = [row.split(None, 3) for row in git("ls-files", "-s", "-z").split("\0") if row]
    entries = [(sha, path) for _mode, sha, _stage, path in rows if CAD_ASSET.search(path)]
    sizes = git("cat-file", "--batch-check=%(objectsize)", stdin="".join(f"{sha}\n" for sha, _path in entries)).split()
    return {path: int(size) for (_sha, path), size in zip(entries, sizes)}


class NoCadAssetsTrackedTest(unittest.TestCase):
    def test_no_cad_or_mesh_file_is_tracked_but_the_listed_few(self) -> None:
        self.assertEqual(violations(tracked_assets()), [])

    def test_the_rule_refuses_what_it_names(self) -> None:
        allowed = (("fixtures/*.glb", 10, "a test opens it"), ("docs/hero.glb", 10, "  "), ("gone/*.step", 10, "none left"))
        tracked = {"fixtures/a.glb": 10, "fixtures/big.glb": 11, "fixtures/deep/c.glb": 1, "tools/part.STEP": 1,
                   "models/x/plate.xbf": 1, "src/readme.md": 1_000_000, "docs/hero.glb": 5}
        broken = violations(tracked, allowed)
        # An entry with no reason, one that excuses nothing, a file past its cap, then the unlisted: a `*` stops
        # at a folder, an extension is no matter of case, and no other file is looked at.
        self.assertEqual([message.split(":")[0] for message in broken], [
            "docs/hero.glb", "gone/*.step", "fixtures/big.glb", "fixtures/deep/c.glb", "models/x/plate.xbf", "tools/part.STEP"])
        self.assertIn("11 bytes, over the 10", broken[2])
        self.assertEqual(violations({"fixtures/a.glb": 10}, allowed[:1]), [])

    def test_every_models_project_ignores_what_its_samples_export(self) -> None:
        projects = sorted({path.split("/")[1] for path in git("ls-files", "models").splitlines() if path.count("/") > 1})
        self.assertTrue(projects)
        outputs = [f"models/{project}/{name}" for project in projects for name in OUTPUT_FOLDERS]
        ignored = set(git("check-ignore", "--no-index", "--", *outputs).split())
        self.assertEqual([path for path in outputs if path not in ignored], [])
        committed = [path for path in git("ls-files", "models").splitlines()
                     if re.search(r"/(?:STEP|STL|GLB|3MF|DXF|XBF|PDF)/", path)]
        self.assertEqual(committed, [], "an export is never committed")


if __name__ == "__main__":
    unittest.main()
