"""Geometry QA for the hinged-lid part (mesh-qa).

Check selection and threshold bases: see design-note.md in this directory.
Dimensional tolerances (+/- 0.2 mm) follow typical FDM accuracy from the
mesh-qa printability reference ranges.
"""

import numpy as np
import pytest
import trimesh

MODEL_DIR = "models/qa-e2e-hinged-lid"


@pytest.fixture(scope="module")
def base_mesh():
    return trimesh.load(f"{MODEL_DIR}/base.stl", force="mesh")


@pytest.fixture(scope="module")
def lid_mesh():
    return trimesh.load(f"{MODEL_DIR}/lid.stl", force="mesh")


@pytest.mark.parametrize("fixture", ["base_mesh", "lid_mesh"])
def test_structural_sanity(fixture, request):
    mesh = request.getfixturevalue(fixture)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.volume > 0
    assert len(mesh.split(only_watertight=False)) == 1


def test_base_dimensions(base_mesh):
    # Design note: base box footprint 60 x 40 mm. Measured from a
    # mid-height cross-section because the hinge lugs legitimately
    # protrude beyond the box footprint in the global bounding box
    # (corrected in iteration 2; see iteration-log.md).
    section = base_mesh.section(plane_origin=[0, 0, 10.0], plane_normal=[0, 0, 1])
    planar, _ = section.to_2D()
    extents = planar.extents
    assert extents[0] == pytest.approx(60.0, abs=0.2)
    assert extents[1] == pytest.approx(40.0, abs=0.2)


def test_lid_plate_thickness(lid_mesh):
    # Design note: lid plate nominal 2.0 mm, hard floor 1.0 mm (FDM
    # handling wall; see mesh-qa printability reference ranges).
    # Measured by a vertical ray through the plate, away from the knuckle.
    origins = [[0.0, -10.0, 50.0]]
    directions = [[0.0, 0.0, -1.0]]
    locations, _, _ = lid_mesh.ray.intersects_location(origins, directions)
    z_hits = np.sort(locations[:, 2])[::-1]
    assert len(z_hits) >= 2, "ray should enter and exit the lid plate"
    plate_thickness = z_hits[0] - z_hits[1]
    assert plate_thickness >= 1.0
