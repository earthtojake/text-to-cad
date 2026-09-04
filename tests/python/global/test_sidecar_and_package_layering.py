"""The layering rule, held on the artifacts the repo actually ships.

design/pose-animation-split.md pins where each kind of state lives, and both
halves are invisible until something breaks:

* The CACHE PACKAGE is what the bytes imply — derived, evictable, content-keyed.
  Kinematics and animation are not derivable from artifact bytes, so a tree
  carrying either would make identical-bytes artifacts collide and would be
  destroyed by `cadgen cache gc`.
* The SIDECAR is what the author meant, and it TRAVELS WITH THE FILE. A path
  into somebody's source tree inside it is a dependency a generated file must
  never have: the animation module's text is COPIED for exactly this reason,
  and `sourcePath` is stored relative to the document so the pair relocates
  together.

These read committed model artifacts rather than building anything, so they are
fast and they fail on what would actually ship.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
MODELS = REPO_ROOT / "models"

# Keys that belong to the sidecar and must never appear in assembly.json.
SIDECAR_ONLY_KEYS = ("kinematics", "bakedPose")


def _sidecars() -> list[Path]:
    return sorted(MODELS.rglob("*.step.json"))


def _descriptors() -> list[Path]:
    # Committed packages, if any: the store is a user-level cache, so this
    # normally finds the assembly.json files only where a fixture pins one.
    return sorted(MODELS.rglob("assembly.json"))


class PackageCarriesNoAuthoredState(unittest.TestCase):
    def test_no_descriptor_carries_kinematics_or_animation(self) -> None:
        for descriptor_path in _descriptors():
            with self.subTest(descriptor=str(descriptor_path.relative_to(REPO_ROOT))):
                try:
                    descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                if not isinstance(descriptor, dict):
                    continue
                for key in SIDECAR_ONLY_KEYS:
                    self.assertNotIn(
                        key,
                        descriptor,
                        f"{key!r} is AUTHORED state and belongs in the sidecar; a "
                        "content-keyed package cannot hold it (identical bytes would "
                        "collide, and `cadgen cache gc` would delete it)",
                    )


class SidecarCarriesNoSourceTreePaths(unittest.TestCase):
    def test_a_sidecar_never_reaches_back_into_a_source_tree(self) -> None:
        # A generated file must have zero dependencies on the machine that made
        # it. `sourcePath` is the one path field, and it is document-relative.
        for sidecar_path in _sidecars():
            with self.subTest(sidecar=str(sidecar_path.relative_to(REPO_ROOT))):
                payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
                self.assertIsInstance(payload, dict)
                source_path = str(payload.get("sourcePath") or "")
                if source_path:
                    self.assertFalse(
                        Path(source_path).is_absolute() or source_path.startswith("~"),
                        f"sourcePath {source_path!r} is absolute; it is recorded "
                        "relative to the document so the pair relocates together",
                    )
                for recorded in payload.get("sourceClosureFiles") or ():
                    self.assertFalse(
                        Path(str(recorded)).is_absolute(),
                        f"closure file {recorded!r} is absolute",
                    )
                for entry in payload.get("meshExports") or ():
                    out = str((entry or {}).get("out") or "")
                    self.assertTrue(out, "a meshExports entry must name its out")
                    self.assertFalse(
                        Path(out).is_absolute(),
                        f"meshExports out {out!r} is absolute; it is recorded "
                        "relative to the artifact",
                    )

    def test_no_sidecar_carries_choreography(self) -> None:
        # Choreography is the render module beside the document (<name>.step.js),
        # loaded by the viewer and never by a build; a sidecar that still carries
        # an `animation` section was written by a retired writer.
        for sidecar_path in _sidecars():
            payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
            with self.subTest(sidecar=str(sidecar_path.relative_to(REPO_ROOT))):
                self.assertNotIn("animation", payload)


if __name__ == "__main__":
    unittest.main()
