"""Selector-manifest entryKind stamping in the GLB STEP_topology writer."""

from __future__ import annotations

import json
import unittest

from cadgen._internal.glb import _GlbBuilder
from cadgen._internal.glb_topology import STEP_TOPOLOGY_EXTENSION
from cadgen.selector_types import SelectorBundle


def _decode_view(builder: _GlbBuilder, view_index: int) -> dict[str, object]:
    views = builder.json["bufferViews"]
    assert isinstance(views, list)
    view = views[view_index]
    start = int(view["byteOffset"])
    length = int(view["byteLength"])
    return json.loads(bytes(builder.binary[start : start + length]).decode("utf-8"))


def _bundle_manifest(*, assembly: bool) -> dict[str, object]:
    manifest: dict[str, object] = {
        "cadPath": "tmp/sample",
        "stepPath": "tmp/sample.step",
        "stepHash": "hash-123",
        "sourceKind": "step",
        "sourcePath": "tmp/sample.step",
        "bbox": {"min": [0.0, 0.0, 0.0], "max": [1.0, 1.0, 1.0]},
        "stats": {"occurrenceCount": 3, "leafOccurrenceCount": 2},
    }
    if assembly:
        manifest["assembly"] = {"id": "o1"}
    return manifest


class GlbSelectorManifestEntryKindTests(unittest.TestCase):
    def _write_step_topology(self, manifest: dict[str, object]) -> tuple[dict[str, object], dict[str, object]]:
        builder = _GlbBuilder()
        builder.add_step_topology(SelectorBundle(manifest=manifest), include_selector_topology=True)
        extensions = builder.json["extensions"]
        assert isinstance(extensions, dict)
        extension = extensions[STEP_TOPOLOGY_EXTENSION]
        selector_manifest = _decode_view(builder, extension["selectorView"])
        return extension, selector_manifest

    def test_assembly_manifest_stamps_selector_entry_kind(self) -> None:
        extension, selector_manifest = self._write_step_topology(_bundle_manifest(assembly=True))

        self.assertEqual("assembly", extension["entryKind"])
        self.assertEqual("assembly", selector_manifest["entryKind"])
        self.assertNotIn("assembly", selector_manifest)

    def test_part_manifest_stamps_selector_entry_kind(self) -> None:
        extension, selector_manifest = self._write_step_topology(_bundle_manifest(assembly=False))

        self.assertEqual("part", extension["entryKind"])
        self.assertEqual("part", selector_manifest["entryKind"])


if __name__ == "__main__":
    unittest.main()
