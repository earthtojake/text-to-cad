# Machining practice

How an experienced machinist would write the job. cadgen checks the program against the part,
stock, tools and fixtures you gave it; this page is what it cannot check: whether the plan is
a good way to make the part. Follow it when you write a job, and say where you departed from it.
Numbers here are conservative starting points for a rigid machine and carbide tools; a hobby
machine or a long tool wants less.

## Ask before you plan

Ask once, in one message, for what you cannot see and the user has not said. Never invent any of
these silently:

- The machine: its make and model (if it is in the catalog, `machine.model` brings its numbers,
  [job-file.md](job-file.md#machine-models)), else its kind and controller, travel, spindle speed
  range and tool changer. Any of these may be unknown: leave it out and the plan assumes the
  kind's usual value and lists it. Never fill one in from a guess of your own.
- How the part is held: vise, clamps, fixture plate, vacuum, chuck, collet. The vise jaw height
  and where the clamps sit become `fixture` boxes in the setup.
- The tools they actually have, with real diameters, flute lengths and stickouts, or their tool
  library file (`"tools": "my-tools.json"`). A plan with a tool they do not own is not a plan, and
  a guessed stickout is a guessed collision check: a length left out is assumed, and `reach` says
  it could not judge a cut past it.
- On a hobby machine or router, its spindle's speed range and its feed limit (`max_rpm`,
  `max_feed_mm_min`: a 24,000 rpm router spindle, a 1,000 mm/min feed): without them the plan
  cannot know them, and posts what the table says.
- The material and its temper: 6061-T6, not "aluminium"; annealed or hardened steel.
- Which features are critical (fits, bores, sealing faces) and the finish they need.

## Hold the part

- Hold it rigidly and as low as possible: the part sits above the vise jaws by the cut depth
  plus 2-3 mm, no more. Work held high chatters and moves.
- Never cut into the vise, clamps or table. Give every jaw and clamp as a `fixture` box; the
  `fixture` check then refuses any move into one, and the plan never comes down onto one. A vise
  grips `jaw height - parallels` of the stock: a grip of 0 or less holds nothing.
- Use as few setups as possible, and cut every feature that must line up with another in the
  same setup. Each re-clamp costs about 0.02-0.05 mm of accuracy.
- Plan the flip. The first setup makes a flat, square face the second setup can sit on. Leave
  stock (`margin_mm` on the bottom) where the second setup faces it off.
- Through cuts on a router or plate need a spoilboard or parallels under the part. Add a
  `through_mm` of 0.2-0.5 mm to break through, and tabs (`contour` `tabs`) so the part does
  not come loose and get thrown by the cutter. Tell the user to cut the tabs by hand after the
  program. A through drill goes the hole's depth plus its point plus `breakthrough_mm` (1 mm):
  make sure that much stands clear under the part (`through_stock_bottom` says where).

## Choose the tools

- **Shortest tool that reaches.** Stickout is the biggest single driver of chatter and tool
  breakage. Keep stickout under 3-4 x diameter; beyond that, cut lighter and say so. Give real
  `stickout_mm` and holder sizes so `reach` and `holder_collision` can judge.
- **Largest diameter that fits.** Use a big tool for roughing and open areas, and a small one
  only for the corners and slots that need it (`rest`, or a second `pocket` with the small tool).
- **Fewest tools.** Every tool change is time, a length offset to set, and on a manual-change
  machine a chance to get Z wrong. On GRBL a tool change is a pause for the operator to change the
  tool and zero it again: each tool is its own file.
- **Flutes by material:**
  - Aluminium and plastics: 2-3 flutes, sharp, polished or uncoated (ZrN or DLC are fine; avoid
    TiAlN).
  - Steel: 4-5 flutes, coated (TiAlN or AlTiN).
  - Wood and MDF: up-cut, down-cut or compression router bits.
- **Inside corners.** The corner radius on the part must be bigger than the tool radius: a pocket
  with R3 corners wants a tool of 6 mm or less. Pick a finishing tool with a radius 10-20 % below
  the corner radius, so it does not wrap a full 180° of the corner and chatter. The
  `corner_radius` warning names corners no tool reaches.
- **Corner-radius (bull) end mills** survive far better than sharp corners for roughing; use one
  when the floor allows it.

## Order the operations

1. **Face** the top so every depth is measured from a true surface.
2. **Rough** everything with stock to leave: `adaptive` or `pocket`, or `rough` in 3D. Leave
   0.2-0.5 mm on walls and floors (`stock_to_leave_mm`).
3. **Semi-finish** where the rough left steps bigger than the finishing tool should take (3D
   terraces, deep walls).
4. **Finish** walls and floors at full depth in one pass where the tool reaches, or in a few
   deep steps; the finish takes 0.1-0.3 mm radially.
5. **Holes:**
   1. Spot drill: one shallow spot per hole, so the drill starts true.
   2. Drill.
   3. Then ream, bore, tap or thread mill.
6. **Chamfer and deburr** last, and engraving last of all.

- Remove the material that keeps the part stiff last: finish thin walls and webs after the
  heavy roughing nearby, never before it.
- Group operations by tool only when the order above still holds.

## Cutting parameters

- **Climb milling** is the default on a CNC (`direction` `climb`). Use conventional only for a
  very loose machine or a hard, scaled skin.
- **Adaptive or high-efficiency roughing:**
  - 8-15 % of the diameter sideways (`stepover` 0.08-0.15).
  - Up to 2-3 x the diameter deep, if the flutes are that long and the tool is short.
- **Full-width slotting** loads a tool hardest. Take at most 0.5 x D deep in aluminium and
  0.25 x D in steel. Prefer an adaptive or trochoidal path whenever the slot is wider than the
  tool.
- **Pocket clearing** with offset paths: 40-50 % stepover, 0.5-1 x D stepdown in aluminium.
- **Finishing:**
  - 0.1-0.3 mm radially; full depth if the tool reaches.
  - 3D finishing stepover sets the scallop height: a ball of radius R at stepover s leaves about
    s² / (8R). For example, R3 at 0.3 mm leaves 0.004 mm.
- **Never plunge a flat end mill straight in.** Enter by helix (2-3° ramp, helix diameter at
  least 0.5 x D) or a ramp along the path. A straight plunge needs a centre-cutting tool and
  half the feed. The run counts every plunge and warns. The planners plunge only in air: the
  tool's whole circle off the stock and clear of the fixtures.
- **Arcs inside a hole** run their centre slower than their edge: the feed at the tool's centre is
  the table's scaled by the centre's radius over the edge's (never under a quarter), so the edge
  cuts at the planned chip.
- **Chip load.** Too light is as bad as too heavy: the tool rubs, heats and wears, and in
  stainless it work-hardens the surface. Do not cut feeds to be safe; cut depth instead.
- **Feeds and speeds** from the table are starting points. Tell the user:
  - Start at 70-80 % on the feed override, listen, and raise it.
  - Chatter usually means a lower RPM or a shorter tool. Squealing or blue chips mean the speed
    is too high or the tool is rubbing.
- **Thin walls** (`thin_wall`: under 1 mm to the outside) bend away from the cutter: finish them
  with light passes, after the heavy roughing near them.
- **Hobby and router machines** (GRBL, small routers):
  - Halve the depth of cut and keep the table's surface speed.
  - The spindle often cannot go slow enough for steel; say so rather than posting an RPM it
    cannot reach. `max_rpm` and `max_feed_mm_min` clamp the table, and the `limits` warning
    names each clamp.

## Materials

| material | do | avoid |
| --- | --- | --- |
| Aluminium | sharp 2-3 flute tools, high RPM, air blast or mist to clear chips, generous chip load | recutting chips (they weld to the edge: built-up edge), dull or TiAlN-coated tools |
| Mild steel | flood coolant, 4 flutes, moderate speed, steady chip load | dwelling in the cut, long stickout |
| Stainless | constant feed, sharp tools, flood, positive chip load at all times | rubbing or dwelling (it work-hardens), light finishing passes on a hardened skin |
| Titanium | low speed, high chip load, flood, rigid setup | heat build-up, interrupted light cuts |
| Brass, copper | sharp tools with zero or negative rake for brass; copper wants sharp, polished tools | grabby positive-rake drills in brass (it pulls them in) |
| Plastics (acetal, nylon, HDPE, acrylic) | single or 2-flute sharp tools, high feed per tooth, air blast | melting (too slow a feed or a dull tool), flood coolant on acrylic (it crazes) |
| Wood, MDF, plywood | compression or down-cut bits for clean faces, dust extraction, tabs | climb cuts against loose grain, cutting without extraction (fire and health risk) |
| Carbon fibre, G10 | diamond-coated or compression bits, vacuum extraction, a mask | dry cutting without extraction (the dust is a lung hazard), dull tools that fray edges |

## Holes and threads

- **Spot first**, with a spot drill of the same point angle or flatter, to a depth that makes a
  small chamfer.
- **Pecking:**
  - Drill deeper than about 3 x D with `peck`: full retract clears chips from deep holes.
  - Use `chipbreak` for medium depths in stringy materials.
  - Drill shallower holes in one go.
- **Tap drill sizes:** use the standard tap drill (M6x1: 5.0 mm, M5x0.8: 4.2 mm, M4x0.7:
  3.3 mm, M3x0.5: 2.5 mm). Blind threads need the drill at least 2-3 pitches deeper than the
  thread.
- **Tapping:**
  - Rigid tapping needs a spindle that synchronises (most industrial controls; not GRBL). The
    posts refuse a tap where the controller cannot hold the feed to the spindle: thread mill
    instead. A tap suits a hole drilled at its tap drill (major less one pitch) or drawn at its
    major diameter.
  - Tap only a hole an earlier operation drilled: `prepared_hole` warns when none did.
  - Taps run slowly; the table caps them.
- **Thread milling** is the safer choice in hard materials, big threads, and where a broken tap
  would scrap the part.
- **Reaming:** drill 0.2-0.3 mm under size (for 6 mm and up), then ream at about half the
  drill's speed and twice its feed.
- **Helix boring** suits a hole a little bigger than the tool; within a tenth of the tool's radius
  of the tool's own size, drill or ream it instead.

## Turning

- Grip the bar by at least 1 x its diameter in the chuck. With no tailstock, keep stickout under
  3 x the diameter; longer parts need a tailstock or a steady rest.
- Use constant surface speed (CSS) with a maximum RPM clamp (`machine.max_rpm`) suited to the
  chuck and the bar. An unbalanced or long bar at high RPM is a hazard.
- Part off as close to the chuck as the part allows, and cut a relief groove before a thread
  that runs up to a shoulder.
- Finish allowance: 0.2-0.4 mm on diameter, 0.1 mm on faces.

## Laser, plasma, waterjet and router cutting

- Cut holes and inner features before the outer profile (the plan does), so the part stays put
  while its details are cut.
- Lead in from the scrap side and pierce away from corners and edges (the plan does). A pierce
  on the part line leaves a blemish.
- **Plasma and waterjet:**
  - Small parts and cut-outs can tip up as they come free and hit the torch or nozzle. Add
    microjoints (`cut` tabs) to small parts and slugs.
  - Order the cuts so the head never crosses a freed part.
- **Plasma:**
  - Holes smaller than the sheet thickness come out tapered and rough; drill them instead.
  - The sheet must be flat and grounded. Height control (THC) needs the pierce and cut heights
    the post writes.
- **Laser:** give the kerf the machine actually cuts, measured on a test square.

## Wire EDM

- Every closed inside profile needs a start hole, drilled or burned before the job.
- Use `hold_mm` to keep the slug attached until a stop, so it does not drop and pinch the wire.
- Each skim pass improves finish and accuracy; one rough plus 1-2 skims is typical for a punch
  or die.

## Proving the program

Tell the user this every time, in these steps; it is how a shop proves a new program:

1. **Check the post matches the controller.** A program for one dialect can do something
   dangerous on another (Marlin reads `M30` as "delete a file").
2. **Set the work offset** (the setup's `wcs`) at the setup's origin, and measure every tool's
   length. On GRBL there is no tool table: re-zero Z on each tool's file.
3. **Simulate:** open `part.cam.glb` in the Viewer and play the cut. Look at every rapid near
   the part and the fixtures.
4. **Dry run above the part:** shift the work offset up 25-50 mm, run the program with the
   spindle on, and watch for any move that would have hit something.
5. **First real cut in single block** with the rapid and feed overrides at 25 %. Keep a hand on
   feed hold, and run full speed only after the first pass of each tool looks right.
6. **Measure the first part** before running more, and adjust tool wear offsets rather than the
   program.

Safety, always:
- Doors or guards closed, eye protection on, and loose clothing, hair and gloves away from the
  spindle.
- Never leave a first run unattended.
- Know where the emergency stop is before cycle start.
