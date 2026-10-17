"""A view's parts as the browser asks for them: each request binds the geometry, the
producer and the parts it names, and a part the store lacks is derived by one pool job."""
from __future__ import annotations

from concurrent.futures import Future
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest
from unittest import mock

from tests.python.support.inline_artifacts import inline_artifacts
from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

SRC = add_repo_path("packages/cadgen/src")
from cadgen.store import parts
from cadgen.store.build import build_tree_from_compound
from cadgen.store.index import remove_entry
from cadgen.store.objects import object_path
from cadgen.store.view import descriptor_for_view
from cadgen.viewer.parts import FaceMeasures, PartSubscribers, _request


class SubscriberFuture(Future):
    def __init__(self):
        super().__init__()
        self.detached = 0

    def detach(self):
        self.detached += 1


def _row_tree() -> tuple[str, dict]:
    """A tree of three distinct boxes: three parts."""
    from build123d import Compound, Pos, Solid

    boxes = [Pos(4 * n, 0, 0) * Solid.make_box(1 + n, 1, 1) for n in range(3)]
    tree, geometry, _ = build_tree_from_compound(Compound(children=boxes), root_name="row")
    return tree, geometry


class PartRequests(unittest.TestCase):
    def setUp(self):
        self.tmp = generated_cad_directory(prefix="part-http-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        env = mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"), "CADGEN_DAEMON": "0",
            "CADGEN_COMPONENT_WORKERS": "1",
        })
        env.start()
        self.addCleanup(env.stop)
        from build123d import Solid
        box = Solid.make_box(1, 2, 3)
        box.cad_face_ordinal_colors = {1: (1., 0., 0., 1.)}
        self.tree, _, _ = build_tree_from_compound(box, root_name="box")
        self.producer = parts.producer_identity()
        self.view = descriptor_for_view(self.tree, producer=self.producer)
        self.cid, self.entry = next(iter(self.view["components"].items()))
        self.part = self.entry["part"]
        self.request = {
            "tree": self.tree, "viewId": self.view["viewId"], "producer": self.producer,
            "components": [{"cid": self.cid, "part": self.part}],
        }
        self.manager = PartSubscribers()
        self.addCleanup(lambda: [self.manager.cancel(token) for token in list(self.manager._jobs)])

    def resolve(self, request=None):
        return self.manager.resolve(json.dumps(request or self.request).encode())

    def test_a_stored_part_is_ready_without_native_work(self):
        record = parts.derive(self.tree)[self.cid]
        self.assertEqual(record, parts.probe(self.part))
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("unexpected job")), \
             mock.patch.object(parts, "producer_identity", side_effect=AssertionError("kernel forbidden")):
            result = self.resolve()
        # The row is the part's record: the client reads its mesh and its table by it.
        self.assertEqual(result, {"viewId": self.view["viewId"],
                                  "components": {self.cid: {"part": self.part, "state": "ready", "record": record}}})

    def test_a_part_missing_from_the_store_is_pending_until_its_one_job_derives_it(self):
        parts.derive(self.tree)
        # Evicted (STORE.md §8): its record, or an object the record names -- either way
        # the part is not stored.
        losses = {
            "record": lambda record: remove_entry("part", self.part),
            "selector table": lambda record: object_path(record["selectors"]["object"]).unlink(),
            "display mesh": lambda record: object_path(record["glb"]["object"]).unlink(),
        }
        for lost, lose in losses.items():
            with self.subTest(lost=lost):
                lose(parts.probe(self.part))
                future = SubscriberFuture()
                with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future) as submit:
                    pending = self.resolve()
                    self.assertEqual(pending["components"][self.cid],
                                     {"part": self.part, "state": "pending", "job": pending["job"]})
                    self.assertEqual([call.args[0] for call in submit.call_args_list],
                                     [{"kind": "display", "tree": self.tree, "cids": [self.cid], "producer": self.producer}])
                    parts.derive(self.tree)
                    future.set_result({})
                    ready = self.resolve({**self.request, "job": pending["job"]})["components"][self.cid]
                self.assertEqual(ready, {"part": self.part, "state": "ready", "record": parts.probe(self.part)})
                self.assertEqual(future.detached, 1)

    def test_a_request_keys_only_the_parts_it_names_and_never_rebuilds_the_view(self):
        tree, _ = _row_tree()
        view = descriptor_for_view(tree, producer=self.producer)
        cid = sorted(view["components"])[1]
        body = json.dumps({"tree": tree, "viewId": view["viewId"], "producer": self.producer,
                           "components": [{"cid": cid, "part": view["components"][cid]["part"]}]}).encode()
        with mock.patch.object(parts, "view_from_geometry", side_effect=AssertionError("whole view rebuilt")), \
             mock.patch.object(parts, "part_key", wraps=parts.part_key) as keyed:
            selected_view, selected, operation, token = _request(body)
        self.assertEqual(selected_view, {"viewId": view["viewId"]})
        self.assertEqual(selected, {cid: view["components"][cid]["part"]})
        self.assertEqual(operation, {"kind": "display", "tree": tree, "cids": [cid], "producer": self.producer})
        self.assertIsNone(token)
        self.assertEqual(keyed.call_count, 1, "only the part the request names is keyed")

    def test_poll_submits_once_and_completion_rechecks_ready_output(self):
        future = SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future) as submit:
            first = self.resolve()
            token = first["job"]
            request = {**self.request, "job": token}
            self.assertEqual(self.resolve(request)["job"], token)
            self.assertEqual(submit.call_count, 1)
            parts.derive(self.tree)
            future.set_result({})
            result = self.resolve(request)
        self.assertEqual(result["components"][self.cid]["state"], "ready")
        self.assertNotIn("job", result)
        self.assertEqual(future.detached, 1)
        self.assertFalse(self.manager._jobs)

    def test_a_failed_completion_racing_first_lookup_reports_ready_what_it_stored(self):
        from cadgen._internal import tessellate

        tree, _ = _row_tree()
        view = descriptor_for_view(tree, producer=self.producer)
        keys = {cid: entry["part"] for cid, entry in sorted(view["components"].items())}
        cids = list(keys)
        request = {"tree": tree, "viewId": view["viewId"], "producer": self.producer,
                   "components": [{"cid": cid, "part": keys[cid]} for cid in cids]}
        real, failing = tessellate.mesh_component, keys[cids[-1]]

        def mesher(topods, table, face_colors, *, part, **options):
            if part == failing:
                raise tessellate.MeshProductionError("OCCT failed on the component: Standard_Failure")
            return real(topods, table, face_colors, part=part, **options)

        future = SubscriberFuture()

        def submit(operation, **kwargs):
            # The job ends after this poll's first lookup: it stores the first two
            # parts, then raises the last one's failure.
            try:
                with mock.patch.object(tessellate, "mesh_component", side_effect=mesher):
                    parts.derive(tree, operation["cids"], producer=self.producer)
            except tessellate.MeshProductionError as error:
                future.set_exception(error)
            return future

        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=submit):
            rows = self.resolve(request)["components"]
        self.assertEqual({cid: row["state"] for cid, row in rows.items()},
                         {**dict.fromkeys(cids[:-1], "ready"), cids[-1]: "failed"},
                         "what the failed job stored is ready; only what it left missing failed")
        self.assertIn(f"component {cids[-1]}: MeshProductionError: OCCT failed on the component", rows[cids[-1]]["error"])
        for cid in cids[:-1]:
            self.assertEqual(rows[cid]["record"], parts.probe(keys[cid]))
        self.assertIsNone(parts.probe(failing))

    def test_completion_racing_first_lookup_still_returns_ready(self):
        future = SubscriberFuture()
        def submit(*args, **kwargs):
            parts.derive(self.tree)
            future.set_result({})
            return future
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=submit):
            self.assertEqual(self.resolve()["components"][self.cid]["state"], "ready")
        self.assertEqual(future.detached, 1)

    def test_cancellation_detaches_only_its_subscriber_and_unknown_poll_never_restarts(self):
        first, second = SubscriberFuture(), SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=[first, second]) as submit:
            token1 = self.resolve()["job"]
            token2 = self.resolve()["job"]
            self.manager.cancel(token1)
            self.assertEqual((first.detached, second.detached), (1, 0))
            with self.assertRaises(ValueError):
                self.resolve({**self.request, "job": token1})
            self.assertEqual(self.resolve({**self.request, "job": token2})["job"], token2)
            self.assertEqual(submit.call_count, 2)

    def test_subscriber_cannot_be_reused_for_other_inputs_or_store(self):
        future = SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future):
            token = self.resolve()["job"]
        # The same component under another producer: another view, another part.
        other = {**self.producer, "ocp": "other-runtime"}
        view = descriptor_for_view(self.tree, producer=other)
        with self.assertRaises(ValueError):
            self.resolve({"tree": self.tree, "viewId": view["viewId"], "producer": other, "job": token,
                          "components": [{"cid": self.cid, "part": view["components"][self.cid]["part"]}]})
        with mock.patch("cadgen.viewer.parts.store_root", return_value=self.root / "other-store"):
            with self.assertRaises(ValueError):
                self.resolve({**self.request, "job": token})

    def test_missing_completed_output_is_terminal_and_releases_subscriber(self):
        future = SubscriberFuture()
        future.set_result({})
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future) as submit:
            row = self.resolve()["components"][self.cid]
        self.assertEqual(row["state"], "failed")
        self.assertIn("without its requested output", row["error"])
        self.assertEqual(submit.call_count, 1)
        self.assertEqual(future.detached, 1)

    def test_failed_old_producer_stages_a_separate_runtime_view(self):
        producer = {**self.producer, "ocp": "old-runtime"}
        old_view = descriptor_for_view(self.tree, producer=producer)
        request = {**self.request, "viewId": old_view["viewId"], "producer": producer,
                   "components": [{"cid": self.cid, "part": old_view["components"][self.cid]["part"]}]}
        future = SubscriberFuture()
        future.set_exception(ValueError("worker cannot implement the request's pinned producer"))
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future), \
             mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value=self.producer):
            result = self.resolve(request)
        self.assertEqual(result["viewId"], old_view["viewId"])
        self.assertEqual(result["replacementView"]["viewId"], self.view["viewId"])
        self.assertNotEqual(result["viewId"], result["replacementView"]["viewId"])
        self.assertEqual(result["replacementView"]["components"][self.cid]["part"], self.part)
        self.assertEqual(result["components"][self.cid]["code"], "producer-unavailable")

    def test_a_refused_hint_is_replaced_on_the_documents_next_view(self):
        """A kernel upgrade: the document's hint names a producer no worker implements. The
        first view pays one refused job; the next view of the document starts under the
        replacement, starts no job, and the document is re-attested with it."""
        from cadgen.store import view
        from cadgen.store.records import document_entry_for_hash, note_document_tree

        self.addCleanup(view._REPLACED.clear)
        parts.derive(self.tree)
        old = {**self.producer, "build123d": "0.0.1"}
        digest = "e" * 64
        note_document_tree(digest, self.tree, producer=old)
        old_view = descriptor_for_view(self.tree, document_hash=digest)
        self.assertNotEqual(old_view["viewId"], self.view["viewId"])
        request = {**self.request, "viewId": old_view["viewId"], "producer": old,
                   "components": [{"cid": self.cid, "part": old_view["components"][self.cid]["part"]}]}
        future = SubscriberFuture()
        future.set_exception(ValueError("worker cannot implement the request's pinned producer"))
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future), \
             mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value=self.producer):
            self.assertIn("replacementView", self.resolve(request))
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("unexpected job")), \
             mock.patch("cadgen.daemon.artifacts.resolve_artifact", side_effect=AssertionError("unexpected job")):
            again = descriptor_for_view(self.tree, document_hash=digest)
        self.assertEqual(again["viewId"], self.view["viewId"])
        self.assertEqual(document_entry_for_hash(digest)["producer"], self.producer)

    @unittest.skipIf(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0), "POSIX permissions")
    def test_a_view_of_a_hintless_document_never_writes_a_read_only_store(self):
        """README law 2: a read never writes the store. A document entry with no hint is
        viewed from a read-only store as from a writable one."""
        from cadgen.store.records import document_entry_for_hash, note_document_tree

        parts.derive(self.tree)
        digest = "f" * 64
        note_document_tree(digest, self.tree)
        store = self.root / "store"
        before = {path: path.read_bytes() for path in store.rglob("*") if path.is_file()}
        subprocess.run(["chmod", "-R", "a-w", str(store)], check=True)
        self.addCleanup(subprocess.run, ["chmod", "-R", "u+w", str(store)], check=True)
        with mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value=self.producer):
            descriptor = descriptor_for_view(self.tree, document_hash=digest)
            from cadgen.store.view import materialize_parts
            _view, records = materialize_parts(descriptor)
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertEqual(set(records), {self.cid})
        self.assertNotIn("producer", document_entry_for_hash(digest))
        self.assertEqual({path: path.read_bytes() for path in store.rglob("*") if path.is_file()}, before)

    def test_expired_subscriber_is_detached_and_not_reused(self):
        future = SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future):
            token = self.resolve()["job"]
        self.manager._jobs[token]["touched"] -= 121
        with self.assertRaises(ValueError):
            self.resolve({**self.request, "job": token})
        self.assertEqual(future.detached, 1)

    def test_abandoned_browser_expires_without_another_http_request(self):
        future = SubscriberFuture()
        detached = threading.Event()
        future.detach = detached.set
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future), \
             mock.patch("cadgen.viewer.parts.SUBSCRIBER_IDLE_SECONDS", .03):
            self.resolve()
            self.assertTrue(detached.wait(2), "an abandoned subscriber kept native work alive")
        self.assertFalse(self.manager._jobs)

    def test_a_request_not_naming_this_views_parts_exactly_never_submits(self):
        refused = {
            "another view": {"viewId": "f" * 64},
            "no component": {"components": []},
            "another part": {"components": [{"cid": self.cid, "part": "f" * 64 + "-v1"}]},
            "a component field it does not take": {"components": [{"cid": self.cid, "part": self.part, "surfaceInput": "f" * 64}]},
            # No tolerance is the page's to name.
            "a field it does not take": {"tessellation": {"chordTolerance": 5e-4, "angleTolerance": 0.35}},
        }
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("submitted")):
            for name, change in refused.items():
                with self.subTest(name), self.assertRaises(ValueError):
                    self.resolve({**self.request, **change})

    def test_kernel_free_import_and_hinted_descriptor_in_fresh_process(self):
        script = """
import json, sys
class NoKernel:
    def find_spec(self, fullname, *args):
        if fullname.split('.')[0] in {'OCP', 'build123d', 'cadquery'}:
            raise AssertionError('kernel import: ' + fullname)
sys.meta_path.insert(0, NoKernel())
from cadgen.viewer.http_app import create_cad_app
from cadgen.store.view import descriptor_for_view
view = descriptor_for_view(sys.argv[1], producer=json.loads(sys.argv[2]))
print(json.dumps({cid: entry['part'] for cid, entry in view['components'].items()}))
"""
        result = subprocess.run([sys.executable, "-c", script, self.tree, json.dumps(self.producer)],
                                capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(result.stdout), {self.cid: self.part})

    def test_http_routes_enforce_guard_and_serve_each_part_bound_to_its_record(self):
        from urllib.parse import urlencode
        from tests.python.packages.cadgen.viewer.test_http_layer import ServerFixture

        fixture = ServerFixture()
        self.addCleanup(fixture.close)
        body = json.dumps(self.request).encode()
        self.assertEqual(fixture.request("POST", "/__cad/parts", body=body)[0], 403)
        record = parts.derive(self.tree)[self.cid]
        status, _, payload = fixture.request("POST", "/__cad/parts", body=body,
                                             headers={"x-cadgen-viewer": "1"})
        self.assertEqual(status, 200, payload)
        self.assertEqual(json.loads(payload)["components"][self.cid],
                         {"part": self.part, "state": "ready", "record": record})
        for role, suffix, content_type in (("glb", ".glb", "model/gltf-binary"),
                                           ("selectors", ".selectors.json", "application/json")):
            facts = record[role]
            route = f"/__tess_cache/{self.part}{suffix}?object={facts['object']}&maxBytes={facts['byteLength']}"
            with self.subTest(role=role):
                status, headers, got = fixture.request("GET", route)
                self.assertEqual((status, got), (200, object_path(facts["object"]).read_bytes()))
                self.assertEqual({name.lower(): value for name, value in headers.items()}["content-type"], content_type)
                # An object the record does not name is a miss.
                self.assertEqual(fixture.request("GET", route.replace(facts["object"], "f" * 64))[0], 404)
        url = "/__cad/store?" + urlencode({"file": self.tree + "/assembly.json", "producer": json.dumps(self.producer)})
        status, _, payload = fixture.request("GET", url)
        self.assertEqual(status, 200, payload)
        descriptor = json.loads(payload)
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertEqual(descriptor["components"][self.cid]["part"], self.part)

    def test_static_views_keep_distinct_saved_document_bindings(self):
        from cadgen.store.records import note_document_tree
        from cadgen.store.view import view_dir_for

        parts.derive(self.tree)
        first, second = "a" * 64, "b" * 64
        note_document_tree(first, self.tree, producer=self.producer)
        note_document_tree(second, self.tree, producer=self.producer)
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("warm view did native work")):
            one = view_dir_for(self.tree, document_hash=first)
            two = view_dir_for(self.tree, document_hash=second)
            self.assertIsNone(descriptor_for_view("f" * 64))
        self.assertNotEqual(one, two)
        self.assertEqual(json.loads((one / "assembly.json").read_text(encoding="utf-8"))["documentHash"], first)
        self.assertEqual(json.loads((two / "assembly.json").read_text(encoding="utf-8"))["documentHash"], second)

    def test_a_static_view_derives_only_what_the_store_lacks_in_one_job(self):
        from cadgen.store.view import export_view

        tree, geometry = _row_tree()
        cids = sorted(geometry["components"])
        with inline_artifacts() as jobs:
            export_view(tree, self.root / "cold-view", producer=self.producer)
        self.assertEqual([call.args[0] for call in jobs.call_args_list],
                         [{"kind": "display", "tree": tree, "cids": cids, "producer": self.producer}],
                         "every part the store lacks, in ONE job")
        with inline_artifacts() as jobs:
            target = export_view(tree, self.root / "warm-view", producer=self.producer)
        self.assertEqual(jobs.call_count, 0, "a view of stored display data only reads")
        descriptor = json.loads((target / "assembly.json").read_text(encoding="utf-8"))
        remove_entry("part", descriptor["components"][cids[1]]["part"])
        with inline_artifacts() as jobs:
            export_view(tree, self.root / "repaired-view", producer=self.producer)
        self.assertEqual([call.args[0]["cids"] for call in jobs.call_args_list], [[cids[1]]],
                         "a part the store lost is derived alone")
        # Each component's BREP and its part's selector table.
        for cid, entry in descriptor["components"].items():
            record = parts.probe(entry["part"])
            self.assertEqual(entry["selectors"], f"components/{cid}.selectors.json")
            self.assertEqual((target / entry["selectors"]).read_bytes(),
                             object_path(record["selectors"]["object"]).read_bytes())
            self.assertEqual((target / entry["brep"]).read_bytes(), object_path(entry["brepObject"]).read_bytes())

    def test_invalid_optional_hint_is_replaced_without_losing_geometry(self):
        from cadgen.store.index import read_entry, write_entry
        from cadgen.store.records import document_key, note_document_tree
        digest = "c" * 64
        note_document_tree(digest, self.tree)
        entry = read_entry("document", document_key(digest))
        entry["producer"] = {"ocp": "broken"}
        write_entry("document", document_key(digest), entry)
        with mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value=self.producer) as job, \
             mock.patch.object(parts, "producer_identity", side_effect=AssertionError("kernel forbidden")):
            descriptor = descriptor_for_view(self.tree, document_hash=digest)
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertEqual(job.call_args.args[0], {"kind": "producer"})
        self.assertEqual(read_entry("document", document_key(digest))["producer"], self.producer)

    def test_static_export_replaces_an_unavailable_producer_as_a_complete_view(self):
        from cadgen.daemon.artifacts import ArtifactJobError
        from cadgen.store.records import note_document_tree, document_entry_for_hash
        from cadgen.store.view import view_dir_for
        producer = {**self.producer, "ocp": "old-runtime"}
        digest = "d" * 64
        note_document_tree(digest, self.tree, producer=producer)
        old_view = descriptor_for_view(self.tree, producer=producer)
        def run(request):
            if request["kind"] == "producer":
                return self.producer
            if request["producer"] == producer:
                raise ArtifactJobError("worker cannot implement the request's pinned producer")
            return parts.derive(request["tree"], request["cids"], producer=request["producer"])
        with inline_artifacts(run):
            target = view_dir_for(self.tree, document_hash=digest)
        descriptor = json.loads((target / "assembly.json").read_text(encoding="utf-8"))
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertNotEqual(descriptor["viewId"], old_view["viewId"])
        self.assertEqual(target.parent.name, descriptor["viewId"])
        entry = descriptor["components"][self.cid]
        self.assertEqual(entry["part"], self.part)
        self.assertEqual((target / entry["selectors"]).read_bytes(),
                         object_path(parts.probe(self.part)["selectors"]["object"]).read_bytes())
        self.assertEqual(document_entry_for_hash(digest)["producer"], self.producer)



class FaceMeasureRequests(unittest.TestCase):
    """A face's exact area and centroid, which no part carries, measured when a view asks: one
    pool job per face, joined by every request for it, its answer the store's afterwards."""

    def setUp(self):
        self.tmp = generated_cad_directory(prefix="face-measure-")
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(self.tmp.name) / "store"), "CADGEN_DAEMON": "0"})
        env.start()
        self.addCleanup(env.stop)
        from build123d import Solid

        self.body = Solid.make_box(10, 8, 4).cut(Solid.make_cylinder(2, 10))
        self.tree, _, _ = build_tree_from_compound(self.body, root_name="plate")
        self.producer = parts.producer_identity()
        view = descriptor_for_view(self.tree, producer=self.producer)
        self.cid, entry = next(iter(view["components"].items()))
        self.request = {"tree": self.tree, "viewId": view["viewId"], "producer": self.producer, "cid": self.cid,
                        "part": entry["part"], "face": 1}

    def exact(self, face):
        """GProps over the face as the stored component decodes, the live body's twin."""
        from OCP.BRepGProp import BRepGProp
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(self.body.wrapped, TopAbs_FACE, faces)
        props = GProp_GProps()
        BRepGProp.SurfaceProperties_s(faces.FindKey(face), props)
        return props.Mass()

    def ask(self, measures, **change):
        return measures.response(json.dumps({**self.request, **change}).encode())

    def test_each_face_is_measured_once_by_its_job_and_answered_by_the_store_after(self):
        measures = FaceMeasures()
        for face in (1, 7):
            status, payload = self.ask(measures, face=face)
            self.assertEqual(status, 200, payload)
            self.assertEqual(payload["face"], face)
            self.assertAlmostEqual(payload["area"], self.exact(face), places=9)
            self.assertEqual(len(payload["center"]), 3)
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("measured again")):
            status, payload = self.ask(FaceMeasures(), face=7)
        self.assertEqual((status, payload["face"]), (200, 7))
        self.assertAlmostEqual(payload["area"], self.exact(7), places=9)

    def test_a_job_still_running_answers_202_and_every_request_for_the_face_joins_it(self):
        pending = Future()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=pending) as submit:
            measures = FaceMeasures(hold_seconds=0.01, retry_ms=250)
            self.assertEqual(self.ask(measures), (202, {"state": "measuring", "retryMs": 250}))
            self.assertEqual(self.ask(measures), (202, {"state": "measuring", "retryMs": 250}))
            pending.set_result({"area": 2.5, "center": [1.0, 2.0, 3.0]})
            self.assertEqual(self.ask(measures), (200, {"face": 1, "area": 2.5, "center": [1.0, 2.0, 3.0]}))
        submit.assert_called_once()
        self.assertEqual(submit.call_args.args[0], {"kind": "measure", "tree": self.tree, "cid": self.cid, "face": 1})

    def test_a_face_the_component_does_not_have_is_its_jobs_failure(self):
        status, payload = self.ask(FaceMeasures(), face=999)
        self.assertEqual(status, 400)
        self.assertIn("faces, not a face 999", payload["error"])

    def test_a_request_not_naming_this_views_part_and_a_face_never_starts_a_job(self):
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("unexpected job")):
            for change in ({"cid": "0" * 16}, {"part": "f" * 64 + "-v1"}, {"viewId": "0" * 64}, {"face": 0},
                           {"face": True}, {"face": "1"}, {"extra": 1}):
                with self.subTest(change=change), self.assertRaises(ValueError):
                    self.ask(FaceMeasures(), **change)

    def test_the_route_is_guarded_and_answers_the_face(self):
        from tests.python.packages.cadgen.viewer.test_http_layer import ServerFixture

        fixture = ServerFixture()
        self.addCleanup(fixture.close)
        body = json.dumps(self.request).encode()
        self.assertEqual(fixture.request("POST", "/__cad/measure", body=body)[0], 403)
        status, _, payload = fixture.request("POST", "/__cad/measure", body=body, headers={"x-cadgen-viewer": "1"})
        self.assertEqual(status, 200, payload)
        self.assertAlmostEqual(json.loads(payload)["area"], self.exact(1), places=9)


if __name__ == "__main__":
    unittest.main()
