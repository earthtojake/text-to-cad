# Orbit: a round LED ring clock

A 120 mm round clock face with an outer ring of 60 addressable RGB LEDs (minutes and seconds) and an inner
ring of 12 (hours), an ESP32-C3 on Wi-Fi time, USB-C power and data, auto-dimming from an ambient light
sensor. Three printed parts go round it: a black baffle with a cell for every LED, a thin translucent diffuser,
and a desk stand that holds the clock tilted back 12 degrees with its USB cable hidden underneath.

**Why it is interesting.** The 72 LEDs and 72 capacitors are placed by a few lines of code from a radius and a
count; the LED data chain runs round both rings as copper arcs, one per link; and the baffle's 72 cells line
up with the LEDs because the CAD model reads every LED's position from the saved board file, not from the
script that placed it.

| | |
| --- | --- |
| Board | 120 mm circle with a flat for the USB-C receptacle, 4 layers, 1.6 mm, JLCPCB standard 4-layer rules |
| Parts | 182 footprints: 72 x WS2812B-2020, 72 x 100 nF, ESP32-C3-WROOM-02, USB-C, 26 others |
| Nets | 91; 536 tracks (1.77 m of copper), 71 arcs (the LED chain's links among them), 256 vias |
| Checks | ERC clean (0 warnings); DRC 0 errors, 0 unconnected; 102 warnings: 101 `lib_footprint_mismatch` (footprints placed, turned and flipped over KiCad's API no longer compare equal to their library's) and the module's own silkscreen outline running past the board edge at the antenna |
| Printed | baffle (black PLA), diffuser (natural PETG, 1.2 mm), stand (black PLA); 3MF of each and a two-material front |

## The design

**Front (F.Cu): the face.** The 60 minute LEDs sit on a 50 mm radius, D1 at 12 o'clock, clockwise; the 12 hour
LEDs on a 38 mm radius. Each LED is turned so its local +y points out of the ring: its DOUT (inner row) faces
the next LED and its DIN (outer row) the previous one, so each link is a single arc from one DOUT to the next DIN.
Each LED's 100 nF sits 2.45 mm inside it, with a +5V via and a GND via under its two pads and a GND via outside
the ring at the LED's VSS pad. The ambient light sensor (LTR-303ALS-01, I2C) is at the centre, behind a window
in the baffle. Between the rings at 12 o'clock: the hop from the minute ring's end to the hour ring's start, and
the data input as an arc on a 43.5 mm radius.

**Back (B.Cu): the electronics.** The ESP32-C3-WROOM-02 at the top edge with its antenna at the board's edge and
a keep-out (no copper on any layer, 5 mm round the antenna, Espressif's rule); the USB-C receptacle on the flat at
the bottom; its USBLC6-2SC6 ESD array in line (flow-through), 5.1k CC pull-downs, a 3 A polyfuse, a 470 uF bulk
capacitor and 22 uF; an AP2112K 3.3 V regulator; a 74AHCT1G125 shifting the LED data from 3.3 V to 5 V with 33 ohm
at the driver; BOOT and RESET; test points for 5V, 3V3, GND, TX and RX (and TP6 at the chain's end on the front).
The CC1/CC2 voltages go to the ESP32's ADC so firmware can cap the LED brightness to what the source advertises.

**Power.** Worst case: 72 LEDs x 3 colours x 12 mA = 2.59 A, plus the ESP32-C3's RF peak (~0.35 A): ~3.0 A, the
most a USB-C source gives at 5 V. The LEDs draw from In2.Cu (a whole-board +5V plane) and return through In1.Cu
(a whole-board GND plane), each by its own vias, so no track carries the ring's current. VBUS runs from both
receptacle pad pairs (0.6 mm stubs, 1.65 A each, IPC-2221 outer 1 oz 10 C), 1.0 mm into the 1210L300 polyfuse
(3 A hold, 6 A trip), out into In2 by two vias. **Why 4 layers:** the 72 LEDs need +5V and GND everywhere round
two rings, the back carries the routing, and the antenna and USB need an unbroken ground: two planes do all three.

**Rules (JLCPCB standard 4-layer, from the pcb skill's manufacturing reference, read 2026-11-04):** 0.15 mm
clearance and minimum track (JLCPCB 0.09/0.09), 0.2 mm signal, 0.6/0.3 mm vias, 0.2 mm minimum drill (the
module's own thermal vias), 0.3 mm copper to edge, 0.19 mm hole clearance (GCT's USB4105 land pattern),
silkscreen 1.0/0.15 mm. Netclasses Default, Power (+5V, VBUS 0.8 mm) and USB in `orbit.kicad_pro`.

**The libraries.** The project carries its own symbols and footprints (`orbit.kicad_sym`, `power.kicad_sym`,
`orbit.pretty`), copied from KiCad's stock ones by `scripts/build_libraries.py`, so ERC and DRC need no library of
the person's. Each footprint names the stock 3D model KiCad's library holds for it (`${KICAD10_3DMODEL_DIR}/...`),
which the board's 3D view and its exports find, but for the two KiCad names and does not ship: the WS2812B-2020
and the LTR-303ALS-01, whose models `src/part_models.py` draws into `orbit.3dshapes/` (`${KIPRJMOD}`).

**The printed parts** (`src/orbit.py`) read the board: the outline (its arc's circle and its flat), the four M3
holes and all 72 LEDs from `orbit.kicad_pcb`, every part's 3D extent from the board's STEP.
- **Baffle**, 8 mm: 60 wedge cells (1.6 mm walls of constant thickness) and 12 round light pipes (7.6 mm), a
  window over the light sensor, pockets underneath for every part outside a cell, M3 pilot holes on the board's
  holes (M3 x 8 self-tapping screws from the back), four peg holes for the diffuser. Prints as modelled, board side
  down.
- **Diffuser**, 1.2 mm natural PETG with a 0.5 mm chamfer and four 3 mm pegs. Prints face down
  (`diffuser_print`). Or print both as one: `front_print` is the diffuser and the baffle stacked as one
  two-material job (face on the plate).
- **Stand**: a 112 x 66 x 34 mm plinth with a saddle that holds the stack by its rim (slot 0.3 mm clear, a lip
  that covers only the outer 4.4 mm of the face, a 6 mm back wall with pockets for the receptacle and the
  polyfuse), tilted back 12 degrees; a pocket for the USB-C plug straight down from the receptacle and a
  45-degree-roofed cable channel under the plinth to the back.

## Files

| Path | What |
| --- | --- |
| `orbit.kicad_pro`, `orbit.kicad_sch` (+ `power`, `mcu`, `minutes`, `hours` `.kicad_sch`), `orbit.kicad_pcb` | the KiCad project (KiCad 10.99 format), the source |
| `orbit.kicad_sym`, `power.kicad_sym`, `orbit.pretty/`, `sym-lib-table`, `fp-lib-table` | the project's libraries |
| `check_orbit.py` | the board's own checks (schematic vs board, current, decoupling, the antenna keep-out) |
| `scripts/build_libraries.py` | builds the libraries from KiCad's stock ones |
| `scripts/schematic.py` | the schematic |
| `scripts/geometry.py`, `scripts/board.py`, `scripts/routing.py` | the board: setup, place, route, zones, silk |
| `src/part_models.py` | the two 3D models KiCad lacks (WS2812B-2020, LTR-303ALS-01) |
| `src/orbit.py`, `src/check_fit.py`, `src/exports.py` | the printed parts, the assembly and its explode, the fit check, the deliverables |

Nothing generated is committed: the two part models (`orbit.3dshapes/`), the fabrication files (`fab/`), the
board's STEP and the printed parts' files (`STEP/`, `XBF/`, `GLB/`, `3MF/`, `DXF/`) are written by the commands
below, and `.gitignore` keeps them out of Git.

## Rebuild

From this folder, with the `cad` command:

```bash
# the two 3D models KiCad's library lacks: run this before opening the board in 3D or exporting its STEP or GLB
cad run src/part_models.py                       # orbit.3dshapes/

# check the board as it is
cad kicad_sch erc orbit.kicad_sch
cad kicad_pcb drc orbit.kicad_pcb
cad run check_orbit.py                           # prints nothing when the board is clean

# make the board again from its sources (each stage states the board it wants; rerunning is harmless)
cad run scripts/build_libraries.py               # the project libraries from KiCad's stock ones
cad run scripts/schematic.py                     # the schematic (a sheet that holds symbols is left alone)
cad run scripts/board.py all                     # setup, place, route, zones, silk

# fabrication files
for k in gerbers drill pos bom pdf; do cad kicad_pcb export orbit.kicad_pcb --to $k -o fab/$k; done
cad kicad_sch export orbit.kicad_sch --to pdf -o fab/schematic
cad kicad_pcb export orbit.kicad_pcb --to dxf -o DXF            # the outline and drilled holes
cad kicad_pcb export orbit.kicad_pcb --to glb -o GLB            # the board with its parts, to look at

# the printed parts, read from the board: its STEP with every part, converted once to an xbf
cad kicad_pcb export orbit.kicad_pcb --to step -o STEP          # STEP/orbit.step
cad step export STEP/orbit.step XBF/orbit.xbf
cad run src/orbit.py                             # prints each model's id
cad run src/check_fit.py                         # interference and clearances, also written to tmp/fit.txt
cad model dfm <baffle id> --process printing --angle-limit 45    # and the stand, diffuser_print
cad run src/exports.py                           # 3MF/ of each printed part and the two-material front,
                                                 # STEP/orbit_assembly.step, GLB/orbit_assembly.glb
```

`build_libraries.py` writes the libraries byte for byte as committed, and `board.py all` makes the same
placement, tracks and vias again. After a board change, export the STEP and the xbf again before
`cad run src/orbit.py`: the printed parts follow.

## Checks and their results

- **ERC**: clean, 0 warnings. **Board vs schematic**, pin by pin: 540 pins, 0 differ.
- **DRC** (the board's JLCPCB rules): 0 errors, 0 unconnected; 102 warnings: 101 `lib_footprint_mismatch`
  and the module's own silkscreen outline running past the board edge at the antenna.
- **Antenna**: nothing poured on any layer and no via under the antenna keep-out (736 sample points). The
  module's own keep-out (a rule area inside its footprint) was left 88 mm right of the module as the footprint
  was placed over KiCad's API, so a board-level keep-out over the antenna is the one that holds.
- **Decoupling**: every LED's VDD pad 1.91 mm from its 100 nF; U1 3V3 1.83 mm, U4 2.13 mm, U2 in 2.38 mm, U2 out
  3.13 mm (review: over the 3 mm guide), U5 1.42 mm.
- **Fit** (`src/check_fit.py`, the assembly as built, every board solid against each printed part):
  interference **0.000 mm3** between the board's 598 solids (the PCB and its 172 parts' models) and the
  baffle, the diffuser and the stand, and 0 between the printed parts. Clearances: baffle 0.14 mm over the PCB
  (it rests on it when screwed), 0.40 mm over every part in a pocket (R3/R4/R6/R8/R9, C9/C10, U5); stand
  0.30 mm round the board's rim (the slot), 0.40 mm round the receptacle and the polyfuse; diffuser 0.30 mm from
  the stand; baffle 0.80 mm from the stand.
- **Printing** (`cad model dfm --process printing --angle-limit 45`, FDM limits from the cad skill's printing
  reference): baffle walls min 1.6 mm, p05 1.6 (FDM unsupported 1.6: pass), 48.6 mm2 of pocket and pilot-hole
  ceilings (bridges of 2.6-4 mm, under FDM's 10 mm), support 0.2 %; diffuser_print walls 1.2 mm (supported 1.2:
  pass), 75 mm2 at 44.9 degrees, its chamfer on the first layer; stand walls min 1.82 mm, p05 6.0 (pass), 245 mm2
  at exactly 45 degrees (the cable channel's roofs and the plug pocket's lip), support 1.4 %. Fixed on the way: the
  stand's arc-sided saddle (1,356 mm2 overhanging, now straight-sided), flat channel ceilings (now 45-degree
  roofs), the diffuser printed face down, and peg holes 0.87 mm from the minute cells (moved in to 42 mm). Not
  measured by the check: minimum hole (the 2.6 mm pilots are over FDM's 2.0), minimum feature, bridge length.

## Assembly

1. Print the stand and the baffle in black PLA, the diffuser in natural PETG (or `front_two_material.3mf` on a
   two-filament printer).
2. Press the diffuser's pegs into the baffle, set the baffle on the board's face (the cells over the LEDs; the
   flat at the bottom) and fix it with four M3 x 8 self-tapping screws from the back.
3. Drop the stack into the stand's slot, the flat down, then plug the USB-C cable up through the plinth.

## Demo video script

The pitch: *"72 LEDs placed by a few lines of code, a data chain routed as arcs round two rings, and 72 printed
cells that line up because the CAD reads the same board."*

| # | The prompt (typed to the agent) | What the viewer shows | Time | Why it lands |
| --- | --- | --- | --- | --- |
| 1 | "Design a round 120 mm LED ring clock: 60 minute LEDs, 12 hour LEDs, an ESP32-C3, USB-C power. Start with the schematic." | The schematic: root sheet with four sheet symbols, then the Minute ring sheet (60 LEDs chained) | 25 s | A hierarchical schematic, ERC clean, from one sentence |
| 2 | "Place the LEDs on the board from a radius and a count, each with its capacitor beside it." | The board in 2D, `placement` view: 72 LEDs and 72 caps snapping into two perfect rings, ratsnest lines | 25 s | Parametric placement: change `R_MINUTE` and the ring moves |
| 3 | "Route the LED data chain round the rings as arcs." | Copper view, zoom on the ring: the smooth arcs, DOUT to DIN, the hop between the rings at 12 | 30 s | Arcs, not jagged segments, all from code |
| 4 | "Show me the back." | Back: the ESP32 at the top edge with its antenna keep-out, USB-C on the flat, the regulator, level shifter | 20 s | Two-sided, 4 layers, a real power design (3 A worst case in the planes) |
| 5 | "Show it in 3D." | The 2D \| 3D switch: the board with every part's 3D model, orbiting round the LED rings | 30 s | THE shot: 144 tiny parts in two rings, in 3D, in the browser |
| 6 | "Now design a baffle with a cell for every LED, read from the board, and a diffuser and a stand." | The baffle: 60 wedge cells and 12 light pipes; the stand with its slot | 25 s | The cells come from the board file, not a copy of its numbers |
| 7 | "Prove it fits." | Terminal: interference 0 mm3 between the board's 172 parts and the baffle, diffuser and stand | 15 s | A measured fit, not a picture |
| 8 | "Play the explode." | The assembly: the diffuser flies forward, then the baffle, then the board rises out of the stand | 25 s | The 72 cells over the 72 LEDs, visible as the parts separate |
| 9 | "Export it for JLCPCB and my printer." | fab/ (Gerbers, BOM, placement) and 3MF/, including a two-material front | 15 s | From a sentence to fab files and prints |

Shots 5 and 8 are the centre of the video: give them the most time, orbit slowly in 5, and play 8 twice. Run
`cad run src/part_models.py` before shot 5, or the 72 LEDs and the sensor stand as blocks; the fit check takes
several minutes, so run it before the take and show its output.

## Sources

- WS2812B-2020 (Worldsemi, datasheet V1.3 as KiCad cites it): 2.0 x 2.0 mm, 12 mA a channel.
- WS2812B-Mini pinout (Worldsemi datasheets, e.g. https://learn.watterott.com/kb/ws281x/WS2812B-Mini-v3.pdf).
- Littelfuse 1210L300SLWR: 3 A hold, 6 A trip, 6 V (https://www.lcsc.com/product-detail/C3762168.html).
- ESP32-C3-WROOM-02 datasheet (Espressif, the footprint's link): antenna keep-out, strapping pins IO2/IO8/IO9.
- JLCPCB capabilities as tabulated in the pcb skill (manufacturing.md, read 2026-11-04).
