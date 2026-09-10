"""The opt-in host refuses stale/arbitrary geometry; the kernel proves real solids."""

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.viewer import reconstruction as host


def circle(radius):
    return {
        "kind": "boundary",
        "edges": [
            {
                "reversed": False,
                "curve": {
                    "kind": "circle",
                    "origin": [0, 0, 0],
                    "xdir": [1, 0, 0],
                    "ydir": [0, 1, 0],
                    "radius": radius,
                    "range": [0, 6.283185307179586],
                },
            }
        ],
    }


def recipe():
    return {
        "schema": 1,
        "units": "mm",
        "output": "cut",
        "steps": [
            {
                "id": "outer",
                "kind": "sketch",
                "label": "Sketch 1",
                "dependsOn": [],
                "profile": circle(10),
            },
            {
                "id": "base",
                "kind": "extrude",
                "label": "Base",
                "dependsOn": ["outer"],
                "sketch": "outer",
                "direction": [0, 0, 5],
            },
            {
                "id": "inner",
                "kind": "sketch",
                "label": "Sketch 2",
                "dependsOn": [],
                "profile": circle(3),
            },
            {
                "id": "cut",
                "kind": "cut",
                "label": "Cut",
                "dependsOn": ["base", "inner"],
                "input": "base",
                "sketch": "inner",
                "direction": [0, 0, 5],
            },
        ],
    }


class ReplayTests(unittest.TestCase):
    def test_replay_matches_independent_cylinders_and_preserves_intermediates(self):
        from cadgen._internal.step_reconstruction import replay, compare, cut, mass
        from OCP.BRepPrimAPI import BRepPrimAPI_MakeCylinder

        target = cut(
            BRepPrimAPI_MakeCylinder(10, 5).Shape(),
            BRepPrimAPI_MakeCylinder(3, 5).Shape(),
        )
        final, states = replay(recipe())
        self.assertTrue(compare(target, final)["passed"])
        self.assertIsNone(states[0]["shape"])
        self.assertGreater(mass(states[1]["shape"]), mass(final))
        self.assertEqual(mass(states[1]["shape"]), mass(states[2]["shape"]))
        changed = recipe()
        changed["steps"][1]["direction"] = [0, 0, 5.1]
        wrong, _ = replay(changed)
        self.assertFalse(compare(target, wrong)["passed"])

    def test_bad_dependencies_and_unbounded_inputs_are_rejected(self):
        from cadgen._internal.step_reconstruction import replay

        for change in [
            lambda r: r["steps"][-1].update(dependsOn=[]),
            lambda r: r.update(output="outer"),
            lambda r: r["steps"][1].update(direction=[0, 0, float("nan")]),
            lambda r: r["steps"][1].update(kind="exec"),
        ]:
            value = recipe()
            change(value)
            with self.assertRaises(ValueError):
                replay(value)


class HostTests(unittest.TestCase):
    def test_experiment_disabled_and_oversize_input(self):
        with patch.dict(os.environ, {"CADGEN_RECONSTRUCTION_EXPERIMENT": "0"}):
            with self.assertRaisesRegex(ValueError, "not enabled"):
                host.reconstruct("/tmp", "part.step", b"{}")
        with patch.dict(os.environ, {"CADGEN_RECONSTRUCTION_EXPERIMENT": "1"}):
            with self.assertRaisesRegex(ValueError, "size limit"):
                host.reconstruct("/tmp", "part.step", b" " * (host.MAX_INPUT + 1))

    def test_stale_and_foreign_components_do_not_start_worker(self):
        with (
            tempfile.TemporaryDirectory() as root,
            patch.dict(os.environ, {"CADGEN_RECONSTRUCTION_EXPERIMENT": "1"}),
            patch.object(host.subprocess, "run") as run,
        ):
            with patch.object(host, "result_tree", return_value="current"):
                with self.assertRaisesRegex(ValueError, "STEP changed"):
                    host.reconstruct(
                        root, "part.step", json.dumps({"tree": "old"}).encode()
                    )
                with patch.object(
                    host, "result_descriptor", return_value={"components": {}}
                ):
                    with self.assertRaisesRegex(ValueError, "does not belong"):
                        host.reconstruct(
                            root,
                            "part.step",
                            json.dumps(
                                {"tree": "current", "component": "foreign"}
                            ).encode(),
                        )
            run.assert_not_called()

    def test_viewer_adapter_does_not_import_kernel(self):
        self.assertNotIn("from OCP", Path(host.__file__).read_text())


class CacheTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        env = patch.dict(os.environ, {"CADGEN_CACHE_DIR": directory.name})
        env.start()
        self.addCleanup(env.stop)

    def test_summary_then_preview_reuses_verified_geometry_and_changed_recipe_rechecks(
        self,
    ):
        with tempfile.TemporaryDirectory() as root:
            models = Path(root) / "models"
            models.mkdir()
            brep = models / "part.brep"
            brep.write_bytes(b"fixture")
            result = {
                "status": "verified",
                "proof": {"passed": True},
                "steps": [{}, {}],
                "reference": {"vertices": [1, 2, 3]},
            }
            with (
                patch.dict(os.environ, {"CADGEN_RECONSTRUCTION_EXPERIMENT": "1"}),
                patch.object(host, "result_tree", return_value="tree"),
                patch.object(
                    host, "result_descriptor", return_value={"components": {"c": {}}}
                ),
                patch.object(host, "virtual_store_asset", return_value=(brep, "")),
                patch.object(
                    host, "_run", return_value=json.dumps(result).encode()
                ) as run,
            ):
                request = {
                    "tree": "tree",
                    "component": "c",
                    "recipe": recipe(),
                    "preview": False,
                }
                summary = host.reconstruct(
                    root, "models/part.step", json.dumps(request).encode()
                )
                self.assertEqual(summary["frameCount"], 2)
                self.assertNotIn("steps", summary)
                request["preview"] = True
                preview = host.reconstruct(
                    root, "models/part.step", json.dumps(request).encode()
                )
                self.assertEqual(len(preview["steps"]), 2)
                self.assertEqual(run.call_count, 1)
                request["recipe"]["steps"][1]["direction"] = [0, 0, 6]
                host.reconstruct(root, "models/part.step", json.dumps(request).encode())
                self.assertEqual(run.call_count, 2)
                request["tree"] = "old-tree"
                with self.assertRaisesRegex(ValueError, "STEP changed"):
                    host.reconstruct(
                        root, "models/part.step", json.dumps(request).encode()
                    )
                self.assertEqual(run.call_count, 2)

    def test_cache_has_a_byte_limit_and_evicts_the_least_recently_used_result(self):
        from collections import OrderedDict

        with (
            patch.object(host, "_cache", OrderedDict()),
            patch.object(host, "_cache_bytes", 0),
            patch.object(host, "MAX_CACHE_BYTES", 10),
        ):
            host._remember("a", (b"12345", {}))
            host._remember("b", (b"12345", {}))
            host._cached("a")
            host._remember("c", (b"12345", {}))
            self.assertIsNone(host._cached("b"))
            self.assertIsNotNone(host._cached("a"))
            self.assertEqual(host._cache_bytes, 10)


if __name__ == "__main__":
    unittest.main()
