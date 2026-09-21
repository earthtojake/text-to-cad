# CNC machining

## Sources

Where the user supplies no shop specification, start from these two, and read
the shared rule-selection rules in `SKILL.md` before citing either:

- [How to design parts for CNC machining](https://www.hubs.com/knowledge-base/how-design-parts-cnc-machining/) (Protolabs Network) for the design rules: cavities and pockets, internal edges, thin walls, holes, threads, small features, tolerances, setups and orientation, undercuts.
- [CNC milling guidelines](https://www.protolabs.com/services/cnc-machining/cnc-milling/design-guidelines/) (Protolabs) for that supplier's size limits, materials, finishes, thread conventions and radii.

Neither establishes the capabilities of an arbitrary lathe, five-axis machine,
or custom fixture. Obtain the actual turning/tooling specification when
reviewing those processes.

## Review

Collect material, stock form, milling versus turning, available axes, critical
fits/tolerances, and the intended shop or tool constraints. If the process is
unspecified, discuss candidate setups without claiming a verified machining plan.

- For milling, identify pockets, internal corner radii, holes, thin walls, and
  approach directions. A cutter fitting in a pocket does not prove holder access.
- Compare actual internal radii with the proposed cutter radius. Report pocket
  depth, hole depth/diameter, and wall height/thickness separately; use the shop's
  material-specific reach limits instead of declaring one universal ratio.
- For turning, identify the rotation axis, diameters, bores, shoulders, grooves,
  and parting/workholding regions. Off-axis features may require live tooling or
  another setup. Rotational symmetry alone does not prove tool access.
- Review stock allowance, fixture contact, setup changes, inaccessible cavities,
  and collision risks. Treat setup counts as estimates until tool and fixture
  envelopes have been checked. No exact cycle time or quote without that evidence.
- Inspect thread callouts, engagement, drill-tip clearance, and tool runout.
  Distinguish modeled thread geometry from a drawing specification and follow
  the target shop's preferred thread representation.
- Separate geometry constraints from cost suggestions. Preserve functional
  interfaces; suggest relaxed tolerances only where function permits them.

Distinguish in-plane pocket corners from floor-to-wall roots: a flat end mill
can produce a sharp floor-to-wall junction. A root fillet is optional and may
require a corner-radius or ball tool and an extra finishing pass. For sharp
in-plane internal corners, consider larger radii or reliefs when acceptable.
A feature infeasible with one end mill is not infeasible for all manufacturing;
identify alternatives such as another setup, tooling, or EDM as proposals.

## Worked reasoning example

The following numbers are illustrative inputs, not default process limits.

A measured 2 mm internal corner radius cannot be reproduced by a proposed 6 mm
diameter cylindrical end mill: its 3 mm radius is too large. A smaller cutter
may fit, but reach, holder clearance, material, and pocket depth remain
separate checks.
