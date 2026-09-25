# From intended motion to a dimensioned joint

Select the mechanism before calling a joint factory. The sculpt provides shape
and installation space, not a unique kinematic specification. Use the user's
intended function; identify consequential assumptions when only a static
mesh is supplied.

## Describe what must move

For each joint, identify the fixed/moving surfaces and the rest pose. Specify:

- Rotations and translations that must be allowed, their axes/centres and ranges,
  and freedoms that should be restrained. State degrees for angles and mm for travel.
- Independent coordinates versus coupled ones. A screw's translation follows its
  rotation; a freely adjustable two-axis joint permits combinations of both axes.
- Whether poses must hold under the appendage's weight, move freely, click into
  detents, return elastically, or intentionally detach. Record relevant material,
  print process and load/lever-arm assumptions; size alone does not prove strength.
- Assembly route, disassembly, separate hardware and concealed areas. Insertion
  is a different motion from operating the assembled model.

A short natural-language motion brief plus named axes/frames is sufficient; a
schema or exhaustive alternative search is unnecessary when the choice is clear.

## Match motion to structure

| Intended movement | Candidate structure | Design consequences |
| --- | --- | --- |
| Bend about one axis; restrain sideways swing and twist | Pin hinge / clevis and knuckle | Pin diameter, bearing length, cheek walls, axial retention, root support and travel stops |
| Twist about the appendage axis | Axle and bore / captive swivel | Bearing engagement, radial and axial gaps, shoulder/retainer and resistance to pull-out |
| Swing in two directions and allow twist | Ball and socket | Ball/stem/mouth dimensions, socket wall, stem sweep, retention and insertion space |
| Two angular freedoms with no independent axial spin | Gimbal / universal joint | Two real axis frames, intermediate carrier and its clearance; axis offsets affect motion |
| Extend/retract along one axis | Guided slider / telescoping joint | Stroke, guide section, anti-rotation if required, minimum engagement at full extension and end stops |
| Coupled rotation and translation | Screw or cam mechanism | Explicit coupling and actual moving contacts; choose only when this behavior is needed |
| No operating movement; parts only need assembly | Keyed plug, fastener, captured dovetail, magnet or other fixed connector | Alignment, retention and assembly access; an assembly connector is not automatically an articulation |

Retention and feel are additional design choices: a detent changes holding
behavior, not the number of axes; a snap feature can retain a pin as well as a
ball. If only bending is wanted, extra ball-joint freedoms need a reason. A
single-axis swivel and a hinge have the same kinematic freedom but different
axis placement and attachment geometry.

When several candidates satisfy the motion, compare their local fit, concealment,
assembly, retained material and part count. Reject infeasible wall/attachment or
access conditions before optimizing appearance. Use
[joint-layout.md](joint-layout.md) for ownership and seams, then pass the chosen
mechanism to [workflow.md](workflow.md). The runtime's ball-socket example does
not determine this choice.

## Derive dimensions from the actual model

Establish physical scale before measuring. After repair and any simplification,
inspect cross-sections perpendicular to candidate axes, available depth and the
narrowest attachment section. Measure more than the outer bounding box: concavities,
nearby appendages, thin skin and hidden voids can consume the apparent space.
Record the section locations/frames and actual dimensions used by the design.

Use the measured installation volume to constrain CAD parameters:

- **Housing budget:** required sculpt skin, mechanical housing, internal gaps and
  any separate cover must all fit. Distinguish a retained decorative wall from a
  wall that also serves as the bearing housing; do not subtract the same wall twice.
- **Moving member and attachment:** size the ball/pin/shaft/guide, stem or root,
  fillets and embedment against the available load path and engagement. Check the
  smallest remaining section after all voids and motion relief, not just the CAD
  primitive's nominal diameter. Reinforcement needs real overlap with the sculpt.
- **Travel and retention:** reserve the swept member's space, end-stop stock,
  pin-head/clip access, socket entry or slider engagement throughout the range.
  Fitting the neutral pose is only an initial placement check.
- **Print parameters:** keep radial fit clearance, diametral clearance, axial gap,
  visible seam gap, motion clearance and any deliberate snap interference distinct.
  Set these from the intended process/material and calibration; do not multiply
  them all by the model's scale factor. Label uncalibrated values as assumptions.

For example, a centered round bearing inside a local circular section of diameter
`D_local` has the initial budget `d_pin + 2*c_radial + 2*t_total <= D_local`, where
`t_total` is all required radial stock from the bearing bore to the exterior.
Thus `d_bore = d_pin + 2*c_radial`. With a **hypothetical** 14 mm section,
2 mm total radial stock and 0.2 mm assumed radial gap, the upper pin-diameter
budget is 9.6 mm. This is an upper fit bound, not a recommended pin size or a
strength check. A clevis also needs room along the pin axis for its cheeks,
knuckle, end gaps and retainer; a noncircular section needs actual section or
solid containment checks. Do not replace these with an overall-height ratio.

Before CAD authoring, record a compact measurement-to-parameter table: measured
local space, reserved wall/attachment, chosen parameter in mm and its reason.
Recheck the complete CAD stock and travel against the real mesh. If it cannot
fit while retaining the requirements, revise the location, axis, mechanism or
layout explicitly. Do not shrink walls, reduce travel silently, or select a
fixed-radius ball just because the helper has defaults.

## Choose the validation route with the mechanism

A fixed-pivot hinge/swivel fits the current angular runtime with one active axis
in an aligned joint frame. A ball joint needs its declared angular combinations;
mechanical limits need not form the Euler box supported by `RotationGrid`.
A gimbal has intermediate bodies that also need checks, and offset axes may not
fit a single fixed-pivot domain.

A slider requires translation transforms; a screw requires its rotation/translation
coupling; a linkage requires its real kinematics. These have no built-in sweep
helper in `cadgen.organic`. Author and validate a compatible motion recipe when needed,
or report the missing checks explicitly. Do not change the intended mechanism
merely to make the existing ball-joint test usable. See
[validation.md](validation.md) for check coverage and URDF mapping.
