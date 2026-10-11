"""cadgen's mesher keeps a component whole when OCCT's pass leaves a face empty.

OCCT's mesher drops the odd tiny face at one deflection and meshes it at the
next (a watch case's 0.002 mm² slivers did, and with them every component the
same request covered). Here the component's pass is made to leave one face of a
bored block empty, as that one did, and the mesher must mesh the component again,
whole and finer, until that face has triangles (a face meshed alone would part
from its neighbours); a face no mesher covers that is larger than the mesh can
resolve is left out and named in the body.
"""

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")
from tests.python.support.tmp_root import generated_cad_directory  # noqa: E402

CHORD, ANGLE = 1.5e-3, 0.35


def _component():
    from build123d import Box, Cylinder

    from cadgen._internal.component_package import decode_display_shape, prepare_geometry_component
    from cadgen._internal.surf_container import read_surf
    from cadgen._internal.surface_extract import extract_surface_component

    prepared = prepare_geometry_component(Box(20, 20, 10) - Cylinder(4, 10))
    entry, payload = prepared["entry"], prepared["payload"]
    index, _ = read_surf(extract_surface_component(decode_display_shape(entry, payload).wrapped))
    return (lambda: decode_display_shape(entry, payload).wrapped), index


def _faces(body: bytes) -> dict[int, int]:
    """Each face's triangle count, from a stored body (every face has a range; an empty one counts 0)."""
    from cadgen.store.meshes import decode_payload

    return {row["ord"]: row["indexCount"] // 3 for row in decode_payload(body).face_ranges()}


class EmptyFaces(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fresh, cls.index = _component()
        cls.fresh = staticmethod(fresh)

    def mesh(self, emptied: int | None, *, every_pass: bool = False, index=None) -> bytes:
        """Mesh the component with face ``emptied`` left without triangles by the
        component's pass (and, with ``every_pass``, by every retry too)."""
        from OCP import BRepMesh
        from OCP.BRepTools import BRepTools
        from OCP.TopAbs import TopAbs_FACE
        from OCP.TopExp import TopExp
        from OCP.TopTools import TopTools_IndexedMapOfShape

        from cadgen._internal.occt_mesh import mesh_component

        real = BRepMesh.BRepMesh_IncrementalMesh
        topods = self.fresh()
        faces = TopTools_IndexedMapOfShape()
        TopExp.MapShapes_s(topods, TopAbs_FACE, faces)
        calls = []

        def mesher(shape, *args):
            result = real(shape, *args)
            calls.append(shape)
            if emptied is not None and (every_pass or len(calls) == 1):
                BRepTools.Clean_s(faces.FindKey(emptied))
            return result

        with mock.patch.object(BRepMesh, "BRepMesh_IncrementalMesh", side_effect=mesher):
            body = mesh_component(topods, index or self.index, surface_input="1" * 64,
                                  surface_object="a" * 64, chord=CHORD, angle=ANGLE)
        self.calls = len(calls)
        return body

    def test_a_face_the_pass_leaves_empty_is_meshed_again_with_the_whole_component(self):
        whole = _faces(self.mesh(None))
        self.assertEqual(sorted(whole), [row["ord"] for row in self.index["faces"]])
        face = max(whole, key=whole.get)
        repaired = _faces(self.mesh(face))
        self.assertGreater(self.calls, 1, "the component was meshed again")
        self.assertTrue(all(count > 0 for count in repaired.values()), "every face has triangles")

    def test_a_face_no_mesher_covers_is_left_out_and_named_unless_below_what_the_mesh_resolves(self):
        from cadgen._internal import face_fallback
        from cadgen._internal.occt_mesh import _bounding_diagonal
        from cadgen.store.meshes import decode_payload

        face = self.index["faces"][0]["ord"]
        deflection = CHORD * _bounding_diagonal(self.fresh())
        sliver = {**self.index, "faces": [{**row, "area": deflection * deflection / 4} if row["ord"] == face else row
                                          for row in self.index["faces"]]}
        with mock.patch.object(face_fallback, "tessellate_face", return_value=None):
            small = self.mesh(face, every_pass=True, index=sliver)
            refused = self.mesh(face, every_pass=True)
        # Under what the mesh resolves, a face may have no triangles, and nothing says so.
        self.assertEqual((_faces(small)[face], decode_payload(small).unmeshed_faces), (0, []))
        # A face OCCT refuses that the fallback cannot draw either: the component is meshed
        # without it, and the body names it for every reader to say so.
        self.assertEqual(_faces(refused)[face], 0)
        self.assertTrue(all(count > 0 for ordinal, count in _faces(refused).items() if ordinal != face))
        self.assertEqual(decode_payload(refused).unmeshed_faces, [face])


class ARequestOutlivesOneComponent(unittest.TestCase):
    def test_a_component_that_fails_to_mesh_leaves_the_rest_of_its_request_meshed(self):
        from build123d import Box, Compound, Cylinder, Pos

        from cadgen._internal import occt_mesh
        from cadgen.store import meshes, surfaces
        from cadgen.store.build import build_tree_from_compound

        with generated_cad_directory(prefix="occt-mesh-request-") as temporary, \
                mock.patch.dict(os.environ, {"CADGEN_CACHE_DIR": str(Path(temporary) / "cache")}):
            tree, geometry, _ = build_tree_from_compound(
                Compound(children=[Box(4, 4, 4), Pos(10, 0, 0) * Cylinder(2, 4)]), root_name="pair")
            real, failed = occt_mesh.mesh_component, []

            def mesher(topods, index, *, surface_input, **options):
                # Whatever fails, not only OCCT's own refusal: the first component meshed fails
                # every time, as a body its encoding refuses would.
                if failed in ([], [surface_input]):
                    failed[:] = [surface_input]
                    raise ValueError("invalid tessellation JSON length")
                return real(topods, index, surface_input=surface_input, **options)

            producer = surfaces.producer_identity()
            named = r"^component [0-9a-f]{16}: ValueError: invalid tessellation JSON length$"
            with mock.patch.object(occt_mesh, "mesh_component", side_effect=mesher), \
                    self.assertRaisesRegex(occt_mesh.MeshProductionError, named):
                surfaces.derive(tree, producer=producer,
                                tessellations=[{"chordTolerance": CHORD, "angleTolerance": ANGLE}])
            inputs = [surfaces.lookup(entry, producer)["surfaceInput"] for entry in geometry["components"].values()]
            others = {surface_input: surface_input != failed[0] for surface_input in inputs}

            def stored(chord, angle):
                return {surface_input: meshes.probe(meshes.tessellation_key(surface_input, chord, angle)) is not None
                        for surface_input in inputs}

            self.assertEqual(stored(CHORD, ANGLE), others,
                             "the other component was meshed and stored before the failure was reported")
            # A request that names mesh keys, as the snapshot host's does, outlives it the same way.
            keys = sorted((meshes.tessellation_key(surface_input, 5e-4, ANGLE) for surface_input in inputs),
                          key=lambda key: not key.startswith(failed[0]))
            with mock.patch.object(occt_mesh, "mesh_component", side_effect=mesher), \
                    self.assertRaisesRegex(occt_mesh.MeshProductionError, named):
                surfaces.produce_meshes(keys)
            self.assertEqual(stored(5e-4, ANGLE), others)
            # An interrupt is not a component's failure.
            with mock.patch.object(occt_mesh, "mesh_component", side_effect=KeyboardInterrupt), \
                    self.assertRaises(KeyboardInterrupt):
                surfaces.produce_meshes([meshes.tessellation_key(failed[0], 2e-3, 1.4)])


if __name__ == "__main__":
    unittest.main()
