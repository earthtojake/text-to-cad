"""A build's preview revision (STORE.md §9b): the result tree the moment the result exists,
its annotations as one object, and its parts as the build pool's one job derives them, all
before the STEP is published; the saved file's parts are the preview's; its catalog row
carries what the annotations carried, by the same tokens; and the viewer's reads of a
preview open no record and import no kernel."""
from __future__ import annotations

import contextlib
import io
import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.tmp_root import generated_cad_directory

MODEL = '''
import cadgen
from cadgen import revolute, step
from cadgen import build123d as bd

MATERIALS = {"definitions": {"paint": {"baseColor": "#336699"}},
             "assignments": [{"targets": ["#arm"], "material": "paint"}]}


def swing_open(t, m):
    m.get("#arm").rotate((0, 0, 1), 45 * t, (0, 0, 6))


@step(kinematics={"mates": [revolute("swing", parent="#base", child="#arm", origin=(0, 0, 6),
                                      direction=(0, 0, 1), limits=(0, 90))]},
      materials=MATERIALS, animation={"open": cadgen.clip(swing_open, duration=2, label="Open")})
def part():
    base = bd.Box(30, 20, 4)
    base.label = "base"
    arm = bd.Pos(10, 0, 6) * bd.Box(16, 4, 4)
    arm.label = "arm"
    return bd.Compound(children=[base, arm])


if __name__ == "__main__":
    part()
'''

UNRESOLVABLE = MODEL.replace('m.get("#arm")', 'm.get("#nothing")')

# The viewer's reads of a preview, run where a native import is an error and a record read
# too (STORE.md §2, property 2): the status, the preview tree's view and its annotations.
READS = '''
import importlib.abc, json, sys


class NoNative(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in {"OCP", "build123d"}:
            raise AssertionError("native import: " + fullname)


sys.meta_path.insert(0, NoNative())
import cadgen.store.index as index
import cadgen.store.records as records

real = index.read_entry


def guarded(kind, key):
    if kind in ("model", "output", "provenance"):
        raise AssertionError("a reader consulted index/" + kind)
    return real(kind, key)


index.read_entry = records.read_entry = guarded
from cadgen.viewer.preview import preview_status
from cadgen.viewer.store_paths import preview_annotations, virtual_store_asset

output, tree, producer, annotations, store, parts = sys.argv[1:7]
producer, parts = json.loads(producer), json.loads(parts)
job = {"id": "e:job-1", "epoch": "e", "sequence": 1, "tool": "run", "storeRoot": store, "outputs": [output],
       "state": "building", "subject": "/private/part.py",
       "previews": {output: {"tree": tree, "producer": producer, "parts": parts, "complete": True}},
       "annotations": {output: {"tree": tree, "object": annotations}}}
status = preview_status(output, jobs=[job])
assert status["preview"] == {"tree": tree, "producer": producer, "parts": parts, "complete": True,
                             "annotations": annotations}, status
payload, _kind = virtual_store_asset(tree + "/assembly.json", producer=producer)
descriptor = json.loads(payload)
assert {cid: entry["part"] for cid, entry in descriptor["components"].items()} == parts, descriptor
assert json.loads(preview_annotations(annotations))["tree"] == tree
assert not any(name.split(".")[0] in {"OCP", "build123d"} for name in sys.modules)
print("ok")
'''


class PreviewRevision(unittest.TestCase):
    def setUp(self) -> None:
        temporary = generated_cad_directory(prefix="preview-revision-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.model = self.root / "part.py"
        self.step = self.root / "part.step"
        self.store = self.root / "store"
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.store), "CADGEN_DAEMON": "0",
                                           "CADGEN_JOBS": "1"})
        env.start()
        self.addCleanup(env.stop)

    def build(self, source: str = MODEL) -> tuple[int, list[dict]]:
        """Run the model in this process, with an event sink that notes at each event
        whether the STEP exists yet: ``(exit code, events)``."""
        from cadgen.cli._run_model import run_model_argv
        from cadgen.daemon import executors

        self.model.write_text(source, encoding="utf-8")
        events: list[dict] = []
        executors.set_event_sink(lambda event: events.append({**event, "stepOnDisk": self.step.is_file()}))
        self.addCleanup(executors.set_event_sink, None)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_model_argv([str(self.model)])
        self.output = output.getvalue()
        return code, events

    @staticmethod
    def _of(events: list[dict], field: str) -> list[dict]:
        return [event for event in events if field in event]

    def test_the_preview_names_its_parts_before_the_step_is_written_and_the_saved_file_shares_them(self):
        from cadgen.daemon import artifacts
        from cadgen.store import parts
        from cadgen.store.records import document_entry_for_hash
        from cadgen.store.view import descriptor_for_view

        with mock.patch.object(artifacts, "submit_artifact", wraps=artifacts.submit_artifact) as submitted:
            code, events = self.build()
        self.assertEqual(code, 0, self.output)
        previews, annotations, saved = (self._of(events, field) for field in ("preview", "annotations", "saved"))
        self.assertTrue(previews and annotations and saved, events)
        # The tree first; its annotations, and its parts once the pool's job is done, whichever
        # is first; then the save: no STEP on disk before it.
        self.assertLess(events.index(previews[0]), events.index(annotations[0]))
        self.assertLess(max(events.index(previews[-1]), events.index(annotations[0])), events.index(saved[0]))
        self.assertFalse(any(event["stepOnDisk"] for event in previews + annotations))
        self.assertTrue(saved[0]["stepOnDisk"])
        tree = previews[0]["preview"]["tree"]
        self.assertTrue(all(event["preview"]["tree"] == tree for event in previews), "one result tree")
        keys, producer = parts.part_keys(tree)
        final = previews[-1]["preview"]
        self.assertEqual((final["parts"], final["complete"], final["producer"]), (keys, True, producer))
        # Stored parts first, then the job's: the map only grows.
        sizes = [len(event["preview"]["parts"]) for event in previews]
        self.assertEqual(sizes, sorted(sizes))
        jobs = [call.args[0] for call in submitted.call_args_list]
        [job] = [job for job in jobs if job["kind"] == "display"]
        self.assertEqual((job["tree"], sorted(job["cids"])), (tree, sorted(keys)), "one job derives the build's parts")
        # The file is an export of the same tree, and verified against it.
        self.assertEqual([(job["kind"], job["tree"]) for job in jobs if job["kind"] != "display"],
                         [("export", tree), ("verify", tree)])
        # The saved document names the same parts (law 20): nothing is derived or fetched twice.
        digest = saved[0]["saved"]["documentHash"]
        document = descriptor_for_view(document_entry_for_hash(digest)["tree"], document_hash=digest)
        self.assertEqual({entry["part"] for entry in document["components"].values()}, set(keys.values()))

    def test_the_annotations_are_what_the_saved_files_row_carries_by_the_same_tokens(self):
        from cadgen._internal.preview_revision import read_annotations
        from cadgen._internal.source_sidecar import appearance_digest, source_sidecar_path
        from cadgen.store.objects import object_path
        from cadgen.store.records import read_record
        from cadgen.viewer.scanner import catalog_entry

        code, events = self.build()
        self.assertEqual(code, 0, self.output)
        announced = self._of(events, "annotations")[-1]["annotations"]
        self.assertEqual(announced["tree"], self._of(events, "preview")[-1]["preview"]["tree"])
        payload = read_annotations(announced["object"])
        self.assertIsNotNone(payload)
        self.assertTrue(object_path(announced["object"]).is_file(), "artifact side: one object")
        row = catalog_entry(str(self.step))
        for field in ("articulation", "display", "animation"):
            self.assertIsNotNone(payload[field], field)
            self.assertEqual(payload[field], row[field], field)
        # The row carries its appearance as a digest; the object carries the block it digests.
        self.assertEqual(appearance_digest(payload["appearance"]), row["appearanceHash"])
        # Nothing durable names the object: not the record, not the sidecar.
        self.assertNotIn(announced["object"], json.dumps(read_record(self.model)))
        self.assertNotIn(announced["object"], Path(source_sidecar_path(self.step)).read_text(encoding="utf-8"))

    def test_a_build_bakes_its_clips_once_for_the_preview_and_the_sidecar(self):
        """The file is written from the result tree the preview resolves against, so its
        sidecar carries the very keyframes the annotations do: baked once, not twice."""
        from cadgen._internal import animation_bake

        with mock.patch.object(animation_bake, "bake_document_animation",
                               wraps=animation_bake.bake_document_animation) as bake:
            code, events = self.build()
        self.assertEqual(code, 0, self.output)
        self.assertTrue(self._of(events, "annotations") and self._of(events, "saved"))
        self.assertEqual(1, bake.call_count)

    def test_the_viewers_reads_of_a_preview_open_no_record_and_import_no_kernel(self):
        code, events = self.build()
        self.assertEqual(code, 0, self.output)
        preview = self._of(events, "preview")[-1]["preview"]
        annotations = self._of(events, "annotations")[-1]["annotations"]["object"]
        result = subprocess.run(
            [sys.executable, "-c", READS, str(self.step), preview["tree"], json.dumps(preview["producer"]),
             annotations, str(self.store), json.dumps(preview["parts"])],
            env=os.environ.copy(), text=True, capture_output=True, timeout=120)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stdout.strip(), "ok")

    def test_a_declaration_that_fails_to_resolve_fails_the_build_after_its_preview(self):
        code, events = self.build(UNRESOLVABLE)
        self.assertNotEqual(code, 0)
        self.assertIn("#nothing", self.output)
        previews = self._of(events, "preview")
        self.assertTrue(previews and previews[-1]["preview"]["complete"], "the preview stands, under the failure")
        self.assertFalse(self._of(events, "annotations") or self._of(events, "saved"))
        self.assertFalse(self.step.exists())

    def test_without_a_display_producer_the_preview_names_its_tree_and_no_parts(self):
        with mock.patch("cadgen.store.parts.producer_identity", side_effect=ValueError("unknown kernel")):
            code, events = self.build()
        self.assertEqual(code, 0, self.output)
        previews = [event["preview"] for event in self._of(events, "preview")]
        self.assertTrue(previews)
        self.assertTrue(all(preview["producer"] is None and preview["parts"] == {} and preview["complete"] is False
                            for preview in previews), previews)


if __name__ == "__main__":
    unittest.main()
