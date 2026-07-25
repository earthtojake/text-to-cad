"""Simulation QA for the hinged-lid mechanism (sim-test).

Engine: MuJoCo — see design-note.md for the environment note (PyBullet has
no Windows wheels in this environment; the sim-test skill documents MuJoCo
as the deliberate contact-fidelity alternative).

Scenario selection: the design note requires the hinge to settle closed
under gravity from an opened position, stay within its 0..1.92 rad limits,
and never interpenetrate the base.
"""

import numpy as np
import pytest

# Skip cleanly on platforms where the chosen engine is unavailable.
mujoco = pytest.importorskip("mujoco")

URDF = "models/qa-e2e-hinged-lid/hinged_lid.urdf"


@pytest.fixture(scope="module")
def model_and_data():
    model = mujoco.MjModel.from_xml_path(URDF)
    data = mujoco.MjData(model)
    return model, data


def test_mechanism_structure(model_and_data):
    model, _ = model_and_data
    assert model.njnt == 1
    assert model.jnt_type[0] == mujoco.mjtJoint.mjJNT_HINGE
    assert model.jnt_limited[0]


def test_hinge_settles_closed_within_limits(model_and_data):
    model, data = model_and_data
    mujoco.mj_resetData(model, data)
    data.qpos[0] = 1.0  # released from ~57 degrees open
    mujoco.mj_forward(model, data)

    angles = []
    for _ in range(2500):  # 5 simulated seconds at the default 2 ms step
        mujoco.mj_step(model, data)
        angles.append(data.qpos[0])

    angles = np.array(angles)
    # Joint limits 0..1.92 rad must hold throughout the swing.
    assert angles.max() <= 1.92 + 1e-3
    # A negative angle means the lid swung through the base box.
    assert angles.min() >= -0.02
    # Damped hinge released open must settle closed.
    assert abs(angles[-1]) <= 0.05
    # Closed lid must be resting on the base, not floating.
    assert data.ncon > 0
