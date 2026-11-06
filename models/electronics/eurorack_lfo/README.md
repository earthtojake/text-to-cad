# Twin Orbit: a dual analog LFO for Eurorack, with its panel made from the board

Two voltage-controlled low-frequency oscillators in 10HP. Each has a **RATE** knob (exponential, 0.013 Hz to
80 Hz), a **CV** input that sweeps the rate, a **SHAPE** knob that crossfades triangle into square, a red/green
LED that breathes with the triangle, and **TRI**, **SQR** and **MIX** outputs. The board is a 2-layer KiCad
design; the front panel is a build123d model whose every hole is read from the board file, exported as a
laser-cut DXF and checked against SendCutSend's rules for 5052 aluminium.

**Why it is a good demo:** synth people love LFOs, and the story is the panel: *move a jack on the board and the
panel's hole moves with it*, then the panel goes straight to a fabrication service's checks.

## Where it stands

| | |
| --- | --- |
| Schematic | 3 sheets (root, `lfo.kicad_sch` placed twice, `power.kicad_sch`); 76 parts, 45 nets, 227 pins; ERC 0 errors, 0 warnings; KiCad's nets equal the drawn intent pin for pin (`scripts/check_schematic.py`) |
| Board | 48 x 107 mm, 2 layers, 1.6 mm; 76 parts (58 SMD, 62 on the back, panel parts on the front); 235 pads; 538 track segments, 1354 mm of copper track, 115 signal vias + 292 GND stitching vias; GND poured on both layers |
| DRC | JLCPCB 2-layer standard rules (track 0.25 / space 0.2, rails 0.4, via 0.8/0.4, copper to edge 0.3): **0 errors, 0 unconnected**; 69 warnings, all `lib_footprint_mismatch` (KiPy rounds a turned or flipped footprint's local coordinates by a nanometre, and the jacks' keepouts are rewritten from the library: see below); silkscreen 0 warnings (46 references printed, 30 in the dense expo cluster and under the jacks kept on the Fab layer) |
| Layout checks | `check_twin_orbit.py`: 0 segments off 45 degrees; no two-pad net over 1.6x its straight line; rails 0.4 mm (1.2 A for 10 C rise, 0.1 A needed); board == schematic, 0 differences; decoupling 2.2-5.5 mm from each supply pin except C106/C206, 8.8 mm from the LM13700's V- pin (it sits at pin 10, the buffer input tied to -12 V: a revision would move it) |
| Panel | 10HP x 3U, 2 mm, every hole read from the board; fit: worst overlap 0.000 mm^3 across 50 panel/hardware x board pairs and 435 hardware pairs; bushings clear their holes by 0.15 mm, LEDs by 0.25 mm (`src/check_fit.py`) |
| SendCutSend | the cut DXF in ALU-080 (5052 H32, 0.080"): every cut check passed (2026-11-06: holes, webs, hole to edge, size, units); the engraved legend is a separate file and a separate question |

## The circuit (per LFO; sheet `lfo.kicad_sch`, used twice)

| Block | Parts | What it does |
| --- | --- | --- |
| Exponential current source | Q101/Q102 BC857B pair, U101 section 1 (TL074) servo, R105 5.6 M, C101 100 p, D101 clamp | Iabc = 2.1 uA x exp(V(QB)/26 mV); RATE (B100k across the rails, 33k) and CV (33k) sum at the base node over 220 ohm |
| OTA integrator | U102 LM13700 (one OTA used, the other terminated), C102 100 nF C0G | the square (divided to +-260 mV by R111/R113) saturates the OTA, which charges C102 with +-Iabc: a linear triangle |
| Buffer and Schmitt | U101 sections 4 (follower) and 2 (Schmitt), R106 47k / R107 56k, R110 1k, D102 AZ23C5V1 | square clamped to +-5.8 V; triangle +-4.87 V; f = Iabc / (4 C2 Vp) = 1.0 Hz at 2 uA |
| Outputs | U101 section 3 (MIX follower), RV102 SHAPE B100k, R108/R112/R114 1k, Thonkiconn PJ398SM x 4, R109 2.2k + bicolour LED | TRI, SQR and the SHAPE crossfade, each through 1 k |

Power (`power.kicad_sch`): shrouded 2x5 Eurorack header (pin 1 = -12 V, red stripe), SS14 Schottky in each rail
(reverse ribbon blocks; 0.35 V drop at the ~25 mA the module draws), BLM21 220 ohm ferrite and 10 uF 25 V X7R bulk
per rail, 100 nF at every supply pin, test points for +12 V, -12 V and GND.

## Key parts

| Ref | Part | MPN |
| --- | --- | --- |
| U101, U201 | quad JFET op-amp | TI TL074CDR (SOIC-14) |
| U102, U202 | dual OTA | TI LM13700MX/NOPB (SOIC-16) |
| Q101-Q202 | PNP | Nexperia BC857B (SOT-23) |
| J101-J204 | 3.5 mm jack | Thonkiconn PJ398SM |
| RV101-RV202 | 9 mm vertical pot B100k | Alpha RD901F-40-15R1 |
| D103, D203 | 3 mm bicolour LED | Kingbright WP3VEGW, on a 3.5 mm spacer |
| J1 | 2x5 shrouded header | Sullins SBH11-PBPC-D05-ST-BK |

KiCad's library names a 3D model for the PJ398SM jack and the 9 mm pots but ships none, so
`src/footprint_models.py` draws both (from Thonk's and Alpha's drawings) and the project's copies of their
footprints (`twin_orbit.pretty`) name them under `${KIPRJMOD}/3dmodels`. The LED's footprint is KiCad's with its
model raised 3.6 mm, the spacer that brings the dome to the panel: KiCad's `LED_D3.0mm` model is 9.9 mm tall,
taller than a datasheet LED's body.

## Mechanics

10HP x 3U panel (50.5 x 128.5 mm, Doepfer A-100), 2 mm 5052 H32 (SendCutSend ALU-080, 0.080"), black anodised,
white legend. The board (48 x 107 mm) sits 10.0 mm behind the panel's back face: the pots' mounting face. The
jacks are 9.0 mm bodies with a 0.5 mm collar, so each gets a 0.5 mm spacer washer. Rail slots 3.2 x 5.2 mm at
x = 7.5 and 43.06 mm, 3.0 mm from the top and bottom edges. Holes: jacks 6.3, pots 7.3, LEDs 3.5 mm.
Hardware modelled: Davies 1900H-style knobs, M6 hex nuts (jacks), M7 hex nuts (pots), spacers.

## How the board was routed

The pcb skill routes by hand, never with an autorouter. Writing every vertex of this board's ~170 connections
by reasoning did not converge, so `scripts/assist_route.py` routes it instead: the agent states the order of the
nets, each net's layer and via costs and the GND ties, and an octolinear A* search on a 0.1 mm grid finds each
connection's path around every other net's copper, inflated by the clearance. It is an autorouter in all but
name, directed net by net, and a departure from the skill: whether the skill should offer such a search is an
open question, so it stays this project's script and no skill names it. Its result is `scripts/routes.json`;
`scripts/board_03_sync.py` puts the board back to that file without searching. The copper is DRC clean and
octolinear, but not what a careful person would draw: some detours and extra vias.

Moving a footprint over KiCad's API leaves its own keepout zones behind (KiPy moves a footprint zone's outline
by the move in the footprint's frame), so `scripts/board_02_keepouts.py` rewrites each jack's keepout from the
library footprint through the footprint's place, after every placement.

## Files

| Path | What |
| --- | --- |
| `twin_orbit.kicad_pro`, `.kicad_pcb`, `twin_orbit.kicad_sch` (+ `lfo`, `power` `.kicad_sch`) | the KiCad project (KiCad 10.99 format), the source |
| `twin_orbit.pretty/`, `fp-lib-table`, `sym-lib-table` | the project's footprints and its library tables (KiCad's stock libraries through `${KICAD10_FOOTPRINT_DIR}` and `${KICAD10_SYMBOL_DIR}`) |
| `check_twin_orbit.py` | the board's own checks |
| `scripts/` | how the board was made, re-runnable: libraries, schematic (and its intent, `schematic_intent.json`), netlist import, placement (`place_table.py`), routing (`assist_route.py`, `route_plan.json`, `routes.json`), pours, silkscreen |
| `src/` | the panel and its hardware: `footprint_models.py` (the jack and the pot), `hardware.py`, `panel.py`, `assembly.py`, `check_fit.py`, `check_dxf.py`, `exports.py`, `lib/twin_orbit.py` (what they read from the board) |

Nothing generated is committed: the footprints' 3D models (`3dmodels/`), the fabrication files (`fab/`), the
board's STEP and the panel's and assembly's files (`STEP/`, `GLB/`, `DXF/`) are written by the commands below,
and `.gitignore` keeps them out of Git.

## Rebuild

From this folder, with the `cad` command. KiCad's stock libraries are named through `${KICAD10_SYMBOL_DIR}` and
`${KICAD10_FOOTPRINT_DIR}`, which ERC, DRC and the generators read from the environment: set them to KiCad's own
folders first, or ERC counts every stock symbol as a missing library and DRC every stock footprint. KiCad's 3D
library needs nothing: the board's 3D view and its exports find it.

```bash
export KICAD10_SYMBOL_DIR=/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols      # macOS
export KICAD10_FOOTPRINT_DIR=/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints

# the 3D models KiCad's library lacks: run this before opening the board in 3D or exporting its STEP or GLB
cad run src/footprint_models.py                 # 3dmodels/: the PJ398SM jack and the RD901F pot

# check the board as it is
cad kicad_sch erc twin_orbit.kicad_sch
cad run scripts/check_schematic.py              # KiCad's nets == the drawn intent, both instances
cad kicad_pcb drc twin_orbit.kicad_pcb
cad run check_twin_orbit.py                     # prints nothing when the board is clean

# make the board again from its sources (each step states the board it wants; rerunning is harmless)
python3 scripts/make_libs.py                    # twin_orbit.pretty and the library tables
python3 scripts/gen_schematic.py                # root, LFO (x2) and power sheets
cad run scripts/board_01_import.py              # netlist -> board
cad run scripts/board_02_place.py               # outline + placement (scripts/place_table.py)
python3 scripts/board_02_keepouts.py            # the jacks' own keepouts back over the jacks
cad run scripts/assist_route.py                 # tracks + vias -> scripts/routes.json (about 3 minutes)
cad run scripts/board_03_sync.py                # or: the board back to routes.json, without searching
cad run scripts/board_04_pour.py                # GND pours both layers + stitching
cad run scripts/board_05_islands.py             # a via in any pour piece left without one
cad kicad_pcb drc twin_orbit.kicad_pcb --json > tmp/drc_before_cleanup.json
cad run scripts/board_06_cleanup.py tmp/drc_before_cleanup.json   # vias DRC calls dangling, same-net vias too close
cad run scripts/board_07_silk.py                # every reference to a free spot, or onto the Fab layer

# fabrication (JLCPCB 2-layer)
for k in gerbers drill pos bom pdf; do cad kicad_pcb export twin_orbit.kicad_pcb --to $k -o fab/$k; done
(cd fab && zip -qr gerbers_jlcpcb.zip gerbers drill)
cad kicad_sch export twin_orbit.kicad_sch --to pdf -o fab/schematic
cad kicad_pcb export twin_orbit.kicad_pcb --to glb -o GLB      # the board with its parts, to look at

# the panel, read from the board: the board's STEP with its origin at the board's top-left corner
cad run kicad-cli pcb export step --force --subst-models --user-origin 100x50mm -o STEP/twin_orbit.step twin_orbit.kicad_pcb
cad run src/hardware.py && cad run src/panel.py && cad run src/assembly.py
cad run src/check_fit.py                        # zero overlap, the intended clearances
cad run src/exports.py                          # DXF/ panel cut and art, STEP/ panel, assembly and hardware, GLB/ assembly
cad run src/check_dxf.py                        # the cut DXF's facts, for a SendCutSend preflight
```

`make_libs.py` and `gen_schematic.py` write the files they make byte for byte as committed. The layout steps
make the same placement and the same tracks again, from `routes.json` or from the search, and the pours'
stitching vias land within a few of where they were; DRC and the check stay clean.

## Demo video script (about 3 minutes)

The thread to keep: **the panel is made from the board.** Every shot builds toward shot 6, where a jack moves on
the board and the panel's hole follows, and shot 7, where the panel goes to a fabrication service's checks.
Record in an agent app with text-to-cad installed and this folder open; the viewer pages are `cad viewer` pages.

| # | Prompt the person types | What the viewer shows | Length | The one impressive thing |
| --- | --- | --- | --- | --- |
| 1 | "Design a Eurorack dual LFO: rate and shape knobs, CV in, triangle, square and mix outs, a bicolour LED, 10HP." | The schematic opening on its root sheet, then the Hierarchy: LFO A, LFO B, Power | 20 s | One LFO sheet placed twice: LFO B is the same circuit with 2xx references |
| 2 | "Walk me through how the rate works." | LFO A's sheet; the Nets tab picks net `/LFO A/QB`, the expo pair lights | 25 s | A real exponential converter servoed by an op-amp feeding an LM13700, with the maths on the sheet (0.013-80 Hz) |
| 3 | "Run ERC and check every pin landed on the right net." | Terminal: ERC clean (0 warnings); the pin-by-pin check: 0 mismatches | 10 s | The agent proves the schematic before touching copper |
| 4 | "Show me the board." | Board in 2D: copper front, then Flip for the bottom, the side with the ICs; Display > copper | 25 s | 2-layer, both GND pours stitched, DRC clean against JLCPCB's standard rules |
| 5 | "Now in 3D." | The corner's 2D/3D button: jacks, Alpha pots, LEDs and the shrouded header in place, every part on its model | 15 s | Every part has a 3D model; the jack and pot models the KiCad library lacks were drawn by the agent with the cad skill |
| 6 | "Make the front panel from the board, and prove it fits." Then: "Move the MIX jacks 2 mm down." | The assembly; then after the edit the panel model rebuilds and the hole has moved; the check prints worst overlap 0.000 mm^3 | 40 s | **The panel's holes are read from the board file**, not retyped: move a jack, the panel follows |
| 7 | "Get the panel ready for SendCutSend in 2 mm aluminium." | The panel DXF in the drawing viewer (CUT layer), then the preflight table | 30 s | Live SendCutSend catalog and specs: ALU-080, holes, webs, edge distance all pass, with citations |
| 8 | "Explode it." | The assembly GLB playing `explode`: knobs, nuts and panel lift off the board and settle back | 15 s | Knobs, nuts and spacers sit on the real stack-up (panel 10 mm off the board, on the pots' mounting face) |

Notes for the recording: run `cad run src/footprint_models.py` first, or the jacks and pots stand as blocks in 3D.
Shot 6's jack move is real but takes a reroute (about 3 minutes of `scripts/assist_route.py`): record the panel
half live and cut to the rerouted board, or move a jack whose hole is the point and show only the panel updating
(the panel reads positions, not copper). Keep the light theme for the schematic, dark for the 3D.
