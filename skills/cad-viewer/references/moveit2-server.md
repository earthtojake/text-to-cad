# MoveIt2 Server

Load this only when the user specifically needs CAD Viewer's optional SRDF IK or path-planning controls. Plain SRDF review and normal Viewer links do not require MoveIt2.

## Start

Run from the `cad-viewer` skill directory:

```bash
npm --prefix scripts/viewer run moveit2:setup
npm --prefix scripts/viewer run moveit2:check
npm --prefix scripts/viewer run moveit2:serve
```

The server defaults to `ws://127.0.0.1:8765/ws`. CAD Viewer connects to that URL when `VIEWER_MOVEIT2_WS_URL` or the browser `?moveit2Ws=` query points at it.

Use the configured ROS 2 / MoveIt2 environment. Do not install ROS 2 or MoveIt2 packages into the repository CAD `.venv`.

## Viewer Controls

Open an `.srdf` file, expand the right-side `MoveIt2` sheet, and use:

- Status: paired SRDF and MoveIt2 server status.
- Target: planning group, end effector, target frame, and X/Y/Z target coordinates.
- Solver: IK timeout, attempts, and tolerance.
- Planning: pipeline, planner ID, plan time, velocity scale, and acceleration scale.
- Actions: select pose from the model, reset to the current pose, solve pose, or plan to pose.

Report whether the environment check passed, whether pose solving/planning worked, and any viewer/server error text.
