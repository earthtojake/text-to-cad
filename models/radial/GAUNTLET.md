# Gauntlet log

Protocol: per part, a fresh-context critic sees only two images — our in-context
render (presentation envelope, presentation-large) and a museum/restoration
photograph — as `a.png`/`b.png` in random order (`tools/critic_pack.py`; keys in
`tmp/critic/keys/`, never shown to critics). Question: "which is more beautiful?"
On a loss the critic names ONE largest gap, which goes back to the owner.

## Part rounds

| round | part | reference | ours | verdict | gap named (for the loser) | routed to |
|---|---|---|---|---|---|---|
| rods_r1 | rods | P_rods_01 | a | LOST (high) | "articulating rods look like stubby brass cup bushings on clevis stubs; no shanks reach the pistons" — the cups are the tappet guides in FRONT of the window: the rods are not visible in context | layout (window / nose cutaway / camera) |
| crankshaft_r1 | crankshaft | P_crank_01 | b | LOST (medium) | "bronze sleeves float in the foreground and dwarf everything; the throw, counterweight and master-rod hub are hidden" — again the tappet guides, floating because the nose case is not built yet | cam (guides' look) + layout; part rounds paused until the core statics exist |
| heads_r2 | heads | P_head_04 | b | LOST (high) | "rocker boxes are oversized flat-lidded rectangular blocks that dwarf the heads; should be small rounded cast housings blending into the head, beside tall thin tightly pitched fins" | heads |
| barrels_r2 | barrels | P_barrel_02 | b | LOST (high) | "barrel fins read as a flat black block of shallow grooves; should be thin, deep, evenly spaced discs with light between them" | barrels |
| pushrods_r2 | pushrods | B_02 | a | LOST (high) | "tubes read too thick (~1/3 cylinder width), crossing in a chaotic V, bulky gold sleeves pile up at the case; should be slim, one size, evenly spaced" | pushrods (+ cam: bronze guide flanges) |
| pistons_r2 | pistons | P_piston_02 | a | LOST (medium) | "black speckled z-fighting on the wrist-pin boss; skirt ends in a flat faceted diagonal chop like a truncated cone; show the hollow interior, ribbed bosses, clean pin bore" | pistons |
| valvetrain_r2 | valvetrain | P_head_03 | b | LOST (high) | "the two pushrods rise vertically through the middle of the cutaway, across valves, springs and chamber" | layout: section moved to cylinder 1's REAR half (no pushrods in front of it); front star now complete |
| crankcase_r2 | crankcase | B_03 | b | LOST (high) | "front is a cut-open jumble of gear rings behind the prop hub, no readable nose case or harness ring" — nose case and harness not built yet at render time | nose / ignition (in progress); re-run |
| valvetrain_r3 | valvetrain (rear section view) | P_head_03 | a | LOST (medium) | "section faces are the same grey as everything else, so walls, ports and chamber don't read; cut plane should be one distinct flat colour, solid wall around a carved chamber" | layout: museum-red section skins on every cut face (geo.cut_with_skin, palette.SECTION_RED) → heads, barrels, pistons, intake, exhaust, ignition, crankcase, nose |

### Layout decisions forced by round 3 (whole-engine renders)
- The FRONT exhaust collector hid the head-on star in every front view → exhaust moved to the REAR (rear-facing ports on the -t side, collector behind the cylinders). Heat tint re-based to warm stainless grey.
- The nose cutaway's retained collar blocked every line of sight to the crankcase window → cutaway reworked so the rods show from the front-right three-quarter.
- The mount ring's top arc crossed the rear section view → mount keeps the top clear.

### User direction (2026-09-23)
Part-level rounds stop after the in-flight iterations (heads rear exhaust port + red section, blower radial outlets → intake re-route, nose sightline, accessory). The user judged the parts good enough; no part has a recorded blind-A/B win. Work proceeds to the layout fixes, then the whole-engine gauntlet (four views), validation and animations.

## Whole-engine gauntlet, round 1 (after the layout pass; rear view held back for its declutter)

| view | reference | verdict | gap named for ours |
|---|---|---|---|
| dead front | A_01 | LOST (high) | propeller blades cut across a third of the star, breaking the nine-fold rhythm |
| dead front | A_06 | LOST (medium) | cylinders nearly vanish: heads read as small knuckles, fins as flat fanned blades; want nine bold finned masses, not eighteen spokes |
| front three-quarter | B_01 | LOST (high) | red nose cutaway reads as a flat sticker; blades hide half the engine |
| front three-quarter | B_03 | LOST (medium) | barrels short dark stubs, shallow head fins, mushy grey; want bright finely layered stacks |
| section (rear) | C_03 | LOST (high) | head cut face one flat dark-maroon block; want bright red thin walls branching into a cut fin comb |
| section (rear) | C_04 | LOST (high) | piston reads as an uncut black dome; want the crown, grooves, rings and pin bore cut in red |

Actions: feathered propeller blades (edge-on from the front); heads — denser deeper wrap-around fins, no solid section web; piston-1 crown section; nose cut faces machined not red; palette — brighter section red, crisper cast aluminium, glossier grey enamel; rear declutter (slim tucked collector, slimmer mount, jewelled magnetos) before the rear view is judged.

## Whole-engine gauntlet, round 2

| view | reference | verdict | gap named for ours |
|---|---|---|---|
| dead front | A_01 | LOST (high) | the (feathered) prop still crosses the star; uniform chrome sheen, fins/heads need tonal depth |
| dead front | A_06 | LOST (medium) | cylinders lost behind a cage of 18 long pushrods converging on the hub; heads small boxy blocks; want bulbous sculpted heads, rods secondary |
| front three-quarter | B_01 | LOST (high) | blades cross the engine; the centre shows gear-train internals where a closed dome should be |
| front three-quarter | B_03 | LOST (medium) | the nose is an open, exposed gear train with red tabs and loose fittings; want a smooth domed nose case with an even bolt ring |
| section (rear) | C_03 | **WON** (medium) | — "clean, symmetric, fully readable section: valves, springs, rockers, crown and rod small end in profile" |
| section (rear) | C_04 | **WON** (medium) | — "whole valve train clear and symmetric, framed by crisp red section fins" |
| rear | D_01 | LOST (high) | a thick plain dark torus (the collector) floats outside the cylinders like a hoop; accessory case a flat disc with plain cans |
| rear three-quarter | D_08 | LOST (medium) | a thick bronze ring and a black inner ring circle the rear face; black rods (mount truss stubs) end in mid-air; collector should sit tucked forward behind the cylinders |

Actions: nose cutaway closed (smooth domed nose case — the crankcase window is still seen through the gap the nose shift opened); mount stubs removed and ring tucked forward to the blower lugs; collector tucked forward behind the heads; accessory case given real gearbox castings; heat tint brightened; heads' bolder fins in progress.

## Whole-engine gauntlet, round 3 (nose closed, rear decluttered, feathered prop, final geometry)

| view | reference | verdict | gap named for ours |
|---|---|---|---|
| dead front | A_01 | LOST (high) | cylinders small and set back behind long thin pushrods; black gaps between cylinders — reads as spokes; want large closely finned barrels + heavy heads filling the ring |
| dead front | A_06 | LOST (medium) | cylinders are flat stacks of thin fins with no body; pale boxy rocker boxes; want bulbous finned cast heads wrapping the boxes + visible dark finned barrels |
| front three-quarter | B_01 | LOST (high) | cylinders read as a few thin widely spaced plates over a dark hollow core; want dense fins rising into large cast heads — one heavy mass per cylinder |
| front three-quarter | B_03 | LOST (medium) | head/barrel fins thin, shallow, spaced apart with dark core showing; want deep closely spaced wrap-around fins |
| section (rear) | C_03 | LOST (medium) | black piston crown swells into the valve heads, no readable chamber; piston rings don't read; red reads dull maroon |
| section (rear) | C_04 | LOST (medium) | piston a flat black dome nearly invisible against the cut face; want bright machined aluminium with ring lands |
| rear | D_01 | LOST (high) | accessory section plain grey cylinders/discs inside an oversized open exhaust ring with a detached stub |
| rear three-quarter | D_08 | LOST (medium) | thin collector ring floats behind the engine like a hoop; should hug the exhaust ports at head height with short stacks |

Note: the section view WON both comparisons in round 2 with a near-identical render; verdict variance at this level is high. The persistent, consistent gap across all front views is cylinder MASS (fin density/depth and head volume); the head builder's full wrap-around fin stack failed to build (OCC fuse/cut robustness, 4 attempts).

## Whole-engine gauntlet, round 4 (final: mass pass — wrap-fin heads, 17-fin barrels, bright pistons, heavier collector, richer accessory case, re-routed leads)

Renders `tmp/final/g4_*.png` from the final STEP/radial.step (2026-09-25 02:51); packets `tmp/critic/w4_*`.

| view | reference | verdict | gap named for ours |
|---|---|---|---|
| dead front | A_01 | LOST (high) | uniform satin grey everywhere; want a varied warm palette (brass/bronze boxes, dark enamel cylinders, copper leads) and wear |
| dead front | A_06 | **WON** (medium) | — "symmetrical radial composition, crisp chrome against a dark field, one intentional object" |
| front three-quarter | B_01 | LOST (high) | same: single satin grey reads as plastic; want brass/bronze boxes, dark pushrods, olive case, some wear |
| front three-quarter | B_03 | **WON** (medium) | — "engine isolated against a dark backdrop, propeller sweeping diagonally, polished metal: one sculptural composition" |
| section (rear) | C_03 | LOST (medium) | head section a flat maroon slab edged with stair-stepped rectangular fins; want tapered fins following the head curve and a shaped chamber and ports |
| section (rear) | C_04 | **WON** (medium) | — "balanced, symmetric, tells the whole story from rockers to con-rod" |
| rear (dead) | D_01 | LOST (high) | sparse and clean between the collector and the case; want dense plumbing, leads and brackets weaving over the cylinders |
| rear three-quarter | D_08 | **WON** (medium) | — "clear radial layout: collector frames the finned cylinders and the magnetos, red cutaway a focal point" |

Result: 4/8, the first round to win every view against at least one reference. Front and front three-quarter now split: the gap moved from cylinder MASS (fixed) to MATERIAL PALETTE (monochrome satin grey vs. restored brass/olive/black). Per the user's direction this was the last round; the work finishes here regardless of result.
