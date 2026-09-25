# Mesh and CAD authoring contract

## Input and coordinate handling

Prefer GLB for scene hierarchy and transforms; OBJ is
acceptable (supply its MTL/textures for visual review), and STL is sufficient
for geometry. Runtime loading applies every scene-node transform, including
repeated mesh instances. The imported asset may still be one welded sculpture
even if it visually depicts many body parts.

`inspect_mesh` reports raw and position-welded topology in source coordinates.
It does not certify self-intersection freedom. `load_mesh` requires exactly one
of `height_mm` and `mm_per_unit`, plus `up="y"` or `up="z"`. Working geometry
is Z-up millimetres. GLB uses Y-up metres on output; STL is written in mm.
For reloading an output GLB use `up="y", mm_per_unit=1000`.
STL/OBJ have no dependable physical-unit contract; record the scale explicitly.

Welding ignores UV/normal seams only on the geometric working copy. Textures
are preserved in the untouched original, not promised on Boolean outputs.
Inspect the untextured silhouette and surface before deciding what will print.

## Project files

Keep ordinary mesh recipes in `recipes/`, original imports under the relevant
format folder's `imported/` subtree, derived outputs in `STL/` and `GLB/`, and
readable reports in `reports/`. CAD feature scripts still use `src/`, `@step`
and `STEP/` according to the CAD workflow. A mesh recipe runs as ordinary
Python; it is not a new return type for `@step` and has no implicit freshness
cache. It explicitly names its inputs and writes its derived outputs.

Group multiple joints in a shared factory with names and transforms. Rebuild
from the recipe; never patch exported triangles by hand. Every report should
include the input path, physical scale, repair/simplification settings,
parameters, validation tolerances and tested motion domain.

## Mechanical CAD handoff

After [joint-design.md](joint-design.md) and
[joint-layout.md](joint-layout.md), use `$cad` when available to author the selected
mechanism. Read its local instructions and relevant modeling/positioning references.
Pass the actual design, not merely "make a joint":

- Mechanism and required freedoms/travel, rest pose, axes/local frames and any
  coupling or unwanted movement to restrain.
- Physical scale, measured local sections/depth, chosen dimensions in mm, fit-gap
  conventions, minimum walls/roots, permitted modification region and protected skin.
- Ownership of each feature/printed part, separate hardware or inserts, assembly
  route, retention/stops and the validation targets.

Produce labeled closed CAD solids and editable source, exact mechanical STEP and
named mating datums. Separate **additive stock**, **functional void tools** and
**independent assembly parts**. These are authoring roles, not a new runtime API.
Keep mating members and cutters derived from shared parameters; do not independently
approximate a matching hole in the mesh recipe. Declare the CAD-to-sculpt transform
and tessellation tolerance explicitly and use the same geometry/parameters for the
STEP and the Boolean recipe.

Validate CAD soundness, critical dimensions, mating alignment, engagement and the
neutral assembly. Review a STEP snapshot. If `$cad` is unavailable, state that and
use `from cadgen import build123d as bd` and `@step` in the installed runtime for
an equivalent parametric source; check dimensions/alignment and run
`cadgen step inspect validate` plus `cadgen step snapshot` on the resulting STEP.
Do not invent unavailable factories or load runtime code from another skill directory.

## Mechanical integration

A planar split caps both pieces but does not infer anatomy or avoid fragile
features. Use closed regional masks for natural seams, retained hoods or overlapping
covers; record region ownership and the actual seam gap. Convert validated CAD
with `from_cad` and apply the declared placement exactly once.

For each printable host, form the intended stock from its sculpt region and assigned
CAD additions, then subtract that host's complete functional voids. In symbolic
terms, `part_i = (sculpt_region_i union additions_i) difference voids_i`.
Leave separate pins, clips, bushings and covers as independent parts. Unioning all
mechanical bodies together would lock the mechanism. A GLB group does not fuse them.

Clear organic stock that would fill a bore, bearing cavity, guide channel, flexure
slot or assembly passage, including stock reintroduced by a mount/reinforcement.
For a mechanism enclosed in a decorative hood, a bounded pocket can clear the
sculpt first, followed by CAD attachments and their functional voids. Scope tools
to their owning parts and intended region; a pin-bore cutter must not drill the pin
itself, nor a construction slot cut a remote cover. Check that bounded tools still
clear the entire required cavity/access region.

Check intended component counts, stock overlap and retained attachment thickness.
Protect bearing surfaces, guides, stops and retainers during motion relief. A
watertight mesh does not prove that a root is thick enough, a snap can flex or a
mechanism can be assembled. If clearance cuts violate requirements, revise the
axis, mechanism, dimensions or segmentation explicitly; do not silently reduce travel.

## Ball-socket helper branch

Use this branch only after selecting a ball socket. Other mechanisms use the same
CAD handoff and Boolean roles with their own authored solids.

`ball_socket` returns CAD `male`, `socket`, `socket_blank` and `socket_void`.
The origin is the ball centre, with the stem along -Z. Apply the same placement
to all four before integration. Union the male with its host. On the other host,
union the socket blank then subtract the full cavity/entry/slot tool; simply
unioning the finished socket leaves the sculpt filling its voids. In a separate
hood, first clear the mechanical pocket and verify flexure room after integration.

Pass explicit parameters derived from the local measurements. The helper's 5 mm
ball radius, 0.2 mm radial gap and 0.8 mm slit are coupon defaults, not a sizing
method or process-calibrated tolerances. The opening is smaller than the ball, so
assembly requires elasticity, a split housing or another retention design. A rigid
operating sweep cannot validate insertion force. Use a coupon matching the material,
layer height, orientation and integrated attachment stiffness for fit assessment.
