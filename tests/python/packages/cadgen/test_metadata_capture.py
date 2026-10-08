"""Metadata reads verify a fresh closure without retaining native payloads."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
import functools
import json
import os
from pathlib import Path
import threading
import time
import unittest
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import generated_cad_directory

add_repo_path("packages/cadgen/src")
from cadgen.store import surfaces, trees
from cadgen.store.build import build_tree_from_compound
from cadgen.store.objects import iter_objects, object_path
from cadgen.viewer.surfaces import SurfaceSubscribers, pinned_surface_object

WINDOWS_TICK_NS = 15_625_000
# Twice the coarsest tick trees.py knows (FAT's 2 s write time), and a whole
# multiple of every finer one.
SETTLE_OFFSET_NS = 4_000_000_000


class PendingSurface(Future):
    def detach(self):
        pass


class MetadataCapture(unittest.TestCase):
    def setUp(self):
        temp = generated_cad_directory(prefix="metadata-capture-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_COMPONENT_WORKERS": "1",
        }))
        from build123d import Solid

        children = [build_tree_from_compound(Solid.make_box(x, 2, 3), root_name=f"box {x}")[0]
                    for x in (1, 2)]
        links = [{"id": f"o{i}", "tree": tree, "name": f"part {i}",
                  "transform": list(trees.IDENTITY_16)} for i, tree in enumerate(children, 1)]
        self.tree = trees.put_tree({
            "units": "mm", "entryKind": "assembly", "components": {}, "occurrences": [],
            "links": links, "assembly": {"root": {
                "id": "root", "nodeType": "assembly", "children": [
                    {"id": link["id"], "nodeType": "link", "children": []} for link in links],
            }},
        })
        self.geometry, self.payloads = trees.capture_tree(self.tree)
        self.producer = surfaces.producer_identity()
        self.view = surfaces.request_view(self.tree, producer=self.producer)
        self.cid = next(iter(self.view["components"]))
        self.request = {
            "tree": self.tree, "viewId": self.view["viewId"], "producer": self.producer,
            "components": [{"cid": self.cid, "surfaceInput": self.view["components"][self.cid]["surfaceInput"]}],
        }
        self.manager = SurfaceSubscribers()
        self.addCleanup(lambda: [self.manager.cancel(token) for token in list(self.manager._jobs)])
        trees._reset_metadata_capture_cache()
        self.addCleanup(trees._reset_metadata_capture_cache)
        self.settle_store_objects()

    @staticmethod
    def settle_store_objects():
        """Age every object past the resolution its filesystem stamps writes with.

        A cache entry is only remembered once a later write to the object would
        stamp a different mtime, so on a coarse-clock filesystem (Windows: a
        ~15.6 ms tick) whether a hit is admitted at all depends on how long the
        fixture took. These tests are about the fingerprint, not the clock.

        The offset is a whole multiple of every tick in
        ``trees._TIMESTAMP_TICKS_NS``, so aging an object cannot change which
        clock its stamp is attributed to -- only how far past it the read sits.
        Twice the coarsest tick leaves the admission a tick of headroom; an
        offset that is not such a multiple (1.5 s, say) would reclassify a
        whole-second stamp and age it against the wrong resolution.
        """
        for _digest, path in iter_objects():
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns - SETTLE_OFFSET_NS))

    def test_metadata_releases_each_payload_and_native_capture_stays_owned(self):
        live = set()
        observed = []
        read = trees.read_verified_object

        class TrackedBytes(bytes):
            def __new__(cls, value):
                item = super().__new__(cls, value)
                live.add(id(item))
                return item

            def __del__(self):
                live.remove(id(self))

        def tracked(digest):
            self.assertFalse(live, "metadata retained a previous raw object during the next read")
            observed.append(digest)
            return TrackedBytes(read(digest))

        with mock.patch.object(trees, "read_verified_object", side_effect=tracked):
            metadata, payloads = trees.capture_tree(self.tree, retain_payloads=False)
        self.assertEqual(metadata, self.geometry)
        self.assertEqual(payloads, {})
        self.assertFalse(live)
        self.assertEqual(Counter(observed), Counter(self.payloads.keys()))
        metadata["occurrences"][0]["name"] = "private edit"
        owned, captured = trees.capture_tree(self.tree)
        self.assertEqual((owned, captured), (self.geometry, self.payloads))

        from cadgen._internal.component_package import decode_geometry_component
        from build123d import Location

        entry = owned["components"][self.cid]
        first = decode_geometry_component(entry, captured[entry["brep"]])
        second = decode_geometry_component(entry, captured[entry["brep"]])
        self.assertFalse(first.wrapped.IsPartner(second.wrapped))
        previous = second.bounding_box().min.X
        first.move(Location((12, 0, 0)))
        self.assertEqual(second.bounding_box().min.X, previous)
        self.assertEqual(captured, self.payloads)

    def test_resolve_and_polls_recheck_one_verified_complete_closure(self):
        pending = PendingSurface()
        read = trees.read_verified_object
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads, \
             mock.patch("cadgen.daemon.artifacts.submit_artifact", return_value=pending) as submit:
            first = self.manager.resolve(json.dumps(self.request).encode())
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
            reads.reset_mock()
            polled = self.manager.resolve(json.dumps({**self.request, "job": first["job"]}).encode())
            self.assertEqual(polled["job"], first["job"])
            self.assertFalse(reads.call_args_list)
            submit.assert_called_once()
        records = surfaces.derive(self.tree, [self.cid], producer=self.producer)
        pending.set_result(records)
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads:
            ready = self.manager.resolve(json.dumps({**self.request, "job": first["job"]}).encode())
            self.assertEqual(ready["components"][self.cid]["state"], "ready")
            self.assertFalse(reads.call_args_list)
        self.assertEqual(trees.capture_tree(self.tree)[0], self.geometry)

    def test_metadata_cache_is_private_bounded_and_store_root_isolated(self):
        trees._reset_metadata_capture_cache()
        first, _ = trees.capture_tree(self.tree, retain_payloads=False)
        first["occurrences"][0]["name"] = "private mutation"
        second, _ = trees.capture_tree(self.tree, retain_payloads=False)
        self.assertEqual(second, self.geometry)
        self.assertGreater(trees._METADATA_CAPTURE_CACHE_SIZE, 0)
        self.assertLessEqual(trees._METADATA_CAPTURE_CACHE_SIZE, trees._METADATA_CAPTURE_CACHE_CAPACITY)

        with mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(self.root / "empty-store")}):
            with self.assertRaises(FileNotFoundError):
                trees.capture_tree(self.tree, retain_payloads=False)

        trees._reset_metadata_capture_cache()
        with mock.patch.object(trees, "_METADATA_CAPTURE_CACHE_CAPACITY", 1):
            self.assertEqual(trees.capture_tree(self.tree, retain_payloads=False)[0], self.geometry)
            self.assertFalse(trees._METADATA_CAPTURE_CACHE)
            self.assertEqual(trees._METADATA_CAPTURE_CACHE_SIZE, 0)

    def test_concurrent_metadata_readers_share_one_exact_verification(self):
        trees._reset_metadata_capture_cache()
        original = trees.read_verified_object
        first_read = threading.Event()
        release = threading.Event()
        calls = []
        guard = threading.Lock()

        def blocked(digest):
            with guard:
                calls.append(digest)
                first = len(calls) == 1
            if first:
                first_read.set()
                self.assertTrue(release.wait(5))
            return original(digest)

        with mock.patch.object(trees, "read_verified_object", side_effect=blocked), \
             ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(trees.capture_tree, self.tree, retain_payloads=False)]
            self.assertTrue(first_read.wait(5))
            futures.extend(pool.submit(trees.capture_tree, self.tree, retain_payloads=False) for _ in range(7))
            release.set()
            results = [future.result(timeout=10) for future in futures]

        self.assertTrue(all(result == (self.geometry, {}) for result in results))
        self.assertEqual(Counter(calls), Counter(self.payloads.keys()))

    def test_concurrent_metadata_failure_reaches_every_waiter(self):
        trees._reset_metadata_capture_cache()
        original_begin = trees._begin_metadata_capture
        all_joined = threading.Event()
        release = threading.Event()
        count = 0
        guard = threading.Lock()

        def joined(key):
            nonlocal count
            result = original_begin(key)
            with guard:
                count += 1
                if count == 8:
                    all_joined.set()
            return result

        def failed(_digest):
            self.assertTrue(release.wait(5))
            raise ValueError("shared failure")

        with mock.patch.object(trees, "_begin_metadata_capture", side_effect=joined), \
             mock.patch.object(trees, "read_verified_object", side_effect=failed), \
             ThreadPoolExecutor(max_workers=8) as pool:
            futures = [
                pool.submit(trees.capture_tree, self.tree, retain_payloads=False)
                for _ in range(8)
            ]
            self.assertTrue(all_joined.wait(5))
            release.set()
            for future in futures:
                with self.assertRaisesRegex(ValueError, "shared failure"):
                    future.result(timeout=10)

    def test_metadata_cache_reverifies_after_same_address_atomic_replacement(self):
        trees._reset_metadata_capture_cache()
        trees.capture_tree(self.tree, retain_payloads=False)
        entry = next(iter(self.geometry["components"].values()))
        target = object_path(entry["brep"])
        replacement = target.with_name(f".{target.name}.replacement")
        replacement.write_bytes(target.read_bytes())
        os.replace(replacement, target)
        self.settle_store_objects()

        read = trees.read_verified_object
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads:
            self.assertEqual(trees.capture_tree(self.tree, retain_payloads=False)[0], self.geometry)
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
            reads.reset_mock()
            self.assertEqual(trees.capture_tree(self.tree, retain_payloads=False)[0], self.geometry)
            self.assertFalse(reads.call_args_list)

    def test_metadata_entrypoints_read_once_before_producer_selection(self):
        from cadgen.store.view import descriptor_for_view

        trees._reset_metadata_capture_cache()
        read = trees.read_verified_object
        with mock.patch.object(trees, "read_verified_object", wraps=read) as reads:
            def selected(*args):
                self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
                return self.producer

            with mock.patch("cadgen.store.view._select_producer", side_effect=selected):
                view = descriptor_for_view(self.tree)
            self.assertEqual(view["viewId"], self.view["viewId"])
            self.assertEqual(Counter(call.args[0] for call in reads.call_args_list), Counter(self.payloads.keys()))
            reads.reset_mock()
            self.assertEqual(surfaces.request_view(self.tree, producer=self.producer), self.view)
            self.assertFalse(reads.call_args_list)

    def test_missing_or_corrupt_unrequested_geometry_is_rejected_every_time(self):
        records = surfaces.derive(self.tree, [self.cid], producer=self.producer)
        other = next(entry for cid, entry in self.geometry["components"].items() if cid != self.cid)
        target = object_path(other["brep"])
        original = target.read_bytes()
        record = records[self.cid]
        same_size_corruption = bytes([original[0] ^ 1]) + original[1:]
        for malformed in (None, b"corrupt geometry", same_size_corruption):
            with self.subTest(missing=malformed is None):
                trees.capture_tree(self.tree, retain_payloads=False)
                if malformed is None:
                    target.unlink()
                else:
                    target.write_bytes(malformed)
                try:
                    with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("damaged closure admitted")):
                        for call in (
                            lambda: trees.capture_tree(self.tree, retain_payloads=False),
                            lambda: surfaces.request_view(self.tree, producer=self.producer),
                            lambda: surfaces.derive(self.tree, [self.cid], producer=self.producer),
                            lambda: self.manager.resolve(json.dumps(self.request).encode()),
                            lambda: pinned_surface_object(self.tree, record["surfaceInput"], record["object"]),
                        ):
                            with self.assertRaises((OSError, ValueError)):
                                call()
                finally:
                    target.write_bytes(original)
        self.assertEqual(trees.capture_tree(self.tree), (self.geometry, self.payloads))

    def test_the_viewer_verifies_a_tree_once_and_stats_what_each_request_names(self):
        from cadgen.viewer import surfaces as viewer_surfaces

        record = surfaces.derive(self.tree, [self.cid], producer=self.producer)[self.cid]
        surf = object_path(record["object"])
        resolve = lambda: self.manager.resolve(json.dumps(self.request).encode())["components"][self.cid]["state"]
        serve = lambda: pinned_surface_object(self.tree, record["surfaceInput"], record["object"])
        self.assertEqual((resolve(), serve()), ("ready", surf))
        with mock.patch.object(viewer_surfaces, "capture_tree", side_effect=AssertionError("verified again")):
            for _ in range(3):
                self.assertEqual((resolve(), serve()), ("ready", surf))

        # GC or eviction deleting what a request names sends the tree back through the
        # complete verification, which fails as it did before the tree was pinned.
        for digest in (self.geometry["components"][self.cid]["brep"], self.tree):
            target = object_path(digest)
            original = target.read_bytes()
            target.unlink()
            try:
                with mock.patch("cadgen.daemon.artifacts.submit_artifact", side_effect=AssertionError("missing object admitted")):
                    for call in (resolve, serve):
                        with self.assertRaises(FileNotFoundError):
                            call()
            finally:
                target.write_bytes(original)
            self.assertEqual((resolve(), serve()), ("ready", surf))
        surf_bytes = surf.read_bytes()
        surf.unlink()
        try:
            self.assertIsNone(serve())
        finally:
            surf.write_bytes(surf_bytes)

        # A component no request names is not looked at; a derivation still verifies
        # the whole closure before it writes anything.
        other = next(entry for cid, entry in self.geometry["components"].items() if cid != self.cid)
        target = object_path(other["brep"])
        original = target.read_bytes()
        target.unlink()
        try:
            self.assertEqual(serve(), surf)
            with self.assertRaises(FileNotFoundError):
                surfaces.derive(self.tree, [self.cid], producer=self.producer)
        finally:
            target.write_bytes(original)

    def test_damage_inside_one_write_clock_tick_is_never_certified(self):
        """A stamp a later write could reproduce must not certify a cache entry.

        Windows reports ``st_ctime`` as the file's CREATION time, so it does not
        move for a rewrite at all, and stamps the last write from a ~15.6 ms
        timer. A same-size rewrite landing in the tick the verified read observed
        leaves dev, inode, size, mtime and ctime identical, so the cached
        metadata would answer for bytes that no longer hash to their address.
        Linux before 6.13 stamps from its timer interrupt too (10 ms at 100 Hz)
        and keeps every nanosecond digit, so no digit pattern gives the tick away.
        """
        entry = next(value for cid, value in self.geometry["components"].items() if cid != self.cid)
        target = object_path(entry["brep"])
        original = target.read_bytes()
        now = time.time_ns()

        def coarse_stamp(digest, mtime_ns):
            stat = object_path(digest).stat()
            return (digest, stat.st_dev, stat.st_ino, stat.st_size, mtime_ns, 0)

        for clock, mtime_ns in (("windows", now // WINDOWS_TICK_NS * WINDOWS_TICK_NS),
                                ("linux jiffy", now // 1_000_000_000 * 1_000_000_000 + 123_456_789)):
            with self.subTest(clock=clock):
                trees._reset_metadata_capture_cache()
                try:
                    with mock.patch.object(trees, "_object_stamp",
                                           side_effect=functools.partial(coarse_stamp, mtime_ns=mtime_ns)), \
                         mock.patch("time.time_ns", return_value=mtime_ns + 5_000_000):
                        trees.capture_tree(self.tree, retain_payloads=False)
                        target.write_bytes(bytes([original[0] ^ 1]) + original[1:])
                        with self.assertRaises((OSError, ValueError)):
                            trees.capture_tree(self.tree, retain_payloads=False)
                finally:
                    target.write_bytes(original)
        trees._reset_metadata_capture_cache()
        self.settle_store_objects()
        self.assertEqual(trees.capture_tree(self.tree), (self.geometry, self.payloads))

    def test_selected_surface_derivation_reads_only_its_exact_native_payload(self):
        records = surfaces.derive(self.tree, [self.cid], producer=self.producer)
        selected = self.geometry["components"][self.cid]
        other = next(entry for cid, entry in self.geometry["components"].items() if cid != self.cid)
        trees._reset_metadata_capture_cache()
        trees.capture_tree(self.tree, retain_payloads=False)

        graph_read = trees.read_verified_object
        selected_read = surfaces.read_verified_object
        with mock.patch.object(trees, "read_verified_object", wraps=graph_read) as graph_reads, \
             mock.patch.object(surfaces, "read_verified_object", wraps=selected_read) as selected_reads:
            self.assertEqual(
                surfaces.derive(self.tree, [self.cid], force=True, producer=self.producer),
                records,
            )
        self.assertFalse(graph_reads.call_args_list)
        read_digests = [call.args[0] for call in selected_reads.call_args_list]
        self.assertIn(selected["brep"], read_digests)
        self.assertNotIn(other["brep"], read_digests)


class VerifiedIdentityAcrossClaims(unittest.TestCase):
    """A publish's claims carry the identities this process verified forward, and a
    capture reads again only what moved (STORE.md §8, §10)."""

    def setUp(self):
        temp = generated_cad_directory(prefix="verified-claims-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.enterContext(mock.patch.dict(os.environ, {
            "CADGEN_CACHE_DIR": str(self.root / "store"),
            "CADGEN_DAEMON": "0", "CADGEN_COMPONENT_WORKERS": "1",
        }))
        from build123d import Solid

        self.children = [build_tree_from_compound(Solid.make_box(x, 2, 3), root_name=f"box {x}")[0]
                         for x in (1, 2)]
        links = [{"id": f"o{i}", "tree": tree, "name": f"part {i}",
                  "transform": list(trees.IDENTITY_16)} for i, tree in enumerate(self.children, 1)]
        self.tree = trees.put_tree({
            "units": "mm", "entryKind": "assembly", "components": {}, "occurrences": [],
            "links": links, "assembly": {"root": {
                "id": "root", "nodeType": "assembly", "children": [
                    {"id": link["id"], "nodeType": "link", "children": []} for link in links],
            }},
        })
        self.closure = {self.tree: self.tree}
        for child in self.children:
            self.closure.update({child: child, **{entry["brep"]: child for entry in trees.get_tree(child)["components"].values()}})
        trees._reset_metadata_capture_cache()
        self.addCleanup(trees._reset_metadata_capture_cache)
        MetadataCapture.settle_store_objects()

    def reads(self):
        return mock.patch.object(trees, "read_verified_object", wraps=trees.read_verified_object)

    def test_a_publish_claims_what_it_verified_without_reading_it_again(self):
        self.assertTrue(trees.tree_complete(self.tree))
        with self.reads() as reads, mock.patch.object(trees, "claim_object", wraps=trees.claim_object) as claims:
            self.assertTrue(trees.claim_tree(self.tree))
        self.assertFalse(reads.call_args_list, "the closure was verified moments ago")
        self.assertEqual(Counter(call.args[0] for call in claims.call_args_list), Counter(self.closure.keys()))
        # The claims moved every mtime, and the identities moved with them.
        with self.reads() as reads:
            self.assertTrue(trees.tree_complete(self.tree))
            self.assertEqual(trees.capture_tree(self.tree, retain_payloads=False)[0]["tree"], self.tree)
        self.assertFalse(reads.call_args_list)

    def test_a_claims_stamp_is_settled_as_it_is_set_and_recent(self):
        from cadgen.store.objects import claim_object, delete_unclaimed, object_path

        digest = next(iter(trees.get_tree(self.children[0])["components"].values()))["brep"]
        before = time.time_ns()
        self.assertTrue(claim_object(digest))
        stamp = trees._object_stamp(digest)
        self.assertTrue(trees._stamp_is_settled(stamp), "a stamp two ticks back is past the tick it sits in")
        self.assertLess(before - stamp[trees._STAMP_MTIME_NS], 5_000_000_000, "and recent enough for any sweep's window")
        self.assertEqual(delete_unclaimed(object_path(digest), time.time() - 3600), 0)

    @unittest.skipIf(os.name == "nt", "POSIX lets only a file's owner set an explicit time")
    def test_a_claim_on_an_object_another_user_owns_still_claims_it(self):
        # A store several users share: a claim may set this object's time to now, but
        # not to the explicit time it tries first.
        import errno

        from cadgen.store.objects import claim_object, delete_unclaimed, object_path, verified_stamp

        digest = next(iter(trees.get_tree(self.children[0])["components"].values()))["brep"]
        path = object_path(digest)
        stat = path.stat()
        aged_ns = stat.st_mtime_ns - 7200 * 1_000_000_000  # written before any sweep's grace window
        os.utime(path, ns=(stat.st_atime_ns, aged_ns))
        self.assertTrue(trees.tree_complete(self.tree))
        self.assertIsNotNone(verified_stamp(str(path)))
        utime = os.utime

        def owner_only_explicit_times(target, times=None, *, ns=None):
            if times is not None or ns is not None:
                raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), os.fspath(target))
            utime(target)

        with mock.patch("os.utime", side_effect=owner_only_explicit_times):
            self.assertTrue(claim_object(digest))
        self.assertGreater(path.stat().st_mtime_ns, aged_ns, "the claim did not stamp the object")
        self.assertEqual(delete_unclaimed(path, time.time() - 3600), 0, "claimed within the grace window")
        self.assertIsNone(verified_stamp(str(path)), "a stamp of now is not settled as it is set")

    def test_damage_after_or_before_a_claim_is_caught(self):
        from cadgen.store.objects import object_path

        entry = next(iter(trees.get_tree(self.children[1])["components"].values()))
        target = object_path(entry["brep"])
        original = target.read_bytes()
        same_size = bytes([original[0] ^ 1]) + original[1:]

        def rewrite():
            target.write_bytes(same_size)

        def truncate():
            os.truncate(target, 16)

        for when in ("after", "before"):
            for damage in (rewrite, truncate, target.unlink):
                with self.subTest(when=when, damage=damage.__name__):
                    target.write_bytes(original)
                    MetadataCapture.settle_store_objects()
                    trees._reset_metadata_capture_cache()
                    self.assertTrue(trees.tree_complete(self.tree))
                    if when == "before":
                        damage()  # between the verified read and the claim
                        self.assertFalse(trees.claim_tree(self.tree), "the claim's own capture finds it")
                    else:
                        self.assertTrue(trees.claim_tree(self.tree))
                        damage()
                    with self.assertRaises((OSError, ValueError)):
                        trees.capture_tree(self.tree, retain_payloads=False)
                    self.assertFalse(trees.tree_complete(self.tree))
        target.write_bytes(original)

    def test_a_capture_reads_again_only_the_subtree_that_moved(self):
        from cadgen.store.objects import object_path

        self.assertTrue(trees.tree_complete(self.tree))
        # Another process published the first child: its claims moved every
        # stamp of that child's closure and nothing else.
        moved = [digest for digest, child in self.closure.items() if child == self.children[0]]
        for digest in moved:
            path = object_path(digest)
            stat = path.stat()
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns - 8_000_000_000))
        with self.reads() as reads:
            self.assertTrue(trees.tree_complete(self.tree))
        self.assertEqual(sorted(call.args[0] for call in reads.call_args_list), sorted([*moved, self.tree]))
        with self.reads() as reads:
            self.assertTrue(trees.tree_complete(self.tree))
        self.assertFalse(reads.call_args_list)


if __name__ == "__main__":
    unittest.main()
