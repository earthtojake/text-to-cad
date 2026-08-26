"""Artifact build failures preserve the runtime provenance needed to compare CLI and Viewer runs."""

from __future__ import annotations

import os
import pathlib
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from server_py import backend, cadgen_bridge, worker_client  # noqa: E402


class ArtifactRuntimeDiagnosticTests(unittest.TestCase):
    def test_bridge_labels_warm_worker_results(self):
        with mock.patch.object(worker_client, "run_cadgen", return_value={"ok": True}):
            result = cadgen_bridge.run_cadgen("cadgen.dxf_artifact", [], os.getcwd())
        self.assertEqual(result["_viewerBackendMode"], "warm-worker")

    def test_bridge_labels_cold_fallback_results(self):
        with mock.patch.object(worker_client, "run_cadgen", side_effect=worker_client._WorkerError("offline")), \
                mock.patch.object(cadgen_bridge, "run_cadgen_cold", return_value={"ok": False, "error": "failed"}):
            result = cadgen_bridge.run_cadgen("cadgen.dxf_artifact", [], os.getcwd())
        self.assertEqual(result["_viewerBackendMode"], "cold-subprocess")

    def test_failure_names_python_node_and_backend_mode(self):
        result = {
            "ok": False,
            "error": "Node builder failed with exit code 1: dxf-artifact.mjs",
            "_viewerBackendMode": "warm-worker",
        }
        with mock.patch.object(backend.cadgen_bridge, "run_cadgen", return_value=result), \
                mock.patch.dict(os.environ, {"VIEWER_CAD_NODE": r"C:\\node\\node.exe"}, clear=False):
            built = backend.LocalAssetBackend()._run_artifact_build(
                "cadgen.dxf_artifact",
                ["--source-path", "drawing.dxf.py"],
                os.getcwd(),
                force=False,
                error_label="DXF render artifact build failed",
            )

        self.assertFalse(built["ok"])
        self.assertIn(f"Python={sys.executable}", built["error"])
        self.assertIn(r"Node=C:\\node\\node.exe", built["error"])
        self.assertIn("backend=warm-worker", built["error"])


if __name__ == "__main__":
    unittest.main()
