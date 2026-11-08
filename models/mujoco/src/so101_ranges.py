"""The SO-101's joint stops from its own geometry: a self-collision sweep of the exported description.

    python src/so101_ranges.py            # after src/so101.py has written out/so101/so101.xml

The STEP carries no joint limits. A servo's travel bounds nothing (the ST3215 turns a full 360
degrees under position control: Waveshare's specification, "Mechanical Limited Angle: No Limit"),
so a joint's range is where the printed parts and servo cases hit each other. This script finds it
the way the parts would: each joint turned alone, the others at zero (the STEP pose), one degree at
a time from zero both ways, until the parts it moves run into the parts it does not.

The test is on surfaces, in the description MuJoCo loads (its meshes and joint frames, so it
checks the export too): every visual mesh but the fasteners and connectors (they sit in holes of
the parts they hold) is sampled to points ``SPACING`` mm apart; the still side's points mark a
voxel grid of ``PITCH`` mm; the moving side's points, turned, are looked up in it. A pair of bodies
already touching at zero (a horn on its servo, a part on the bearing it turns on) keeps its count
as it turns about the shared axis, so a stop is a pair's count rising ``STOP`` points over its count
at zero. The angle printed is the last clear degree. Limits written into ``so101.py`` are these,
rounded towards zero.

Voxels make it a clearance test to about ``PITCH``: two surfaces within a millimetre count as
touching. That is the margin a printed part's tolerance takes anyway.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
MJCF = HERE.parent / "out/so101/so101.xml"
SKIP = re.compile(r"screw|nut|050375033")  # fasteners and connectors: inside the parts they hold
SPACING = 0.6  # mm between surface samples
PITCH = 1.0  # mm, the occupancy grid
STOP = 40  # sample points over a pair's count at zero: about 15 mm^2 of new contact
STEP = 1.0  # degrees
REACH = 360.0  # degrees each way: a joint clear over a whole turn has no stop


def samples(model: mujoco.MjModel, geom: int) -> np.ndarray:
    """A mesh geom's surface as points in its geom frame (metres), about SPACING mm apart."""
    mesh = model.geom_dataid[geom]
    start, count = model.mesh_vertadr[mesh], model.mesh_vertnum[mesh]
    vertices = model.mesh_vert[start:start + count].astype(np.float64)
    faces = model.mesh_face[model.mesh_faceadr[mesh]:model.mesh_faceadr[mesh] + model.mesh_facenum[mesh]]
    a, b, c = (vertices[faces[:, i]] for i in range(3))
    areas = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1) * 1e6  # mm^2
    rng = np.random.default_rng(int(geom))
    count = int(areas.sum() / SPACING ** 2)
    picked = rng.choice(len(faces), size=count, p=areas / areas.sum())
    u, v = rng.random(count), rng.random(count)
    flip = u + v > 1
    u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
    return np.vstack([vertices, a[picked] + u[:, None] * (b[picked] - a[picked]) + v[:, None] * (c[picked] - a[picked])])


def subtree(model: mujoco.MjModel, body: int) -> set[int]:
    found = {body}
    for other in range(model.nbody):
        if model.body_parentid[other] in found and other not in found:
            found.add(other)
    for other in range(model.nbody):  # bodies are numbered parents first; a second pass is a guard
        if model.body_parentid[other] in found:
            found.add(other)
    return found


def main() -> None:
    model = mujoco.MjModel.from_xml_path(str(MJCF))
    data = mujoco.MjData(model)
    geoms = [g for g in range(model.ngeom)
             if model.geom_type[g] == mujoco.mjtGeom.mjGEOM_MESH and model.geom_contype[g] == 0
             and not SKIP.search(mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) or "")]
    local = {g: samples(model, g) for g in geoms}
    print(f"{len(geoms)} meshes, {sum(len(p) for p in local.values())} surface samples")

    def world(g: int) -> np.ndarray:
        return (local[g] @ data.geom_xmat[g].reshape(3, 3).T + data.geom_xpos[g]) * 1000.0  # mm

    for joint in range(model.njnt):
        name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_JOINT, joint)
        moving_bodies = subtree(model, model.jnt_bodyid[joint])
        moving = [g for g in geoms if model.geom_bodyid[g] in moving_bodies]
        still = [g for g in geoms if g not in moving]
        data.qpos[:] = 0
        mujoco.mj_kinematics(model, data)
        # The still side's occupancy: each voxel the body (index + 1) whose surface passes through it.
        points = [world(g) for g in still]
        owners = np.concatenate([np.full(len(p), model.geom_bodyid[g] + 1, dtype=np.int16) for g, p in zip(still, points)])
        points = np.vstack(points)
        low = points.min(axis=0) - 2 * PITCH
        cells = np.floor((points - low) / PITCH).astype(np.int64)
        shape = cells.max(axis=0) + 2
        grid = np.zeros(shape, dtype=np.int16)
        grid[cells[:, 0], cells[:, 1], cells[:, 2]] = owners
        # The geom each voxel came from, for saying what hits what.
        geom_grid = np.zeros(shape, dtype=np.int32)
        geom_grid[cells[:, 0], cells[:, 1], cells[:, 2]] = np.concatenate(
            [np.full(len(p), g, dtype=np.int32) for g, p in zip(still, [world(g) for g in still])])
        moving_geoms_of = np.concatenate([np.full(len(local[g]), g, dtype=np.int64) for g in moving])
        child, parent = model.jnt_bodyid[joint], model.body_parentid[model.jnt_bodyid[joint]]

        def pairs(angle: float) -> dict[tuple[int, int], int]:
            data.qpos[:] = 0
            data.qpos[model.jnt_qposadr[joint]] = math.radians(angle)
            mujoco.mj_kinematics(model, data)
            turned = np.vstack([world(g) for g in moving])
            at = np.floor((turned - low) / PITCH).astype(np.int64)
            inside = np.all((at >= 0) & (at < shape), axis=1)
            hit = np.zeros(len(at), dtype=np.int16)
            hit[inside] = grid[at[inside, 0], at[inside, 1], at[inside, 2]]
            found: dict[tuple[int, int], int] = {}
            touched = np.flatnonzero(hit > 0)
            for at_point in touched:
                mover = int(moving_geoms_of[at_point])
                if model.geom_bodyid[mover] != child or int(hit[at_point]) - 1 != parent:
                    continue  # another pair of links: a self-collision of the pose, not this joint's stop
                cell = at[at_point]
                key = (mover, int(geom_grid[cell[0], cell[1], cell[2]]))
                found[key] = found.get(key, 0) + 1
            return found

        zero = pairs(0.0)
        stops = []
        for sign in (-1, 1):
            clear, why = None, None
            for k in range(1, int(REACH / STEP) + 1):
                angle = sign * k * STEP
                over = {pair: count - zero.get(pair, 0) for pair, count in pairs(angle).items()}
                worst = max(over.items(), key=lambda item: item[1], default=(None, 0))
                if worst[1] > STOP:
                    clear = angle - sign * STEP
                    names = [mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, g) for g in worst[0]]
                    why = f"{names[0]} hits {names[1]} at {angle:+.0f} ({worst[1]} points)"
                    break
            stops.append((clear, why))
        (lower, low_why), (upper, up_why) = stops
        text = lambda value: "none" if value is None else f"{value:+.0f}"
        print(f"{name:14s} lower {text(lower):>5s}  upper {text(upper):>5s}   [{low_why or 'clear'}; {up_why or 'clear'}]")


if __name__ == "__main__":
    main()
