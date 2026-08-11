# Robot Fixtures

Robot description fixtures and supporting meshes for URDF, SRDF, STEP, STL,
and CAD Viewer workflows.

## Directory Map

- `elrobot/`: ELRobot follower URDF/SRDF plus STL meshes.
- `lekiwi/`: LeKiwi URDF/SRDF plus STL meshes for mobile-base and arm parts.
- `openarm/`: OpenArm bimanual URDF/SRDF fixture.
- `so101/`: SO-101 URDF/SRDF plus STL meshes.
- `tom/`: authored text-to-cad robot arm source, generated STEP/URDF outputs,
  STL exports, gripper parts, and sheet-metal DXF fixtures.

## Conventions

- Keep URDF/SRDF text files readable in normal Git.
- Keep mesh, STEP, STL, DXF, and render sidecar artifacts in Git LFS.
- Do not commit simulator cache directories, generated preview media, local
  package-resolution experiments, or printer credentials.

For TOM-specific generated CAD sources, keep Python generators near their
corresponding STEP output so the fixture remains inspectable without a separate
source tree.
