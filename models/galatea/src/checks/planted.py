# /// script
# dependencies = ["embreex", "numpy", "rtree", "trimesh"]
# ///
"""Is the interference check able to see what it is for?

    cad run src/checks/planted.py

Four pairs are made here, away from the robot, and put through the steps the check uses
(`common`'s `surfaces_cross`, `surfaces_near` and `mesh_depth` on meshes, `interferences`
on solids):

    a plate planted through a 2.6 mm skin       found by the meshes (crossing, and deep) and by the kernel
    the plate inside the skin, 0.3 mm from it   not crossing, but near: so it is sent to the kernel, which clears it
    the plate inside, 3 mm clear                 neither crossing nor near: never sent
    a pin in a bore of its own diameter          whatever the meshes say of two facetings of one cylinder,
                                                 not deep, and cleared by the kernel (they touch)

The first is the case an earlier, point-sampling check passed: a flat plate has no mesh
points but on its outline, and a thin skin has no inside for one to land in.
"""

import sys

import build123d as bd
import numpy as np
import trimesh
from common import DEEP, GL_TO_CAD, Geometry, Part, interferences, mesh_depth, surfaces_cross, surfaces_near


def planted(name, solid):
    """A part of the check's own kind from a solid: its mesh, and the solid itself."""
    vertices, triangles = solid.tessellate(0.2)
    mesh = trimesh.Trimesh([(v.X, v.Y, v.Z) for v in vertices], triangles, process=False)
    part = Part("planted", name, Geometry(name, mesh), np.linalg.inv(GL_TO_CAD))
    part.solid = solid
    return part


def main():
    skin = bd.Cylinder(50, 200) - bd.Cylinder(47.4, 220)
    block = bd.Box(40, 40, 30) - bd.Cylinder(5, 60)
    cases = [
        # name, a, b, and what must be so: meshes cross, meshes near, meshes deep, solids share volume (None: either)
        # (each part has a name of its own: the check remembers a measured pair by its parts' names)
        ("a plate through a 2.6 mm skin", planted("skin", skin), planted("plate_through", bd.Pos(46, 0, 0) * bd.Box(8, 60, 100)),
         True, True, True, True),
        ("the plate inside, 0.3 mm from it", planted("skin", skin), planted("plate_close", bd.Pos(43.1, 0, 0) * bd.Box(8, 6, 80)),
         False, True, False, False),
        ("the plate inside, 3 mm clear", planted("skin", skin), planted("plate_clear", bd.Pos(40.4, 0, 0) * bd.Box(8, 6, 80)),
         False, False, False, False),
        ("a pin in its bore", planted("block", bd.Pos(200, 0, 0) * block), planted("pin", bd.Pos(200, 0, 0) * bd.Cylinder(5, 50)),
         None, True, False, False),
    ]
    failed = 0
    for name, a, b, must_cross, must_near, must_deep, must_share in cases:
        crossed, near, depth = surfaces_cross((a, b)), surfaces_near((a, b)), mesh_depth((a, b))
        overlaps, unmeasured = interferences([(a, b)])
        shared = overlaps[0][0] if overlaps else 0.0
        right = (not unmeasured and bool(overlaps) == must_share and near == must_near and (depth > DEEP) == must_deep
                 and (must_cross is None or crossed == must_cross))
        failed += not right
        print(f"  {name:33s} meshes cross: {str(crossed):5s} near: {str(near):5s} deep: {depth:4.2f} mm   solids share {shared:8.1f} mm3"
              f"   {'as it should be' if right else 'WRONG'}")
    print("OK: the check finds what is planted and nothing that is not" if not failed else f"{failed} planted case(s) judged wrongly")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
