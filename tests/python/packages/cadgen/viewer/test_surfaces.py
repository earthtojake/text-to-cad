"""Owned browser requests bind geometry, producer and exact surface output."""
from __future__ import annotations

from concurrent.futures import Future
import copy
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
from cadgen.store import surfaces
from cadgen.store.build import build_tree_from_compound
from cadgen.store.objects import object_path
from cadgen.viewer.surfaces import SurfaceSubscribers, _request, pinned_surface_object


class SubscriberFuture(Future):
    def __init__(self):
        super().__init__()
        self.detached = 0

    def detach(self):
        self.detached += 1


class SurfaceRequests(unittest.TestCase):
    def setUp(self):
        self.tmp = generated_cad_directory(prefix="surface-http-")
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
        self.producer = surfaces.producer_identity()
        self.view = surfaces.request_view(self.tree, producer=self.producer)
        self.cid, self.entry = next(iter(self.view["components"].items()))
        self.request = {
            "tree": self.tree, "viewId": self.view["viewId"], "producer": self.producer,
            "components": [{"cid": self.cid, "surfaceInput": self.entry["surfaceInput"]}],
        }
        self.manager = SurfaceSubscribers()
        self.addCleanup(lambda: [self.manager.cancel(token) for token in list(self.manager._jobs)])

    def resolve(self, request=None):
        return self.manager.resolve(json.dumps(request or self.request).encode())

    def test_ready_request_never_initializes_native_work_and_serves_only_pinned_bytes(self):
        from cadgen.store import selectors

        record = surfaces.derive(self.tree)[self.cid]
        table = selectors.probe(selectors.selector_key(self.entry["surfaceInput"]))
        self.assertIsNotNone(table, "the surface is derived with its selector table")
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("unexpected job")), \
             mock.patch.object(surfaces, "producer_identity", side_effect=AssertionError("kernel forbidden")):
            result = self.resolve()
            row = result["components"][self.cid]
            self.assertEqual(row["state"], "ready")
            self.assertEqual(row["surfaceObject"], record["object"])
            # The table rides the ready row, served by the same store route as the surface.
            self.assertEqual(row["selectors"], {
                "object": table["object"], "byteLength": table["byteLength"],
                "url": row["url"].replace(record["object"], table["object"]),
            })
            self.assertEqual(pinned_surface_object(self.tree, self.entry["surfaceInput"], record["object"]),
                             object_path(record["object"]))
            self.assertEqual(pinned_surface_object(self.tree, self.entry["surfaceInput"], table["object"]),
                             object_path(table["object"]))
            self.assertIsNone(pinned_surface_object(self.tree, "f" * 64, record["object"]))
            self.assertIsNone(pinned_surface_object(self.tree, "f" * 64, table["object"]))
            self.assertIsNone(pinned_surface_object(self.tree, self.entry["surfaceInput"], "f" * 64))

    def test_a_surface_without_its_table_is_pending_until_the_job_restores_it(self):
        from cadgen.store import selectors
        from cadgen.store.index import remove_entry

        surfaces.derive(self.tree)
        key = selectors.selector_key(self.entry["surfaceInput"])
        remove_entry("selector", key)  # evicted (STORE.md §8): the surface alone is not ready
        future = SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future) as submit:
            pending = self.resolve()
            self.assertEqual(pending["components"][self.cid]["state"], "pending")
            self.assertEqual(submit.call_count, 1)
            surfaces.derive(self.tree)
            future.set_result({})
            ready = self.resolve({**self.request, "job": pending["job"]})["components"][self.cid]
        self.assertEqual(ready["state"], "ready")
        self.assertEqual(ready["selectors"]["object"], selectors.probe(key)["object"])

    def test_request_validates_only_named_surface_inputs_without_rebuilding_whole_view(self):
        surface_input = surfaces.surface_input
        with mock.patch.object(
            surfaces, "_view_from_geometry", side_effect=AssertionError("whole view rebuilt")
        ), mock.patch.object(surfaces, "surface_input", wraps=surface_input) as inputs:
            view, selected, operation, token, canonical = _request(json.dumps(self.request).encode())
        self.assertEqual(view, {"viewId": self.view["viewId"]})
        self.assertEqual(selected, {self.cid: {"surfaceInput": self.entry["surfaceInput"]}})
        self.assertEqual(operation["cids"], [self.cid])
        self.assertIsNone(token)
        self.assertIn(self.cid, canonical["components"])
        self.assertEqual(inputs.call_count, 1)

    def test_poll_submits_once_and_completion_rechecks_ready_output(self):
        future = SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future) as submit:
            first = self.resolve()
            token = first["job"]
            request = {**self.request, "job": token}
            self.assertEqual(self.resolve(request)["job"], token)
            self.assertEqual(submit.call_count, 1)
            surfaces.derive(self.tree)
            future.set_result({})
            result = self.resolve(request)
        self.assertEqual(result["components"][self.cid]["state"], "ready")
        self.assertNotIn("job", result)
        self.assertEqual(future.detached, 1)
        self.assertFalse(self.manager._jobs)

    def test_a_named_tessellation_is_ready_only_with_its_mesh_and_the_row_carries_it(self):
        from cadgen.store import meshes

        tessellation = {"chordTolerance": 5e-4, "angleTolerance": 0.35}
        request = {**self.request, "tessellation": tessellation}
        surfaces.derive(self.tree)
        future = SubscriberFuture()
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future) as submit:
            pending = self.resolve(request)
            self.assertEqual(pending["components"][self.cid]["state"], "pending",
                             "a stored surface without its mesh is not ready")
            [operation] = [call.args[0] for call in submit.call_args_list]
            self.assertEqual(operation["tessellations"], [tessellation], "the job meshes the named tessellation")
            surfaces.derive(self.tree, tessellations=operation["tessellations"])
            future.set_result({})
            ready = self.resolve({**request, "job": pending["job"]})["components"][self.cid]
        key = meshes.tessellation_key(self.entry["surfaceInput"], 5e-4, 0.35)
        self.assertEqual(ready["state"], "ready")
        self.assertEqual(ready["mesh"], meshes.probe(key), "the row is the mesh's probe row")
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("unexpected job")):
            self.assertEqual(self.resolve(request)["components"][self.cid]["mesh"], ready["mesh"])
        for bad in ({"chordTolerance": 5e-4}, {"chordTolerance": 1e-9, "angleTolerance": 0.35}, "fine"):
            with self.subTest(tessellation=bad), self.assertRaises(ValueError):
                self.resolve({**self.request, "tessellation": bad})

    def test_a_failed_completion_racing_first_lookup_reports_ready_what_it_stored(self):
        from build123d import Compound, Pos, Solid
        from cadgen._internal import occt_mesh
        from cadgen.store import meshes

        parts = [Pos(4 * n, 0, 0) * Solid.make_box(1 + n, 1, 1) for n in range(3)]
        tree, _, _ = build_tree_from_compound(Compound(children=parts), root_name="row")
        view = surfaces.request_view(tree, producer=self.producer)
        inputs = {cid: entry["surfaceInput"] for cid, entry in sorted(view["components"].items())}
        cids = list(inputs)
        request = {"tree": tree, "viewId": view["viewId"], "producer": self.producer,
                   "tessellation": {"chordTolerance": 1.5e-3, "angleTolerance": 0.35},
                   "components": [{"cid": cid, "surfaceInput": inputs[cid]} for cid in cids]}
        real, failing = occt_mesh.mesh_component, inputs[cids[-1]]

        def mesher(topods, index, *, surface_input, **options):
            if surface_input == failing:
                raise occt_mesh.MeshProductionError("OCCT did not mesh 1 face(s) of the component: f3")
            return real(topods, index, surface_input=surface_input, **options)

        future = SubscriberFuture()

        def submit(operation, **kwargs):
            # The job ends after this poll's first lookup: it stores the first two
            # components, then raises the last one's failure.
            try:
                with mock.patch.object(occt_mesh, "mesh_component", side_effect=mesher):
                    surfaces.derive(tree, operation["cids"], producer=self.producer,
                                    tessellations=operation["tessellations"])
            except occt_mesh.MeshProductionError as error:
                future.set_exception(error)
            return future

        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=submit):
            rows = self.resolve(request)["components"]
        self.assertEqual({cid: row["state"] for cid, row in rows.items()},
                         {**dict.fromkeys(cids[:-1], "ready"), cids[-1]: "failed"},
                         "what the failed job stored is ready; only what it left missing failed")
        self.assertIn(f"component {cids[-1]}: MeshProductionError: OCCT did not mesh", rows[cids[-1]]["error"])
        for cid in cids[:-1]:
            self.assertEqual(rows[cid]["mesh"], meshes.probe(meshes.tessellation_key(inputs[cid])))

    def test_completion_racing_first_lookup_still_returns_ready(self):
        future = SubscriberFuture()
        def submit(*args, **kwargs):
            surfaces.derive(self.tree)
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
        request = copy.deepcopy(self.request)
        request["job"] = token
        request["components"][0]["expectedSurfaceObject"] = "f" * 64
        with self.assertRaises(ValueError):
            self.resolve(request)
        with mock.patch("cadgen.viewer.surfaces.store_root", return_value=self.root / "other-store"):
            with self.assertRaises(ValueError):
                self.resolve({**self.request, "job": token})

    def test_displayed_mesh_surface_conflict_never_rebinds_selector_output(self):
        surfaces.derive(self.tree)
        request = copy.deepcopy(self.request)
        request["components"][0]["expectedSurfaceObject"] = "f" * 64
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("must fail pinned output")):
            result = self.resolve(request)["components"][self.cid]
        self.assertEqual((result["state"], result["code"]), ("failed", "surface-conflict"))

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
        old_view = surfaces.request_view(self.tree, producer=producer)
        request = {**self.request, "viewId": old_view["viewId"], "producer": producer,
                   "components": [{"cid": self.cid, "surfaceInput": old_view["components"][self.cid]["surfaceInput"]}]}
        future = SubscriberFuture()
        future.set_exception(ValueError("worker cannot implement the request's pinned surface producer"))
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=future), \
             mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value=self.producer):
            result = self.resolve(request)
        self.assertEqual(result["viewId"], old_view["viewId"])
        self.assertEqual(result["replacementView"]["viewId"], self.view["viewId"])
        self.assertNotEqual(result["viewId"], result["replacementView"]["viewId"])
        self.assertEqual(result["components"][self.cid]["code"], "producer-unavailable")

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
             mock.patch("cadgen.viewer.surfaces.SUBSCRIBER_IDLE_SECONDS", .03):
            self.resolve()
            self.assertTrue(detached.wait(2), "an abandoned subscriber kept native work alive")
        self.assertFalse(self.manager._jobs)

    def test_wrong_view_or_component_never_submits(self):
        for field, value in (("viewId", "f" * 64), ("components", []),
                             ("components", [{"cid": self.cid, "surfaceInput": "f" * 64}])):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.resolve({**self.request, field: value})

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
assert view and all('surfaceObject' not in entry for entry in view['components'].values())
"""
        result = subprocess.run([sys.executable, "-c", script, self.tree, json.dumps(self.producer)],
                                capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(SRC)})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_http_routes_enforce_guard_and_serve_exact_surface_binding(self):
        from urllib.parse import urlencode
        from tests.python.packages.cadgen.viewer.test_http_layer import ServerFixture

        fixture = ServerFixture()
        self.addCleanup(fixture.close)
        body = json.dumps(self.request).encode()
        self.assertEqual(fixture.request("POST", "/__cad/surfaces", body=body)[0], 403)
        record = surfaces.derive(self.tree)[self.cid]
        status, _, payload = fixture.request("POST", "/__cad/surfaces", body=body,
                                             headers={"x-cadgen-viewer": "1"})
        self.assertEqual(status, 200, payload)
        row = json.loads(payload)["components"][self.cid]
        self.assertEqual(fixture.request("GET", row["url"])[::2], (200, object_path(record["object"]).read_bytes()))
        self.assertEqual(fixture.request("GET", row["selectors"]["url"])[::2],
                         (200, object_path(row["selectors"]["object"]).read_bytes()))
        wrong = row["url"].replace(record["object"], "f" * 64)
        self.assertEqual(fixture.request("GET", wrong)[0], 404)
        url = "/__cad/store?" + urlencode({"file": self.tree + "/assembly.json", "surfaceProducer": json.dumps(self.producer)})
        status, _, payload = fixture.request("GET", url)
        self.assertEqual(status, 200, payload)
        descriptor = json.loads(payload)
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertNotIn("surfaceObject", descriptor["components"][self.cid])

    def test_static_views_keep_distinct_saved_document_bindings(self):
        from cadgen.store.records import note_document_tree
        from cadgen.store.view import view_dir_for, descriptor_for_view

        surfaces.derive(self.tree)
        first, second = "a" * 64, "b" * 64
        note_document_tree(first, self.tree, surface_producer=self.producer)
        note_document_tree(second, self.tree, surface_producer=self.producer)
        with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("warm view did native work")):
            one = view_dir_for(self.tree, document_hash=first)
            two = view_dir_for(self.tree, document_hash=second)
            self.assertIsNone(descriptor_for_view("f" * 64))
        self.assertNotEqual(one, two)
        self.assertEqual(json.loads((one / "assembly.json").read_text(encoding="utf-8"))["documentHash"], first)
        self.assertEqual(json.loads((two / "assembly.json").read_text(encoding="utf-8"))["documentHash"], second)

    def test_a_static_view_deals_its_missing_surfaces_across_the_pool(self):
        from build123d import Compound, Pos, Solid
        from cadgen.store.view import export_view

        parts = [Pos(4 * n, 0, 0) * Solid.make_box(1 + n, 1, 1) for n in range(3)]
        tree, geometry, _ = build_tree_from_compound(Compound(children=parts), root_name="row")
        with inline_artifacts() as jobs, mock.patch("cadgen.daemon.broker.job_limit", return_value=2), \
                mock.patch("cadgen.daemon.artifacts.SURFACES_PER_STARTED_WORKER", 1):
            target = export_view(tree, self.root / "row-view", producer=self.producer)
        dealt = [call.args[0]["cids"] for call in jobs.call_args_list if call.args[0]["kind"] == "surfaces"]
        self.assertEqual(len(dealt), 2, "one job per CPU slot the pool runs at once")
        self.assertEqual(sorted(cid for cids in dealt for cid in cids), sorted(geometry["components"]))
        descriptor = json.loads((target / "assembly.json").read_text(encoding="utf-8"))
        self.assertTrue(all(entry.get("surf") for entry in descriptor["components"].values()))

    def test_invalid_optional_hint_is_replaced_without_losing_geometry(self):
        from cadgen.store.index import read_entry, write_entry
        from cadgen.store.records import note_document_tree
        from cadgen.store.view import descriptor_for_view
        digest = "c" * 64
        note_document_tree(digest, self.tree)
        entry = read_entry("document", digest)
        entry["surfaceProducer"] = {"ocp": "broken"}
        write_entry("document", digest, entry)
        with mock.patch("cadgen.daemon.artifacts.resolve_artifact", return_value=self.producer) as job, \
             mock.patch.object(surfaces, "producer_identity", side_effect=AssertionError("kernel forbidden")):
            descriptor = descriptor_for_view(self.tree, document_hash=digest)
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertEqual(job.call_args.args[0], {"kind": "producer"})
        self.assertEqual(read_entry("document", digest)["surfaceProducer"], self.producer)

    def test_static_export_replaces_an_unavailable_producer_as_a_complete_view(self):
        from cadgen.daemon.artifacts import ArtifactJobError
        from cadgen.store.records import note_document_tree, document_entry_for_hash
        from cadgen.store.view import view_dir_for
        producer = {**self.producer, "ocp": "old-runtime"}
        digest = "d" * 64
        note_document_tree(digest, self.tree, surface_producer=producer)
        old_view = surfaces.request_view(self.tree, producer=producer)
        def run(request):
            if request["kind"] == "producer":
                return self.producer
            if request["producer"] == producer:
                raise ArtifactJobError("worker cannot implement the request's pinned surface producer")
            return surfaces.derive(request["tree"], request["cids"], producer=request["producer"])
        with inline_artifacts(run):
            target = view_dir_for(self.tree, document_hash=digest)
        descriptor = json.loads((target / "assembly.json").read_text(encoding="utf-8"))
        self.assertEqual(descriptor["viewId"], self.view["viewId"])
        self.assertNotEqual(descriptor["viewId"], old_view["viewId"])
        self.assertEqual(target.parent.name, descriptor["viewId"])
        entry = descriptor["components"][self.cid]
        self.assertEqual(entry["surfaceInput"], self.entry["surfaceInput"])
        self.assertEqual((target / entry["surf"]).read_bytes(), object_path(entry["surfaceObject"]).read_bytes())
        self.assertEqual(document_entry_for_hash(digest)["surfaceProducer"], self.producer)


if __name__ == "__main__":
    unittest.main()
