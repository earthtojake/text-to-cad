# Robot renderer fixtures

The descriptions the robot renderer's tests open: `arm.urdf` (a URDF of primitives
with a fixed frame root, a prismatic mimic pair, a named visual, and one link mesh
file, `meshes/head.glb`, carrying two named objects), the `arm.srdf` paired with it
(a `home` state, a named pose, an end effector), `swing.sdf` (a world whose joint
frame and child frame differ), `chain.urdf` (a 29-joint chain, for what a pose
step costs), `linkage.urdf` (a crank-rocker four-bar whose crank `tcad:four_bar`
derives from the rocker, for a linkage that closes on screen), and two descriptions the engine
refuses: `gone.urdf`, whose link mesh is missing, and `lonely.srdf`, with no URDF
beside it.

Beside each is what the engine resolves it to: `<name>.<kind>.robot.json` is exactly
what a robot document's `structure` (`GET /api/v1/documents/<urdf|srdf|sdf>/<id>/structure`) answers for it (`cad_server.robot_payload`), with every
visual's mesh named by the URL the browser test's server answers; `primitives/`
holds the meshes the engine made for the shapes (one GLB per shape and size, named
by the sha256 of its bytes); `refusals.json` holds the sentence the engine refuses the two
refused descriptions with. So the browser test (`RobotRenderer.browser.test.mjs`)
and the unit tests need neither Python nor a store, and the Python suite holds
these files current (`tests/python/packages/cad_server/test_robot_payload.py`).

Regenerate after changing a description or the payload shape, from the
repository root:

    .venv/bin/python packages/ui/src/renderers/robot/__fixtures__/make_fixtures.py
