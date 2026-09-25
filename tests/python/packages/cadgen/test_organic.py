"""Geometric regressions for mixed sculpt/CAD articulated parts."""
from __future__ import annotations
import json
from pathlib import Path
import subprocess
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import trimesh

from cadgen.organic import (
    RotationGrid, ball_socket, boolean, carve_clearance, check_motion,
    clearance_envelope, from_cad, inspect_mesh, load_mesh, prepare_mesh,
    split_plane, stl_roundtrip, write_mesh, write_scene,
)


class MeshContractTest(unittest.TestCase):
    def test_import_is_light(self):
        code = "import sys, cadgen.organic; assert not {'OCP','build123d','trimesh','manifold3d','vtkmodules'} & set(sys.modules)"
        subprocess.run([sys.executable, "-c", code], check=True)

    def test_scene_instances_scale_roundtrip_and_preserved_source(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "source.glb"
            scene = trimesh.Scene()
            cube = trimesh.creation.box((1, 2, 3))
            scene.add_geometry(cube, node_name="left", geom_name="shared")
            scene.graph.update(frame_to="right", matrix=trimesh.transformations.translation_matrix([4, 0, 0]), geometry="shared")
            path.write_bytes(scene.export(file_type="glb"))
            original = path.read_bytes()
            facts = inspect_mesh(path)
            self.assertEqual(len(facts["instances"]), 2)
            m = load_mesh(path, up="y", height_mm=20)
            np.testing.assert_allclose(m.extents, [50, 30, 20])
            for kwargs in ({}, {"height_mm": 20, "mm_per_unit": 10}):
                with self.assertRaises(ValueError):
                    load_mesh(path, up="y", **kwargs)
            self.assertEqual(path.read_bytes(), original)
            out = Path(root) / "result.glb"
            write_mesh(m, out)
            again = load_mesh(out, up="y", mm_per_unit=1000)
            np.testing.assert_allclose(again.bounds, m.bounds, atol=1e-5)
            first = out.read_bytes()
            size = struct.unpack_from("<I", first, 12)[0]
            header = json.loads(first[20:20 + size])
            self.assertIn("NORMAL", header["meshes"][0]["primitives"][0]["attributes"])
            self.assertEqual(header["materials"][0]["pbrMetallicRoughness"]["metallicFactor"], 0)
            write_mesh(m, out)
            self.assertEqual(first, out.read_bytes())

    def test_shared_glb_export_keeps_vertex_colors(self):
        colored = trimesh.creation.box((2, 2, 2))
        colored.visual.vertex_colors = np.tile([255, 0, 0, 255], (len(colored.vertices), 1))
        with tempfile.TemporaryDirectory() as root:
            out = Path(root) / "colored.glb"
            write_scene({"colored": colored}, out)
            data = out.read_bytes()
            size = struct.unpack_from("<I", data, 12)[0]
            header = json.loads(data[20:20 + size])
            self.assertEqual(header["nodes"][0]["name"], "colored")
            self.assertIn("COLOR_0", header["meshes"][0]["primitives"][0]["attributes"])

    def test_untextured_pbr_glb_roundtrip_and_image_boundary(self):
        mesh = trimesh.creation.box((2, 2, 2))
        mesh.visual = trimesh.visual.TextureVisuals(
            material=trimesh.visual.material.PBRMaterial(
                baseColorFactor=[0.2, 0.4, 0.6, 0.25], alphaMode="BLEND"
            )
        )
        with tempfile.TemporaryDirectory() as root:
            first = Path(root) / "material.glb"
            second = Path(root) / "again.glb"
            write_mesh(mesh, first)
            payload = first.read_bytes()
            size = struct.unpack_from("<I", payload, 12)[0]
            header = json.loads(payload[20:20 + size])
            self.assertEqual(header["materials"][0]["alphaMode"], "BLEND")
            loaded = trimesh.load_scene(first, process=False)
            part = next(iter(loaded.geometry.values()))
            self.assertEqual(part.visual.kind, "texture")
            np.testing.assert_allclose(
                np.asarray(part.visual.vertex_attributes["color"])[0] / 65535,
                [0.2, 0.4, 0.6, 0.25], atol=0.005,
            )
            scaled = load_mesh(first, up="y", mm_per_unit=1000)
            write_mesh(scaled, second)
            again = trimesh.load_scene(second, process=False)
            again_part = next(iter(again.geometry.values()))
            np.testing.assert_allclose(
                np.asarray(again_part.visual.vertex_attributes["color"])[0] / 65535,
                [0.2, 0.4, 0.6, 0.25], atol=0.005,
            )
            np.testing.assert_allclose(
                load_mesh(second, up="y", mm_per_unit=1000).bounds,
                scaled.bounds, atol=1e-5,
            )

            textured = trimesh.creation.box((2, 2, 2))
            textured.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    baseColorTexture=np.ones((2, 2, 4), dtype=np.uint8)
                )
            )
            with self.assertRaisesRegex(ValueError, "image textures need baking"):
                write_mesh(textured, second)

    def test_pbr_rgb_and_rgba_vertex_colors_roundtrip(self):
        for channels in (3, 4):
            with self.subTest(channels=channels), tempfile.TemporaryDirectory() as root:
                mesh = trimesh.creation.box((2, 2, 2))
                mesh.visual = trimesh.visual.TextureVisuals(
                    material=trimesh.visual.material.PBRMaterial(
                        baseColorFactor=[1.0, 1.0, 1.0, 1.0],
                        alphaMode="BLEND" if channels == 4 else "OPAQUE",
                    )
                )
                source = np.array([32768, 16384, 49152, 16384][:channels], dtype=np.uint16)
                mesh.visual.vertex_attributes["color"] = np.tile(source, (len(mesh.vertices), 1))
                first = Path(root) / "first.glb"
                second = Path(root) / "second.glb"
                write_mesh(mesh, first)
                loaded = load_mesh(first, up="y", mm_per_unit=1000)
                write_mesh(loaded, second)
                result = next(iter(trimesh.load_scene(second, process=False).geometry.values()))
                actual = np.asarray(result.visual.vertex_attributes["color"])[0] / 65535
                expected = source.astype(float) / 65535
                if channels == 3:
                    expected = np.append(expected, 1)
                np.testing.assert_allclose(actual, expected, atol=0.005)

    def test_unmaterialed_gltf_linear_color_is_converted_only_on_import(self):
        grey = trimesh.creation.box((2, 2, 2))
        grey.visual.vertex_colors = np.tile([128, 128, 128, 255], (len(grey.vertices), 1))
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "linear.glb"
            target = Path(root) / "roundtrip.glb"
            authored = Path(root) / "authored.glb"
            source.write_bytes(grey.export(file_type="glb"))
            original = source.read_bytes()
            size = struct.unpack_from("<I", original, 12)[0]
            header = json.loads(original[20:20 + size])
            self.assertNotIn("materials", header)
            imported = load_mesh(source, up="y", mm_per_unit=1000)
            write_mesh(imported, target)
            result = next(iter(trimesh.load_scene(target, process=False).geometry.values()))
            imported_linear = np.asarray(result.visual.vertex_attributes["color"])[0, :3] / 65535
            np.testing.assert_allclose(imported_linear, [128 / 255] * 3, atol=0.006)
            # Authored ColorVisuals remain sRGB; no global reinterpretation.
            write_mesh(grey, authored)
            manual = next(iter(trimesh.load_scene(authored, process=False).geometry.values()))
            manual_linear = np.asarray(manual.visual.vertex_attributes["color"])[0, :3] / 65535
            self.assertLess(max(manual_linear), 0.23)

    def test_pbr_alpha_modes_survive_glb_roundtrip(self):
        for mode in ("OPAQUE", "MASK", "BLEND"):
            with self.subTest(mode=mode), tempfile.TemporaryDirectory() as root:
                mesh = trimesh.creation.box((2, 2, 2))
                mesh.visual = trimesh.visual.TextureVisuals(
                    material=trimesh.visual.material.PBRMaterial(
                        baseColorFactor=[0.5, 0.5, 0.5, 0.25],
                        alphaMode=mode, alphaCutoff=0.4 if mode == "MASK" else None,
                    )
                )
                first = Path(root) / "first.glb"
                second = Path(root) / "second.glb"
                write_mesh(mesh, first)
                write_mesh(load_mesh(first, up="y", mm_per_unit=1000), second)
                for path in (first, second):
                    payload = path.read_bytes()
                    size = struct.unpack_from("<I", payload, 12)[0]
                    header = json.loads(payload[20:20 + size])
                    material = header["materials"][0]
                    self.assertEqual(material["alphaMode"], mode)
                    if mode == "MASK":
                        self.assertAlmostEqual(material["alphaCutoff"], 0.4)
                    result = next(iter(trimesh.load_scene(path, process=False).geometry.values()))
                    alpha = np.asarray(result.visual.vertex_attributes["color"])[0, 3] / 65535
                    self.assertAlmostEqual(alpha, 1 if mode == "OPAQUE" else 0.25, delta=0.005)

    def test_multinode_mask_alpha_stays_on_the_same_side_of_cutoff(self):
        cutoff = 0.4
        source_alpha = {"below": 0.399, "edge": 0.4, "above": 0.401}
        parts = {}
        for index, (name, alpha) in enumerate(source_alpha.items()):
            mesh = trimesh.creation.box((2, 2, 2))
            mesh.apply_translation((4 * index, 0, 0))
            mesh.visual = trimesh.visual.TextureVisuals(
                material=trimesh.visual.material.PBRMaterial(
                    baseColorFactor=[1.0, 1.0, 1.0, 1.0],
                    alphaMode="MASK", alphaCutoff=cutoff,
                )
            )
            mesh.visual.vertex_attributes["color"] = np.tile(
                np.array([0.5, 0.5, 0.5, alpha], dtype=np.float32),
                (len(mesh.vertices), 1),
            )
            parts[name] = mesh
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source.glb"
            target = Path(root) / "merged.glb"
            write_scene(parts, source)
            source_scene = trimesh.load_scene(source, process=False)
            expected = sorted({
                int(np.asarray(piece.visual.vertex_attributes["color"])[0, 3])
                for piece in source_scene.geometry.values()
            })
            self.assertEqual(len(expected), 3)
            self.assertLess(expected[0] / 65535, cutoff)
            self.assertAlmostEqual(expected[1] / 65535, cutoff, delta=1 / 65535)
            self.assertGreater(expected[2] / 65535, cutoff)

            merged = load_mesh(source, up="y", mm_per_unit=1000)
            write_scene({"merged": merged}, target)
            payload = target.read_bytes()
            size = struct.unpack_from("<I", payload, 12)[0]
            header = json.loads(payload[20:20 + size])
            self.assertEqual(header["materials"][0]["alphaMode"], "MASK")
            self.assertAlmostEqual(header["materials"][0]["alphaCutoff"], cutoff)
            output = next(iter(trimesh.load_scene(target, process=False).geometry.values()))
            actual = sorted(set(np.asarray(output.visual.vertex_attributes["color"])[:, 3]))
            self.assertEqual(actual, expected)

    def test_imported_float_colors_survive_mesh_copy_and_translation(self):
        linear_grey = ((0.5 + 0.055) / 1.055) ** 2.4
        for count in (1, 2):
            with self.subTest(nodes=count), tempfile.TemporaryDirectory() as root:
                parts = {}
                for index, alpha in enumerate((0.399, 0.401)[:count]):
                    mesh = trimesh.creation.box((2, 2, 2))
                    mesh.apply_translation((4 * index, 0, 0))
                    mesh.visual = trimesh.visual.TextureVisuals(
                        material=trimesh.visual.material.PBRMaterial(
                            baseColorFactor=[1.0, 1.0, 1.0, 1.0],
                            alphaMode="MASK", alphaCutoff=0.4,
                        )
                    )
                    mesh.visual.vertex_attributes["color"] = np.tile(
                        np.array([linear_grey, linear_grey, linear_grey, alpha], dtype=np.float32),
                        (len(mesh.vertices), 1),
                    )
                    parts[f"part-{index}"] = mesh
                source = Path(root) / "source.glb"
                target = Path(root) / "copied.glb"
                write_scene(parts, source)
                source_scene = trimesh.load_scene(source, process=False)
                expected = sorted({
                    tuple(np.asarray(piece.visual.vertex_attributes["color"])[0, [0, 3]])
                    for piece in source_scene.geometry.values()
                })
                self.assertTrue(all(color[0] < 20000 for color in expected))
                loaded = load_mesh(source, up="y", mm_per_unit=1000)
                copied = loaded.copy()
                copied.apply_translation((10, 0, 0))
                np.testing.assert_allclose(copied.bounds[:, 0], loaded.bounds[:, 0] + 10)
                write_scene({"moved": copied}, target)
                payload = target.read_bytes()
                size = struct.unpack_from("<I", payload, 12)[0]
                header = json.loads(payload[20:20 + size])
                self.assertEqual(header["materials"][0]["alphaMode"], "MASK")
                self.assertAlmostEqual(header["materials"][0]["alphaCutoff"], 0.4)
                output = next(iter(trimesh.load_scene(target, process=False).geometry.values()))
                actual = sorted({
                    tuple(row[[0, 3]]) for row in
                    np.asarray(output.visual.vertex_attributes["color"])
                })
                self.assertEqual(actual, expected)

    def test_raw_gltf_material_factor_keeps_mask_alpha_precision(self):
        # Include the reviewed two-.399 case and distinct materials to check
        # the glTF primitive-to-geometry association, plus a single node.
        for factors in ((0.399,), (0.399, 0.399), (0.399, 0.401)):
            with self.subTest(factors=factors), tempfile.TemporaryDirectory() as root:
                parts = {}
                for index in range(len(factors)):
                    mesh = trimesh.creation.box((2, 2, 2))
                    mesh.apply_translation((4 * index, 0, 0))
                    mesh.visual = trimesh.visual.TextureVisuals(
                        material=trimesh.visual.material.PBRMaterial(
                            baseColorFactor=[1.0, 1.0, 1.0, 1.0],
                            alphaMode="MASK", alphaCutoff=0.4,
                        )
                    )
                    parts[f"part-{index}"] = mesh
                source = Path(root) / "source.glb"
                target = Path(root) / "roundtrip.glb"
                write_scene(parts, source)
                payload = source.read_bytes()
                old_size = struct.unpack_from("<I", payload, 12)[0]
                header = json.loads(payload[20:20 + old_size])
                for material, alpha in zip(header["materials"], factors):
                    material["pbrMetallicRoughness"]["baseColorFactor"] = [0.5, 0.5, 0.5, alpha]
                json_bytes = json.dumps(header, separators=(",", ":")).encode("utf-8")
                json_chunk = json_bytes + b" " * (-len(json_bytes) % 4)
                tail = payload[20 + old_size:]
                source.write_bytes(
                    struct.pack("<III", 0x46546C67, 2, 20 + len(json_chunk) + len(tail))
                    + struct.pack("<II", len(json_chunk), 0x4E4F534A)
                    + json_chunk + tail
                )
                raw = source.read_bytes()
                raw_size = struct.unpack_from("<I", raw, 12)[0]
                raw_header = json.loads(raw[20:20 + raw_size])
                self.assertEqual(
                    [mat["pbrMetallicRoughness"]["baseColorFactor"][3]
                     for mat in raw_header["materials"]],
                    list(factors),
                )
                loaded = load_mesh(source, up="y", mm_per_unit=1000)
                write_scene({"merged": loaded}, target)
                output = next(iter(trimesh.load_scene(target, process=False).geometry.values()))
                colors = np.asarray(output.visual.vertex_attributes["color"]) / 65535
                np.testing.assert_allclose(colors[:, 0], 0.5, atol=1 / 65535)
                np.testing.assert_allclose(
                    sorted(set(colors[:, 3])), sorted(set(factors)), atol=1 / 65535
                )
                self.assertLess(min(colors[:, 3]), 0.4)
                target_payload = target.read_bytes()
                target_size = struct.unpack_from("<I", target_payload, 12)[0]
                target_header = json.loads(target_payload[20:20 + target_size])
                self.assertEqual(target_header["materials"][0]["alphaMode"], "MASK")
                self.assertAlmostEqual(target_header["materials"][0]["alphaCutoff"], 0.4)

    def test_multinode_vertex_colors_survive_load_and_reexport(self):
        red = trimesh.creation.box((2, 2, 2))
        blue = red.copy()
        blue.apply_translation((4, 0, 0))
        red.visual.vertex_colors = np.tile([255, 0, 0, 255], (len(red.vertices), 1))
        blue.visual.vertex_colors = np.tile([0, 0, 255, 255], (len(blue.vertices), 1))
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "parts.glb"
            target = Path(root) / "combined.glb"
            write_scene({"red": red, "blue": blue}, source)
            loaded = load_mesh(source, up="y", mm_per_unit=1000)
            self.assertEqual(loaded.visual.kind, "vertex")
            write_mesh(loaded, target)
            part = next(iter(trimesh.load_scene(target, process=False).geometry.values()))
            colors = np.asarray(part.visual.vertex_attributes["color"])[:, :3]
            self.assertIn((65535, 0, 0), {tuple(row) for row in colors})
            self.assertIn((0, 0, 65535), {tuple(row) for row in colors})

    def test_multinode_image_textures_remain_importable_but_cannot_export_unbaked(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is needed to create a textured GLB fixture")
        textured = trimesh.creation.box((2, 2, 2))
        textured.visual = trimesh.visual.TextureVisuals(
            uv=np.zeros((len(textured.vertices), 2)),
            material=trimesh.visual.material.PBRMaterial(
                baseColorTexture=Image.fromarray(np.full((2, 2, 4), 255, dtype=np.uint8))
            ),
        )
        plain = trimesh.creation.box((2, 2, 2))
        plain.apply_translation((4, 0, 0))
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "textured.glb"
            scene = trimesh.Scene()
            scene.add_geometry(textured, node_name="textured")
            scene.add_geometry(plain, node_name="plain")
            source.write_bytes(scene.export(file_type="glb"))
            loaded = load_mesh(source, up="y", mm_per_unit=1000)
            self.assertTrue(loaded.is_volume)
            with self.assertRaisesRegex(ValueError, "image textures need baking"):
                write_mesh(loaded, Path(root) / "unbaked.glb")

    def test_repair_is_explicit_and_audited(self):
        damaged = trimesh.creation.box()
        damaged.update_faces(np.arange(len(damaged.faces)) != 0)
        with self.assertRaises(ValueError):
            prepare_mesh(damaged)
        repaired, audit = prepare_mesh(damaged, fill_small_holes=True)
        self.assertTrue(repaired.is_volume)
        self.assertEqual(audit["added_cap_triangles"], 1)
        self.assertFalse(damaged.is_watertight)

    def test_stl_roundtrip_checks_delivered_geometry(self):
        a = trimesh.creation.box((10, 10, 10))
        r, audit = stl_roundtrip(a)
        self.assertTrue(r.is_volume)
        self.assertEqual(audit["components"], 1)
        b = a.copy(); b.apply_translation((10, 10, 0))
        touching = boolean("union", [a, b])
        # Two cubes meeting only on an edge have valid separate topology in
        # Manifold, but lose that distinction in STL's triangle soup.
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "part.stl"
            write_mesh(a, path); valid = path.read_bytes()
            with self.assertRaisesRegex(ValueError, "STL round trip"):
                write_mesh(touching, path)
            self.assertEqual(valid, path.read_bytes())

    def test_split_gap_and_true_union(self):
        cube = trimesh.creation.box((10, 10, 10))
        low, high = split_plane(cube, origin=(0, 0, 0), normal=(0, 0, 4), gap_mm=2)
        self.assertTrue(low.is_volume and high.is_volume)
        self.assertAlmostEqual(low.volume + high.volume, 800)
        self.assertAlmostEqual(high.bounds[0, 2] - low.bounds[1, 2], 2)
        translated = cube.copy(); translated.apply_translation((5, 0, 0))
        joined = boolean("union", [cube, translated])
        self.assertAlmostEqual(joined.volume, 1500)
        self.assertEqual(len(joined.split(only_watertight=False)), 1)
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "assembly.glb"
            write_scene({"a": cube, "b": translated}, target)
            self.assertEqual(len(inspect_mesh(target)["instances"]), 2)


class MotionContractTest(unittest.TestCase):
    def test_compound_grid_and_intermediate_collision(self):
        a = trimesh.creation.box((1, 1, 1)); a.apply_translation((5, 0, 0))
        grid = RotationGrid((0, 0, 0), z_degrees=(-90, 90), step_degrees=90)
        result = check_motion(a, a, grid)
        self.assertEqual([row["status"] for row in result["samples"]], ["pass", "collision", "pass"])
        self.assertFalse(result["ok"])
        combined = RotationGrid((0, 0, 0), (-10, 10), (-10, 10), (-10, 10), 10)
        self.assertEqual(len(list(combined.frames())), 27)
        self.assertEqual(result["status"], "fail")

    def test_gap_units_and_saturation(self):
        a = trimesh.creation.box()
        b = a.copy(); b.apply_translation((1.15, 0, 0))
        result = check_motion(a, b, RotationGrid((0, 0, 0)), clearance_mm=.2)
        self.assertEqual(result["samples"][0]["status"], "insufficient_clearance")
        self.assertAlmostEqual(result["minimum_sampled_gap_mm"], .15)
        self.assertEqual(result["maximum_overlap_mm3"], 0)
        b.apply_translation((100, 0, 0))
        far = check_motion(a, b, RotationGrid((0, 0, 0)), clearance_mm=.2)
        self.assertTrue(far["ok"] and far["minimum_gap_is_lower_bound"])

    def test_invalid_input_never_passes(self):
        bad = trimesh.creation.box(); bad.update_faces(np.arange(len(bad.faces)) != 0)
        with self.assertRaises(ValueError):
            check_motion(bad, trimesh.creation.box(), RotationGrid((0, 0, 0)))
        with self.assertRaises(ValueError):
            list(RotationGrid((0, 0, 0), (1, -1)).frames())

    def test_envelope_contains_unsampled_poses(self):
        obstacle = trimesh.creation.box((1, 1, 1)); obstacle.apply_translation((10, 0, 0))
        grid = RotationGrid((0, 0, 0), z_degrees=(0, 90), step_degrees=90)
        envelope, audit = clearance_envelope(obstacle, grid, clearance_mm=.3)
        self.assertLess(audit["between_sample_padding_mm"], 3.5)
        for angle in (22.5, 45, 67.5):
            frame = next(RotationGrid((0, 0, 0), z_degrees=(angle, angle)).frames())
            posed = obstacle.copy(); posed.apply_transform(frame["matrix"])
            remainder = boolean("difference", [posed, envelope])
            self.assertEqual(len(remainder.faces), 0)

    def test_partitioned_sweep_preserves_an_obstacle_concavity(self):
        left = trimesh.creation.box((2, 8, 2)); left.apply_translation((-3, 0, 0))
        right = left.copy(); right.apply_translation((6, 0, 0))
        base = trimesh.creation.box((8, 2, 2)); base.apply_translation((0, -3, 0))
        obstacle = boolean("union", [left, right, base])
        probe = trimesh.creation.box((1, 1, 1)); probe.apply_translation((0, 2, 0))
        grid = RotationGrid((0, 0, 0))
        coarse, _ = clearance_envelope(obstacle, grid, clearance_mm=.1)
        local, audit = clearance_envelope(obstacle, grid, clearance_mm=.1, cell_size_mm=2)
        self.assertGreater(boolean("intersection", [coarse, probe]).volume, .9)
        self.assertEqual(len(boolean("intersection", [local, probe]).faces), 0)
        self.assertEqual(len(boolean("difference", [obstacle, local]).faces), 0)
        self.assertGreater(audit["partition_cells"], 1)
        with self.assertRaisesRegex(ValueError, "512 cells"):
            clearance_envelope(obstacle, grid, clearance_mm=.1, cell_size_mm=.1)

    def test_interpolation_cover_contains_compound_inverse_poses_and_clearance(self):
        obstacle = trimesh.creation.box((2, 3, 4)); obstacle.apply_translation((10, 4, -2))
        pivot = (2, -3, 1)
        grid = RotationGrid(pivot, (-20, 25), (5, 40), (-10, 50), 30)
        rng = np.random.default_rng(17)
        for inverse in (False, True):
            envelope, _ = clearance_envelope(obstacle, grid, clearance_mm=.3,
                                             inverse=inverse, cell_size_mm=2)
            for _ in range(12):
                degrees = rng.uniform([-20, 5, -10], [25, 40, 50])
                frame = next(RotationGrid(pivot, *((d, d) for d in degrees))
                             .frames(inverse=inverse))
                placed = obstacle.copy(); placed.apply_transform(frame["matrix"])
                # Axis offsets exercise the explicit clearance in world space.
                for offset in ([.3, 0, 0], [0, -.3, 0], [0, 0, .3]):
                    shifted = placed.copy(); shifted.apply_translation(offset)
                    remainder = boolean("difference", [shifted, envelope])
                    self.assertTrue(not len(remainder.faces) or abs(remainder.volume) < 1e-8)

    def test_protected_material_and_disconnection(self):
        host = trimesh.creation.box((10, 10, 10))
        cutter = trimesh.creation.box((4, 12, 12)); cutter.apply_translation((4, 0, 0))
        protect = trimesh.creation.box((3, 3, 3)); protect.apply_translation((3.5, 0, 0))
        after, _, report = carve_clearance(host, cutter, allowed_region=host, protected=protect)
        self.assertGreater(report["removed_volume_mm3"], 0)
        self.assertAlmostEqual(boolean("intersection", [after, protect]).volume, protect.volume)
        with self.assertRaises(ValueError):
            carve_clearance(host, trimesh.creation.box((2, 12, 12)), allowed_region=host)

    def test_kernel_error_is_inconclusive(self):
        mesh = trimesh.creation.box()
        class BrokenSolid:
            def transform(self, matrix):
                raise RuntimeError("synthetic kernel failure")
        with patch("cadgen.organic.motion._solid", return_value=BrokenSolid()):
            result = check_motion(mesh, mesh, RotationGrid((0, 0, 0)))
        self.assertFalse(result["ok"])
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(len(result["errors"]), 1)

    def test_inverse_envelope_maps_fixed_obstacle_to_moving_frame(self):
        obstacle = trimesh.creation.box(); obstacle.apply_translation((8, 0, 0))
        grid = RotationGrid((0, 0, 0), z_degrees=(90, 90))
        envelope, _ = clearance_envelope(obstacle, grid, clearance_mm=0, inverse=True)
        np.testing.assert_allclose(envelope.centroid, [0, -8, 0], atol=1e-10)


class JointTest(unittest.TestCase):
    def test_cad_features_and_rigid_motion(self):
        joint = ball_socket()
        self.assertLess(joint.parameters["mouth_radius_mm"], joint.parameters["ball_radius_mm"])
        for shape in (joint.male, joint.socket, joint.socket_blank, joint.socket_void):
            self.assertTrue(shape.is_valid)
            self.assertEqual(len(shape.solids()), 1)
        male, socket = from_cad(joint.male), from_cad(joint.socket)
        self.assertTrue(male.is_volume and socket.is_volume)
        report = check_motion(male, socket, RotationGrid((0, 0, 0), (-10, 10), (-10, 10), (-10, 10), 10), clearance_mm=.1)
        self.assertTrue(report["ok"], json.dumps(report))
        self.assertGreater(report["minimum_sampled_gap_mm"], .1)
        with self.assertRaises(ValueError):
            ball_socket(mouth_z_mm=0)


if __name__ == "__main__":
    unittest.main()
