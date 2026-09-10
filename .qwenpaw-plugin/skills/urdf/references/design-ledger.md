# URDF Design Ledger

Use this reference before creating or editing a `.urdf`. The ledger is the written spatial model that prevents silent frame, axis, unit, and mesh-scale mistakes.

The ledger's canonical home is a comment block at the top of the `.urdf` file itself (see the compact format in `references/authoring-contract.md`), optionally expanded in an adjacent README for large robots. It must be specific enough that another engineer can audit the URDF without reverse-engineering the XML, and it must be updated in the same edit that changes the modeled facts.

The sections below are the checklist of what the ledger must cover. For small robots the per-link and per-joint tables can collapse into a few comment lines; the information, not the table format, is what is required.

## Required Sections

### Robot Metadata

Record:

- robot name
- target consumers: RViz, robot_state_publisher, Gazebo/Ignition, MoveIt, real robot driver, or other
- unit convention: meters, kilograms, seconds, radians unless the project explicitly states otherwise
- frame convention: REP-103-style body convention when applicable, or a documented exception
- mesh unit convention: meters, millimeters, inches, or other
- source of dimensions: CAD, drawing, measured data, vendor documentation, existing URDF, or assumption

### Link Ledger

For every link, record:

| Field | Meaning |
|---|---|
| link name | Exact URDF `<link name="...">` value. |
| role | Physical link, frame-only link, sensor frame, tool frame, base frame, or other. |
| frame definition | Where the link frame is located and how its axes point. |
| parent joint | Joint that creates this child link frame, or `none` for root. |
| visual geometry | Primitive or mesh source, with origin relative to the link frame. |
| collision geometry | Primitive or mesh source, with origin relative to the link frame. |
| inertial source | CAD mass properties, vendor data, approximation, or intentionally omitted. |

Frame-only links such as `base_footprint`, optical frames, and `tool0` may omit inertial, visual, and collision blocks. Mark them explicitly as frame-only rather than leaving intent ambiguous.

### Joint Ledger

For every joint, record:

| Field | Meaning |
|---|---|
| joint name | Exact URDF `<joint name="...">` value. |
| type | `fixed`, `revolute`, `continuous`, or `prismatic` for the bundled validator; record `floating` or `planar` only if the project has a different supported validation path. |
| parent link | Link whose frame expresses the joint origin. |
| child link | Link whose frame is created at the joint frame. |
| origin xyz/rpy | Parent-link-frame transform from parent link to joint frame. |
| axis | Axis vector expressed in the joint frame, for movable joints. |
| limits | Radians for revolute, meters for prismatic, no finite lower/upper limits for continuous. |
| positive motion | What positive joint motion physically does. |
| source | CAD, drawing, measured data, existing model, or documented assumption. |

Do not write a movable joint without an explicit positive-motion convention. The sign of the axis is part of the model, not a cosmetic detail.

### Geometry Ledger

For every visual or collision item, record:

| Field | Meaning |
|---|---|
| link | Owning link. |
| kind | `visual` or `collision`. |
| geometry type | `mesh`, `box`, `cylinder`, or `sphere`. |
| source | CAD export, primitive approximation, vendor mesh, generated mesh, or temporary placeholder. |
| origin xyz/rpy | Transform from link frame to geometry frame. |
| scale | Mesh scale if applicable. |
| units | Mesh source units and URDF scale needed to express meters. |

Visual geometry is for display. Collision geometry is for contact, planning, and physics. It may intentionally be simpler than the visual geometry.

### Inertial Ledger

For every physical link, record:

| Field | Meaning |
|---|---|
| mass | Kilograms. |
| center of mass | Inertial origin xyz in the link frame. |
| inertia tensor | Tensor values and frame. |
| source | CAD mass properties, vendor data, calculation, approximation, or intentionally omitted. |
| confidence | Exact, estimated, placeholder, or unknown. |

Do not silently copy visual origins into inertial origins. The visual frame, collision frame, link frame, and center of mass can all differ.

### Assumption Ledger

Record every inferred or guessed value, including:

- unknown dimensions
- mesh units
- sign conventions
- joint axes
- parent/child direction
- visual or collision offsets
- mass, COM, and inertia approximations
- frame-only link intent
- unverified package URI resolution

List assumptions one per line in the ledger comment block so they survive with the file. In helper scripts, name assumed values by physical meaning (`ASSUMED_BASE_TO_SHOULDER_Z_M`), never as unlabelled numeric literals.

## When Information Is Missing

If spatial information is missing, do not invent a precise-looking transform. Choose one of these outcomes:

1. preserve existing source data unchanged;
2. create a frame-only or placeholder structure with explicit assumption comments;
3. use a clearly named approximate constant;
4. ask for dimensions or CAD data when the workflow allows interaction;
5. report that the model is structurally valid but spatially provisional.

A provisional URDF is acceptable when clearly labelled. A plausible but undocumented URDF is not.
