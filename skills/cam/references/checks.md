# The verdict and the checks

Every `cadgen cam plan` runs every check that applies to its job and gives one verdict:

- **Ready to cut** (`verdict.status` `ready`): no check found an error. Warnings may remain.
- **N to fix** (`fix`): N errors. No G-code is written (`posts` is empty, `verdict.gcode` and the
  first warning say "G-code not written: fix N errors first", and the last run's posted files are
  gone), so nothing a machine could run stands beside the part. The GLB is still written: the
  Viewer shows the toolpaths and where each error is. Change the job and plan again.

The headline is what the Viewer's Job panel shows first: "Ready to cut · 42 min · 3 tools".

Each finding is one object in the result's `findings` (and one line of the CLI's output):
`check` (the check below), `severity` (`error`, `warning` or `info`), `type` (the particular kind,
such as `reach_flutes`), `summary` (one plain sentence), `description` and `items` (where: the
setup, the operation's index, the point `at` in part mm, and the numbers).

| check | level | what it means | usual fix in the job |
| --- | --- | --- | --- |
| `gouge` | error | a cutting move goes into the part beyond the tolerance | a smaller tool or stepover, `stock_to_leave_mm` on the roughing, a tighter `tolerance_mm` |
| `holder_collision` | error | the holder or shank, above the flutes, touches the stock or the part | a longer `stickout_mm`, a slimmer holder, a shallower operation from another setup |
| `reach` | error | the cut is deeper than the flutes or the stickout. A back bore is judged by its stickout only: the holder must stay over the stock's top with the head down under the part. Past a length the job did not state, a `not_judged` warning, not an error | a longer tool, or cut it from another side; a back bore: a longer bar (`stickout_mm`). `not_judged`: ask for the tool's real flute length and stickout |
| `rapid_into_stock` | error | a rapid move, or any move made with the spindle stopped, passes through uncut stock. A back bore's bar going through the hole spindle stopped is judged by its neck (`shank_diameter_mm`): a hit there is the hole not drilled through | raise `clearance_mm`, reorder operations; a back bore: drill the hole through first |
| `travel` | error | a move leaves the machine's travel (`machine.travel_mm`, `rotary_limits_deg`) | move `origin`, another setup |
| `fixture` | error | a move enters a fixture keep-out box (a box of the job's, or a vise's jaw, floor or parallel, or a plate: [job-file.md](job-file.md#fixture)); a tip resting on a box's top is no hit | change the region, move the part in the vise, another setup |
| `machine` | error | an operation needs an axis or a process the machine does not have | another machine kind, or another operation |
| `corner_radius` | warning | an inside corner is tighter than the tool's radius, so material stays in it | a smaller tool for those corners (`rest` or a second pocket), or accept the radius |
| `material_left` | warning | stock is left above the part after every operation, beyond the `stock_to_leave_mm` of the last operation that covered that place (a roughing's allowance does not excuse what its finish left) | add a finishing or rest operation where it says |
| `limits` | warning | a feed or speed was clamped to `max_feed_mm_min` or `max_rpm`, once per tool and limit, naming its operations. Under a spindle clamp a worked-out feed follows the slower spindle (the chip is kept, the cut is slower), but a feed the operation states is kept, so each tooth takes a bigger chip: the description gives the feed that keeps the planned chip. Under a feed clamp each tooth takes a thinner chip, which rubs and wears the tool. A tap slows its spindle instead, so its feed stays rpm x pitch | a spindle clamp on a worked-out feed: none, report it (a larger tool needs fewer rpm). A stated feed: lower it in step. A feed clamp: a lower `speed` on the operation, or a tool with fewer flutes |
| `empty_operation` | error (warning when it names no faces or region) | an operation put no cutting move in the program: nothing of its feature is left above it, or it was not below the material. Named faces or a region that get no cut means a missing feature, so it blocks the G-code; a facing pass over stock already flat only warns | check its faces or region, its depth and what the operations before it took off; drop it if nothing is left to do |
| `through_stock_bottom` | warning | a cut goes below the stock's bottom (a through drill's point, a profile's `through_mm`): whatever stands under the stock is cut too (not said where the same cut already enters a `fixture` box) | say what must be under it: a spoilboard, a sacrificial plate, or a gap between the parallels there |
| `long_stickout` | warning | an end mill stands out of its holder more than 4 times its diameter: it deflects and chatters | hold it shorter (`stickout_mm`), or take lighter cuts; state the real stickout |
| `full_slot` | warning | an operation cuts at the tool's full width for more than 5 of its diameters (a pocket's or adaptive clear's links from ring to ring); a `slot` is meant to | a smaller `stepdown_mm` or a lower `feed` is gentler; say it when the tool is small or the material hard |
| `prepared_hole` | warning | `assumes_prepared_hole`: a tap or an internal thread mill works a hole no earlier operation makes (drills, bores or mills three quarters of the way down; a spot drill does not count), so the job assumes the hole is already there | add the drilling first (the tap drill for a tap), or confirm with the user the hole is made before the job runs |
| `uncut_feature` | warning | a hole (along a setup's axis) or a pocket (its floor square to it) that a setup reaches and no operation cuts at least halfway down; holes of one size are one warning. Not judged on a blank from STEP | add the operation, or confirm with the user it stays as it is |
| `thin_wall` | warning | a hole or pocket the job cuts leaves under 1 mm of wall to the part's outside, measured halfway down it: the wall bends away from the cutter and chatters | light finishing passes on it, support it, or check with the user the part needs it that thin |
| `unused_tool` | info | a tool the job lists that no operation runs: it is not drawn, checked or posted | drop it, or check each operation's `tool` is the one meant |
| `fixture` (`assumed_fixture`) | info | a vise or plate was modelled with sizes the job does not state; it names each with the default used (`Setup top's vise is modelled with sizes the job does not state: jaws_along y, jaw_height_mm 40, ...`) | state the real sizes in the setup's `fixture` |

### Operations that cannot be planned, and posts that cannot write them

An operation the part makes impossible is an error finding on that operation (`check` `plan`),
and every other operation is still planned, so one run lists every refusal. Its `type` says
which:

| `type` | what it means | usual fix |
| --- | --- | --- |
| `empty_operation` | it would cut nothing: the feature is not below the material, nothing suits the tool | check the feature and the depth; drop the operation |
| `too_deep` | it would cut below what the part allows: a depth past the feature's floor, a facing below the part's top | leave the depth out to use the feature's own, or ask for less |
| `unreachable` | the tool cannot get there from this setup, or cannot come down there (a hole under a roof, no room to ramp, a helix pitch steeper than its ramp angle) | another setup from the side that reaches it, or what the summary names |
| `tool_too_large` | the tool does not fit the feature: a pocket narrower than it, a drill bigger than its hole | a smaller tool, or the tool of the hole's size |
| `tool_too_small` | the tool cannot make the feature as asked (a spot wider than the spot drill) | a larger tool |
| `gouge` | the only path the operation has goes into the part | redraw the region inside the material, or cut the feature by its selector |

A post that cannot write what the job needs (a tap on a controller with no spindle-synchronised
feed) is a `no_post_support` error (`check` `post`) on the operation. Either way no G-code is
written; the GLB still shows every operation that planned.

### Every finding's `check` and `type`

The `type`s are a closed set, so an agent can act on one by name:

| `check` | `type`s |
| --- | --- |
| `job` | `job` (the job was refused before anything was planned), `internal_error` (a bug in cadgen: report it with the job and the part) |
| `plan` | the kinds above (`empty_operation`, `too_deep`, `unreachable`, `tool_too_large`, `tool_too_small`, `gouge`), and `note` (info: what an operation did on purpose, such as a chamfer cut into a modelled edge) |
| `post` | `no_post_support` |
| `checks` | `setup_not_simulated` |
| `gouge` | `gouge_2d`, `gouge_3d`, `gouge_turning`, `gouge_multiaxis`, `swarf_skipped` (a swarf wall it could not judge), `not_judged` |
| `holder_collision` | `shank_part`, `holder_part`, `shank_stock`, `holder_stock`, `holder_multiaxis`, `not_judged` |
| `reach` | `reach_flutes`, `reach_holder`, `not_judged` (a cut past a flute length or stickout the job did not state) |
| `travel` | `travel`, `rotary_travel` |
| `material_left` | `material_left`, `not_judged` |
| `machine` | `machine_axes` |
| `drill` | `hole_size`, `hole_floor`, `tap_thread`, `no_hole_in_model` ([drilling.md](drilling.md#what-it-checks)) |
| `prepared_hole` | `assumes_prepared_hole` |
| `fixture` | `fixture`, `assumed_fixture` (info: the vise or plate sizes it assumed) |
| every other check | its own name: `rapid_into_stock`, `corner_radius`, `limits`, `empty_operation`, `through_stock_bottom`, `long_stickout`, `full_slot`, `uncut_feature`, `thin_wall`, `unused_tool` |

## What a check could not judge

A check never passes in silence. A setup the stock simulator cannot simulate (a side setup on a
3-axis mill's heightfield) gets a warning (`check` `checks`, `type` `setup_not_simulated`) naming
the checks that did not judge it (`rapid_into_stock`, `material_left`, and `holder_collision`
against the stock); a check that could not read what it judges says so with a `not_judged`
finding. The shank and holder are judged against the stock only in top and bottom setups on a 3-axis
mill's stock: elsewhere (a tilted or indexed setup, a mill4 or mill5) an info note says they were
checked against the part only. Each is an entry in the GLB's `checks.skipped` (`check`, `setup`, `why`). Tell the user
which setups went unchecked and that they must be air-cut first.

## Adapted steps

A part too big for the time and memory target is never refused: the run coarsens the stock grid,
loosens the sampling or keeps fewer simulation frames, and says each step in an `adapted:` line
(and `adapted` in the result) with what it cost. Report every one; the toolpaths themselves keep
the job's tolerance, only the simulation and checks are coarser.

## What the checks do not cover

The checks know the part, the stock, the tools and the boxes you gave (or the vise or plate built
from the sizes you gave, and the defaults the `assumed_fixture` note lists). They do not know the
user's real vise, clamps, tool lengths, work offsets, machine kinematics beyond the job, or whether
the stock is held well enough for the cut. Say so, and say that the program must be air-cut or run
single-block first.

The `fixture` check stands the tool along its setup's axis: a continuous 4th-axis wrap, swarf or
5-axis finish tilts the tool along its path, and that tilt is not judged against the boxes, so check
fixtures near those operations by hand.
