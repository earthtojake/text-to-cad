# Joint layout before segmentation

Use [joint-design.md](joint-design.md) to establish the required movement,
select a mechanism and measure its installation space. Refine the mechanism,
part ownership, dimensions and seam together. The present runtime does not infer
anatomical parts or optimize connector ownership automatically; these are authored design
choices that the recipe and reports must make explicit.

## Design brief

Record the fixed and moving *surfaces*, not just the names of body parts.
A sculpted shoulder cap can belong to the fixed torso while the arm below it
moves. Decide the pivot, axes, required travel, protected exterior, permitted
hidden cuts, minimum attachment/wall targets, and the assembly approach.

Inspect existing creases, cuffs, armor plates, neck collars and overlapping
surfaces as possible seams. Use [motion-surfaces.md](motion-surfaces.md) for curved parting boundaries and
motion-derived smooth relief. A regional Boolean mask can follow several
boundaries; a single through-plane may capture unrelated trim or expose a
large mechanical joint. Prefer reusing the original exterior to replacing it
with a generic spherical shell unless the latter is the design intent.

## Choose an architecture

Use the user's proposed architecture as a candidate and examine the tradeoffs
that could invalidate it. Assign each bearing, moving member, retainer and
mount to a sculpt part or separate insert. For a hinge this can mean deciding
which side carries the clevis versus knuckle and whether the pin is separate;
for a ball socket, compare ball-on-A / socket-on-B with the reverse when ambiguous.
Other useful alternatives include an internal carrier, a separately assembled
cover, a captured split housing, or a different joint type. Do not enumerate every
alternative when the requirements already settle the choice.

First reject candidates with unresolved collision, insufficient attachment or
wall, or no feasible assembly access. Then compare visible silhouette change,
seam visibility, added/removed material, manufacturing access and part count.
Material and process affect flexure and strength; unsupported estimates must
not masquerade as validated scores. Report why the selected candidate was
chosen and which alternatives were only considered, measured or tested.

## Example: a fixed hollow shoulder hood

For a shoulder whose selected mechanism is a ball socket, a useful arrangement is:

- The original rounded shoulder exterior and its torso attachment stay fixed.
- The hood contains a separate mechanical pocket. A downward-facing socket
  attaches to the inside crown or an internal carrier.
- The arm carries the ball and stem; its boundary sits near the natural
  constriction below the hood.
- The rim overlaps the joint region visually while leaving the specified
  swept arm/stem volume clear. The socket's flexure slots also have room to
  open without immediately bearing against the hood.

The decorative hood is not automatically the bearing surface. Keep its wall,
the bearing/retaining socket, its mount and the motion void as distinct design
features even if they ultimately print as one connected part. A mount must
connect to real stock; unioning tangent shapes or a floating socket is not an
attachment. Reinforcement should stay inside the intended exterior.

Clear all original material from the mechanical pocket before adding the
socket. A long slot construction tool need not cut through a distant decorative
hood: bound it to the feature region only after proving the cavity and slot
free space are clear. Check the integrated result for refilled voids and for
mounts that stiffen a required flexure. A watertight mesh alone proves neither.

Plan an insertion route. The ball may enter through the lower opening with
elastic snap-in, or the design may need an assembled cover/split housing.
An opening hidden from view can still be inaccessible to fingers, fasteners,
support removal or assembly tools. A rigid operating sweep does not test
snap-in force or whether the socket can open inside the hood.

## Review evidence

Save a section or cutaway exposing the internal mechanism, a neutral exterior
view, and extreme operating poses from specified normal viewing directions.
Check the real final fixed/moving pair, with every hood/rim/rib/carrier present.
Measure wall/attachment and the corresponding output mesh, and compare the
combined exterior to the original at the same rest pose.

Describe concealment by view and pose. A top/front view can hide a socket that
is visible from below or when the arm is raised. Do not claim all-angle
concealment or full travel from a single favorable screenshot. A failed hood
layout should lead to an explicit rim, pivot, support, architecture or travel
revision; never silently enlarge the cover or reduce travel until checks pass.
