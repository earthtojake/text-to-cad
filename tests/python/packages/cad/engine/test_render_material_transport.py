"""Each material a document's parts carry reaches the native OCCT face aspect a still is drawn with
(`engine/render`): from the document itself and from its STEP, GLB and 3MF exports, and a face that
names a material alone takes its colour from each instance. The rest of the stills are
`test_render.py`'s, which says where a test that draws can make its OpenGL context."""

from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from tests.python.support.render_stills import build, served


class MaterialTransportTest(unittest.TestCase):
    """Each imported material reaches the actual native OCCT face aspect."""

    def test_same_color_different_finishes_survive_each_snapshot_source(self) -> None:
        from cad.engine import export, formats
        from cad.engine.mesh import Mesh
        from cad.engine.render.occt import Scene
        from cad.engine.render.shapes import FaceGroup, prototype_shapes

        folder = Path(tempfile.mkdtemp(prefix="render-material-"))
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        source = """
import build123d as bd
from bd_materials import FinishedMaterial, metals
from cad.engine import xbf, paint
from threejs_materials import PbrProperties

@xbf("XBF/sample.xbf")
def sample():
    physical = metals.aluminum().material
    metal = FinishedMaterial(physical, pbr=PbrProperties.create(
        "same", color="#aaaacc", metalness=1, roughness=.15, opacity=.55))
    dielectric = FinishedMaterial(physical, pbr=PbrProperties.create(
        "same", color="#aaaacc", metalness=0, roughness=.8, opacity=.55))
    part = bd.Box(10, 10, 10)
    part.material, part.color = metal, bd.Color("#aaaacc", alpha=.55)
    return paint(part, part.faces()[0], dielectric)
"""
        xbf = build(folder, source, "sample")
        for suffix in (".xbf", ".step", ".glb", ".3mf"):
            path = xbf if suffix == ".xbf" else folder / f"sample{suffix}"
            if suffix != ".xbf":
                export.translate(xbf, None, path)
            if suffix in (".xbf", ".step"):
                structure, buffers = served(path)
                retained = {}
            else:
                foreign = formats.read(path)
                structure, buffers, retained = foreign.structure, foreign.buffers, foreign.shapes
            prototype = structure["prototypes"][0]
            parts = retained.get(prototype["key"]) or prototype_shapes(
                prototype, Mesh.from_bytes(buffers[prototype["key"]]))
            scene = Scene.__new__(Scene)
            scene.parts, scene.prototypes, scene.sources = [parts], [prototype], {}
            results = []
            for group in parts.faces:
                color = prototype.get("color") if group is None else group.color if isinstance(group, FaceGroup) else group
                source = scene._faces(0, group, tuple(color) if color is not None else None, "lit")
                pbr = source.Attributes().ShadingAspect().Material().PBRMaterial()
                results.append((pbr.Metallic(), pbr.Roughness(), pbr.Alpha()))
            self.assertEqual(len(results), 2, suffix)
            for actual, expected in zip(sorted(results), ((0., .8, .55), (1., .15, .55))):
                for got, want in zip(actual, expected):
                    self.assertAlmostEqual(got, want, delta=.002, msg=suffix)

    def test_material_only_face_uses_inherited_color_and_invalidates_cache(self) -> None:
        from cad.engine.formats.gltf import material_of
        from cad.engine.render.occt import Scene
        from cad.engine.render.service import _paints
        from cad.engine.render.shapes import FaceGroup, prototype_shapes
        from cad.engine.formats.buffer import buffer

        material = material_of({"pbrMetallicRoughness": {"metallicFactor": 1., "roughnessFactor": .2}})
        prototype = {"color": [.2, .3, .4, .6], "faceMaterials": {"1": material}}
        mesh, _ = buffer(np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]]),
                         np.array([[0, 1, 2]]))
        parts = prototype_shapes(prototype, mesh)
        face = next(group for group in parts.faces if isinstance(group, FaceGroup))
        self.assertIsNone(face.color, "no explicit face paint: inherit each instance")
        self.assertNotEqual(_paints(prototype), _paints({**prototype, "faceMaterials": {}}))
        scene = Scene.__new__(Scene)
        scene.parts, scene.prototypes, scene.sources = [parts], [prototype], {}
        colors = ([.2, .3, .4, .6], [.7, .1, .2, .9])
        scene.structure = {"instances": [{"prototype": 0, "color": color} for color in colors]}
        scene.canvas, scene.hidden, scene.shown, scene.timings = mock.Mock(), set(), [], {}
        scene.placement, scene._rig, scene._clip = lambda _index: np.eye(4), mock.Mock(), mock.Mock()
        with mock.patch("OCP.AIS.AIS_ConnectedInteractive"):
            scene.show({"mode": "shaded"})
        self.assertEqual(len(scene.sources), 2)
        for color in colors:
            source = scene.sources[("faces", 0, face, tuple(color), "lit", None)]
            pbr = source.Attributes().ShadingAspect().Material().PBRMaterial()
            actual = pbr.Color().GetRGB()
            for got, want in zip((actual.Red(), actual.Green(), actual.Blue(), pbr.Alpha()), color):
                self.assertAlmostEqual(got, want, delta=1e-6)


def setUpModule() -> None:
    # The registry and cache of every engine this module starts are its own, never the developer's
    # (``engine_daemon.isolate``); each test still names its own engine folder.
    from tests.python.support import engine_daemon

    engine_daemon.isolate(unittest.addModuleCleanup)


if __name__ == "__main__":
    unittest.main()
