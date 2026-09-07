# Physical reaction comb work

`lib/guide_mounts.py` now provides `guide_end_registry()` for all 254 unique
fixed liner-end datums, merging adjacent paths at a shared point/tangent/frame.
The capstan follower upstream mouths are intentionally free; their downstream
mouths are fixed. The manifest is
`../../validation/anthropomorphic_hand/guide_mount_endpoint_manifest.json`.

`make_phalanx_comb(length, width, station, lanes, label)` builds eight real
bodies: two split comb jaws, two exact rail saddle caps, two liner-clamp screws,
and two rail-clamp screws. Each lower jaw includes the curved support branches
and the two lower rail saddles. The original phalanx solid is subtracted from
the saddle blanks to form exact mating faces. No skeleton drilling or shape
change is needed. Liner jaw split gaps are 0.08 mm, providing travel beyond the 0.04 mm bore/liner diametral clearance; rail saddle gaps are 0.02 mm; the guide bores are R0.47, outer
scallops R0.57 and axial length 0.55 mm. Hardware uses nominal M0.6 shanks and
real hex socket heads; thread helices are omitted.

`phalanx_guide_mounts()` returns `(shape, frame, system, kind)` tuples already
placed in the assembled neutral finger fan. Do not fan them twice. It currently
builds three comb stations for each of the four fingers: MCP outlet, PIP inlet,
and PIP outlet. These cover 32 unique fixed datums. Two adjacent guide ends at
an MCP/PIP outlet share one bore.

The dedicated review model is `guide_comb_review.py`. Its straight tendon/liner
stubs illustrate the bores; they are review context, not alternative accepted
routing. Exact production-path checks use `check_guide_combs.py` in validation.

Remaining hardware: the fixed curved-guide drive outlets, all yaw-reaction
ends, palm inlets/cup frames, thumb reaction ends, and the 98 forearm-owned
endpoints. CMC inlet spacing needs a shared thin-web comb rather than separate
R0.57 collars. Do not consider all guide reactions anchored yet.

## Palm banks and remaining prototypes

`lib/palm_guide_mounts.py` and `palm_guide_mounts_review.py` supply the index,
middle and ring palm banks: 42 unique mouth datums, attached by exact split
clamps around the original MCP palmar bearing bosses. The three groups contain
67 real solids. All placements are already fanned and every part belongs to
`wrist_flexion`. The ring bank's host truss divides its back jaw into two real
pieces; its front cap and cross bolts tie those fitted pieces to the host.
The adjacent index/right and middle/left side posts sit at local |X|7.2 mm;
other posts sit at |X|8 mm. Nominal guide bores are R0.47 and jaw splits0.08 mm.
The final revision relieves structural metal around caps and screw heads.

The pre-relief narrowed banks cleared all48 full neutral routes (302 exact
curve/solid distances), and all original palm solids. Final relief removes
material only. See `palm_guide_banks_body_report.json` for the passing final mutual/host
gate and `palm_guide_mounts_validate.json` for strict geometry. Native macro:
`../../renders/anthropomorphic_hand/palm_guide_mounts_macro.png`.

Unaccepted prototypes are separate: `lib/fixed_guide_mounts.py` builds16 drive
outlet mouths (80 bodies) across four fingers. These clamp the actual curved
liner0.425 mm upstream of its end, oriented by its exact Bezier tangent.
Middle full local sweep clears every guide and host across29 poses, including
the combined fist. Family strict validation passes80/80 real solids. Other
three finger sweeps and complete assembly validation remain required. The family artifact is
`fixed_outlet_mounts_review.step`; do not treat its build as full acceptance.

`lib/yaw_guide_mounts.py` is unfinished and must not be integrated: its negative
carrier hub clamp is cut into two pieces by the original carrier branch and
currently fails the one-solid builder assertion. Its source includes open
240-degree outlet jaws to clear the adjacent flexion drums, plus actual M0.4
pinch screws. It still needs a coherent host attachment and full route checks.

Wrist drive mouths, cup/little inlet banks and the non-CMC thumb mouths have
not been built here. Forearm builder owns96 forearm mouths; thumb specialist
owns12 CMC mouths. After phalanx32+palm42+forearm96+CMC12 there are72 unique
datums remaining, including the unaccepted fixed16 and yaw8 above. The old
manifest predates the accepted CMCY16 change; regenerate it from the current
`guide_end_registry()` before auditing thumb coverage.
