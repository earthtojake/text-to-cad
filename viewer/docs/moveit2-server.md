# MoveIt2 Server

The MoveIt2 server is an optional CAD Viewer backend module for SRDF IK and
path-planning controls. It is disabled for normal hosted viewer use and is only
needed when a user explicitly wants interactive solve or plan-to-pose controls.

## Install

From the viewer package or generated cad-viewer skill runtime directory:

```bash
npm run moveit2:setup
```

The setup script creates or updates the `moveit2-server` conda environment from
`moveit2_server/environment.yml`, installs the Python package in editable mode,
and runs a server import check.

Use a ROS 2 / MoveIt2 capable conda installation. Do not install ROS 2 or
MoveIt2 into the repository CAD `.venv`.

Useful environment variables:

```text
MOVEIT2_SERVER_CONDA_ENV_NAME
MOVEIT2_SERVER_CONDA_EXE
MOVEIT2_SERVER_REPO_ROOT
MOVEIT2_SERVER_HOST
MOVEIT2_SERVER_PORT
```

## Run

From the viewer package or generated cad-viewer skill runtime directory:

```bash
npm run moveit2:check
npm run moveit2:serve
```

The websocket endpoint defaults to:

```text
ws://127.0.0.1:8765/ws
```

CAD Viewer connects to that URL in local dev when MoveIt2 controls are enabled,
unless `VIEWER_MOVEIT2_WS_URL` or the browser `?moveit2Ws=` query parameter
overrides it.

## Hosted Backend

The MoveIt2 module is a long-running websocket backend, not a Vercel serverless
function. Host it in a ROS 2 / MoveIt2 capable VM or container by running the
same Python package and exposing its websocket URL:

```bash
MOVEIT2_SERVER_HOST=0.0.0.0 \
MOVEIT2_SERVER_PORT=8765 \
MOVEIT2_SERVER_REPO_ROOT=/srv/cad-viewer \
npm run moveit2:serve
```

Point the viewer at that endpoint with `VIEWER_MOVEIT2_WS_URL` at build time or
`?moveit2Ws=` at runtime. Production viewer builds keep MoveIt2 disabled unless
a websocket URL is explicitly configured by the deployment or user.

## Protocol

Requests use `protocolVersion: 1`.

Supported request types:

- `srdf.solvePose`
- `srdf.planToPose`

Use native joint-value fields:

- `startJointValuesByName`
- `jointValuesByName`
- trajectory `positions`

Legacy `*Deg` fields remain compatibility aliases. Angular values convert
between degrees and native radians; prismatic joints stay linear.

Pose targets require `target.frame`, `target.xyz`, and `target.endEffector`.
Set `target.targetLink` or `moveit2.targetLink` when the desired TCP is not
obvious.

Orientation can be provided as exactly one of:

```json
"quat_xyzw": [0, 0, 0, 1]
```

or:

```json
"rpy": [0, 0, 0]
```

If no orientation is provided, `moveit2.ik.positionOnly` defaults to true. If
`positionOnly` is false, an orientation must be supplied.

## Notes

- The server has no Python import dependency on the SRDF skill. It includes the
  SRDF metadata parser it needs under `moveit2_server/moveit2_server`.
- Success depends on the paired URDF, SRDF, collision geometry, solver
  availability, and MoveIt environment.
- The generated MoveIt config defaults are suitable for viewer smoke tests but
  are not universal production planning settings.
- Cache invalidation is based on paired URDF/SRDF file size and modification
  time.
