"""Reopened documents reuse proof; changed inputs and broken caches recheck."""

from collections import OrderedDict
from contextlib import ExitStack
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cadgen.viewer import reconstruction as host
from cadgen.viewer import reconstruction_cache as disk
from cadgen.store.paths import StoreUnwritableError
from cadgen.store.tess_cache import write_tessellation_cache


class PersistentCacheTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory()))
        self.stack.enter_context(
            patch.dict(
                os.environ,
                {
                    "CADGEN_CACHE_DIR": str(self.root / "cache"),
                    "CADGEN_RECONSTRUCTION_EXPERIMENT": "1",
                    "CADGEN_MESH_CACHE": "1",
                },
            )
        )
        self.brep = self.root / "part.brep"
        self.brep.write_bytes(b"geometry")
        self.stack.enter_context(patch.object(host, "result_tree", return_value="tree"))
        self.stack.enter_context(
            patch.object(
                host, "result_descriptor", return_value={"components": {"c": {}}}
            )
        )
        self.stack.enter_context(
            patch.object(host, "virtual_store_asset", return_value=(self.brep, ""))
        )
        self.stack.enter_context(patch.object(host, "_cache", OrderedDict()))
        self.stack.enter_context(patch.object(host, "_cache_bytes", 0))
        self.payload = json.dumps(
            {
                "status": "verified",
                "proof": {"passed": True},
                "steps": [{"id": "base"}],
                "reference": {},
            }
        ).encode()
        self.run = self.stack.enter_context(
            patch.object(host, "_run", return_value=self.payload)
        )
        self.request = {
            "tree": "tree",
            "component": "c",
            "recipe": {"depth": 5},
            "preview": False,
        }

    def request_result(self):
        return host.reconstruct(
            str(self.root), "part.step", json.dumps(self.request).encode()
        )

    def clear_memory(self):
        host._cache.clear()
        host._cache_bytes = 0

    def test_reopen_reuses_disk_and_a_new_process_can_read_playback(self):
        self.assertEqual(self.request_result()["frameCount"], 1)
        self.clear_memory()
        self.request["preview"] = True
        self.assertEqual(self.request_result()["steps"], [{"id": "base"}])
        self.assertEqual(self.run.call_count, 1)
        key = disk.cache_key(self.brep, self.request["recipe"])
        code = "from cadgen.viewer.reconstruction_cache import read_preview; import sys; sys.stdout.buffer.write(read_preview(sys.argv[1], 25165824))"
        output = subprocess.check_output([sys.executable, "-c", code, key], timeout=15)
        self.assertEqual(output, self.payload)

    def test_geometry_recipe_and_interpreter_changes_miss(self):
        self.request_result()
        self.brep.write_bytes(b"different geometry")
        self.request_result()
        self.request["recipe"]["depth"] = 6
        self.request_result()
        with patch.object(disk, "version", return_value="new-kernel"):
            self.request_result()
        self.assertEqual(self.run.call_count, 4)
        original_key = disk.cache_key(self.brep, self.request["recipe"])
        original_read = Path.read_bytes

        def changed_worker(path):
            return (
                b"new interpreter"
                if path.name == "step_reconstruction.py"
                else original_read(path)
            )

        with patch.object(Path, "read_bytes", changed_worker):
            self.assertNotEqual(
                disk.cache_key(self.brep, self.request["recipe"]), original_key
            )

    def test_corrupt_missing_or_oversize_disk_entries_are_misses(self):
        key = disk.cache_key(self.brep, self.request["recipe"])
        for data in (b"broken", b"x" * 65 + self.payload, b"{}"):
            write_tessellation_cache(key, data)
            self.assertIsNone(disk.read_preview(key, host.MAX_OUTPUT))
        for payload in (
            b"[]",
            b'{"status":"verified","proof":false}',
            b'{"status":"unverified"}',
        ):
            write_tessellation_cache(
                key, sha256(payload).hexdigest().encode() + b"\n" + payload
            )
            self.assertIsNone(disk.read_preview(key, host.MAX_OUTPUT))
        disk.write_preview(key, self.payload)
        self.assertIsNone(disk.read_preview(key, 1))
        self.assertIsNone(disk.read_preview("reconstruction-missing", host.MAX_OUTPUT))

    def test_unwritable_cache_does_not_fail_verified_result(self):
        with patch.object(
            disk,
            "write_tessellation_cache",
            side_effect=StoreUnwritableError("read only"),
        ):
            self.assertEqual(self.request_result()["status"], "verified")
        self.clear_memory()
        self.request_result()
        self.assertEqual(self.run.call_count, 2)

    def test_failed_verification_is_not_persisted(self):
        self.run.return_value = b'{"status":"unverified","proof":{"passed":false}}'
        self.request_result()
        self.clear_memory()
        self.request_result()
        self.assertEqual(self.run.call_count, 2)

    def test_disk_cache_never_bypasses_current_document_check(self):
        self.request_result()
        self.clear_memory()
        with patch.object(host, "result_tree", return_value="changed"):
            with self.assertRaisesRegex(ValueError, "STEP changed"):
                self.request_result()
        self.assertEqual(self.run.call_count, 1)


if __name__ == "__main__":
    unittest.main()
