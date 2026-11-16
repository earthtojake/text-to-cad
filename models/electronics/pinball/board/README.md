# SHORT CIRCUIT: the playfield board

**Build the board first.** Its KiCad files (the board, the seven schematic sheets, the project file and its custom
rules, the project libraries and their tables) are generated from the design model by `scripts/`, not committed:
`cad run build.py`, from this folder, makes them in about eight minutes, most of it the routes' plan. It needs the
`cad` command (KiCad 10.99's kicad-cli and API come with it) and KiCad's stock libraries (macOS's KiCad.app, or
`KICAD_STOCK`). Opening the board or the schematic in the CAD Viewer or in KiCad, `check_board.py` and
`check_fit.py` all read what it writes, so run it before any of them.

The playfield of the SHORT CIRCUIT pinball machine is this circuit board: its gold art is the machine's switches (the
steel ball shorts a comb of two nets), its parts live on the underside, and its outline, holes and art come from the
design model's numbers (`../src/layout.py`, `../src/playfield.py`) through `scripts/geometry.py`.

| | |
| --- | --- |
| Board | 112 x 236 x 1.6 mm, corners r 4, 4 layers (F.Cu art, In1 ground, In2 and B.Cu wiring), ENIG, black mask, the CAD model's outline |
| Parts | 250 footprints: 189 to assemble (38 LEDs, RP2040, flash, CH224K, TPS563201, AP2112K, 74AHCT1G125, MAX98357A, LIS3DH, USBLC6-2SC6, AO3400A x 2, SS34 x 2, 18 TVS, the connectors and passives), 18 ball switches, 33 holes, 6 fiducials, 4 SWD test pads |
| Nets | 125 |
| Routing | every net: 2055 track segments, 6.80 m of copper, 514 vias (369 the wiring's, 145 the art's stitching) |
| ERC | clean: 0 errors, 0 warnings (`cad kicad_sch erc`) |
| DRC | clean: 0 errors, 14 warnings (`cad kicad_pcb drc` on the built board, the project's rules; the warnings are listed below) |
| Fit | `check_fit.py` passes, 0 failures: outline, flipper bores, every fixing hole under its part, every insert's LED under its window, the combs against `playfield.py`, every top part hidden under furniture, the underside clear of the flipper mechanisms |
| Own checks | `check_board.py` clean: 630 pins, 0 differ from the schematic; 0 segments off 45 degrees; each rail's width for its peak current (IPC-2221, 10 C rise); each supply pin's capacitor distance; In1 under the whole USB pair (D+ 42.7 mm, D- 44.8 mm) |
| Rules | JLCPCB standard 4-layer from the pcb skill's table (read 2026-11-04): 0.15 mm clearance (fab 0.09), 0.2 mm signal, 0.3/0.6 mm vias, 0.3 mm copper to edge, 0.25 mm hole clearance; a custom rule each for the combs' chevrons (0.1 mm, `pinball.kicad_dru`), the stock SK6812MINI-E's own cut-out (0.2 mm to its edge) and the RP2040's fan-out (0.15 mm tracks under the package) |

## The design, sheet by sheet

**Power** (`power.kicad_sch`). USB-C (HRO TYPE-C-31-M-12, J1) -> 2 A polyfuse (F1) -> CH224K (U3) asks the charger for
9 V (6.8k on CFG1, R3) -> TPS563201 buck (U5) to 5 V (56k/10k: 0.768 V x 6.6 = 5.07 V) -> AP2112K-3.3 (U6). The USB pair
runs through a USBLC6-2SC6 (U4), the ESD clamp at the connector. A 100k/22k divider (R7/R8) lets the firmware read the
9 V rail on GPIO29 (ADC3).

**MCU** (`mcu.kicad_sch`). RP2040 (U1), W25Q128JVS flash (U2), 12 MHz crystal (Y1, 15 pF loads, 1k on XOUT), 27 ohm
series resistors on D+ and D- (R10/R11), BOOTSEL (SW1, through 1k on QSPI_SS) and RESET (SW2), SWD on test pads
(TP1..TP4), I2C pull-ups (R14/R15). Every GPIO has a job; the map (`geometry.gpio_map`) gives each signal the pin that
travels least to where it goes, after the silicon's own constraints (I2C1 on GP18/19, the PIO I2S pair on GP20/21, ADC on
GP29).

**Inputs** (`inputs.kicad_sch`). The 18 ball switches (S1..S18): each comb is two nets, `SENSE_*` and GND, 0.4 mm
fingers on a 0.8 mm pitch; the 8 mm steel ball bridges them. The combs are exposed metal, so each has a TVS
(PESD5V0S1BA, D3..D20) at its land and a 1k (R50..R67) beside it; the line on to the RP2040 (`IN_*`) is pulled up inside
the chip. The flipper buttons (SW3/SW4, in the rails) and START (SW5, in the lockdown bar) go straight to GPIO; the
tilt is an LIS3DH (U9) on I2C.

**Lighting** (`lighting.kicad_sch`). 38 addressable LEDs in one chain: reverse-mount SK6812MINI-E under the inserts
(each in a cut-out, shining up through the board), WS2812B-2020 under the bumpers, slings and targets and as underglow.
The RP2040's 3.3 V data goes through a 74AHCT1G125 (U7: VIH 2 V, so 3.3 V is a clean high; it drives a full 5 V edge,
which the chain needs: its VIH is 0.7 VDD = 3.5 V) with a 33 ohm series resistor (R20) at its output; C50 decouples it,
C51 (220 uF) holds the LED rail, and every LED has its own 100 nF (C101..C138).

**Flippers** (`flippers.kicad_sch`). Each coil (Takaha CA07300160, 16 ohm, 0.56 A at 9 V) is switched low-side by an
AO3400A (Q1/Q2) with a 100 ohm gate resistor (R30/R32) and a 10k pull-down (R31/R33) that holds it off while the RP2040
boots; an SS34 (D1/D2) across each coil catches the flyback. C60 (220 uF) and C61/C62 (10 uF) at the drivers carry the
pulse.

**Audio and backbox** (`audio.kicad_sch`). MAX98357A (U8, I2S, mono (L+R)/2 by its SD_MODE resistor R40) to speaker
pads (J5) and to the backbox link (J4, JST SH: +5V, I2C, speaker, GND).

## The layout

- **F.Cu is the art**: the gold combs on their nets, the pinstripes, the radiance and the letters, copper with the mask
  opened over it so the ball rolls over gold on black. The stitching vias the art draws are real: GND vias through to
  In1. In1 is a whole ground plane; In2 and B.Cu carry the wiring, each poured with ground round it.
- **The RP2040's supply pins** (U1) each run inward under the package to a via in the ring between the pads and the
  exposed pad; each pin's capacitor stands on the top copper over its via, its supply pad 0.4 to 0.9 mm from the pin
  (C20..C31: the loop is the board's thickness), under the backbox where there is no art, its ground in a patch of
  top-copper ground. C26 and C28 (a second 100 nF and VREG_VIN's 1 uF) stand at the package's corners, 9 to 11 mm out. Under U1 on
  In2 an island of 3V3 joins the supply vias; the 1V1 vias (VREG_VOUT to the two DVDD pins) are joined by hand on In2.
  The signal pins fan out to a 0.8 mm pitch on B.Cu; on the side facing the field each long line may drop to In2 at the
  end of its lane.
- **The USB pair** is routed by hand (`routes.usb_pair`): the connector's two rows joined (D- over the top of the pad row,
  D+ under it), straight through U4's flow-through pins, then side by side (0.2 mm tracks, 0.2 mm apart, over the In1
  plane) to R10/R11 and U1.
- **Currents.** VBUS and +9V run on 1.0 mm tracks (2.39 A at a 10 C rise by IPC-2221, against a 2.02 A peak), the coils'
  drains and the buck's switch node on 0.8 mm, the 5 V rail on 0.6 mm (1.65 A against 1.45 A); each necks to 0.3 mm only
  within 1.6 mm of a pad, and the LED branches run at 0.3 mm.
- **Ground**: every ground pad on the underside has its own via to In1 beside it, never in the pad (the exposed pads'
  thermal vias excepted; the MAX98357A's ground pins join its exposed pad under the body).
- **Routed by a script.** The pcb skill says route by hand; with 120 nets over 112 x 236 mm, `scripts/routes.py` plans
  the wiring as an octolinear path search on a 0.1 mm grid (B.Cu and In2.Cu, a via costing 2.5 mm of track, nets that
  find no way ripped up with their neighbours and tried again), with the hand-placed pieces above. Every track is at a
  multiple of 45 degrees (`check_board.py`). It is a script's routing, not a person's: say so to whoever reviews it.

## Files

| Path | What |
| --- | --- |
| `build.py` | the one command that makes the KiCad project: every script below, in order |
| `scripts/geometry.py` | every place, from the design model: holes, combs, LEDs, the art clipped for the fab, the GPIO map, part places |
| `scripts/build_libraries.py` | the libraries from KiCad's stock ones, the combs' footprints from `playfield.py` |
| `scripts/schlib.py`, `scripts/schematic.py` | the schematic, as text |
| `scripts/board.py` | the board: setup (with the project's netclasses and custom rules), place, art, route, zones, silk, finish, each stage a `kicad_pcb.edit` |
| `scripts/routes.py` | every track and via, planned from the placed board (`tmp/routes.json`) |
| `scripts/part_models.py` | the 3D models KiCad's library lacks (WS2812B-2020, HRO USB-C) |
| `check_fit.py`, `check_board.py` | the board against the CAD model; the board's own properties and against its schematic |

Nothing generated is committed: the KiCad project `build.py` writes (`pinball.kicad_pro`, `.kicad_pcb`, `.kicad_dru`,
`pinball.kicad_sch` and its `power`, `mcu`, `inputs`, `lighting`, `flippers` and `audio` sheets, all in KiCad 10.99's
format, and the libraries `pinball.kicad_sym`, `power.kicad_sym`, `pinball.pretty/`, `sym-lib-table` and
`fp-lib-table`), the routes' plan (`tmp/routes.json`), the part models (`pinball.3dshapes/`) and the fabrication
files are written by the commands below, and `.gitignore` keeps them out of Git. The board is saved with its zones'
fills (about 6.5 MB), which DRC and `check_board.py` read.

## Rebuild

From this folder, with the `cad` command:

```bash
# the board and its schematic, from the design model (the board made afresh each time)
cad run build.py                               # about eight minutes: the steps below, in order
#   scripts/build_libraries.py                 the project libraries, the combs' footprints from playfield.py
#   scripts/schematic.py                       the seven sheets, as text
#   scripts/board.py setup place art           the board, its project and rules, its parts, its art
#   scripts/routes.py                          tmp/routes.json: the plan (most of the build)
#   scripts/board.py route zones silk finish   the tracks and vias, the pours (filled), the legends, the stackup

cad run scripts/part_models.py                 # pinball.3dshapes/: before opening the board in 3D

# check the board
cad kicad_sch erc pinball.kicad_sch
cad kicad_pcb drc pinball.kicad_pcb
cad run check_board.py                         # pin by pin against the schematic, angles, widths, decoupling, USB
cd .. && cad run board/check_fit.py && cd board   # against the CAD model
```

## See it

```bash
cad viewer --json pinball.kicad_pcb pinball.kicad_sch     # prints each file's url
cad kicad_pcb snapshot pinball.kicad_pcb tmp/copper.png --display copper
cad kicad_sch snapshot pinball.kicad_sch tmp/mcu.png --sheet /MCU/
```

## What is real and what is simplified

**Real:** the schematic (every part, net and pin, ERC clean), the outline, holes and art from the design model's
numbers, every part placed, every net routed, the planes, the 3D models, the fixing scheme (each fixing hole under its
part, checked by `check_fit.py`).

**Simplified, unchecked or waived:**

- **Part numbers.** LCSC numbers checked against JLCPCB's parts library: CH224K C970725, RP2040 C2040, W25Q128JVSIQ C97521,
  AP2112K-3.3 C51118, SK6812MINI-E C5149201. The rest in `build_libraries.py` are from memory of JLCPCB's library and
  some are blank (the PESD5V0S1BA, the polyfuse, the 220 uF, the switches): check each before ordering. CH224K's
  resistor table, the buck's L and C, and the parts' pin maps follow the datasheets as remembered; no datasheet was
  opened for this board.
- **Impedance.** The USB pair is two 0.2 mm tracks 0.2 mm apart over 0.2 mm of prepreg to In1; no field solver was run,
  so its impedance is not stated. Full speed (12 Mbit/s) does not need it controlled.
- **The combs are drawn, not pads.** The viewer draws a custom pad as its hull, so each comb's copper is board polygons
  on the land's net; KiCad sees real copper on real nets.
- **Mechanics the CAD doesn't model yet.** The CAD's parts are solid where the board needs pockets (`check_fit.py`
  lists them: the furniture LEDs and caps, the buttons under the rails and lockdown bar, the decoupling capacitors under
  the backbox's base). `parts.underside_parts` still draws its stand-ins at the old places: it should read the board.
- **DRC's warnings:** 13 `connection_width` on the +5V rail at LED decoupling capacitors (C101, C112, C115, C117, C135, C138 and neighbours): KiCad measures a 0.028 mm narrow spot in the merged +5V copper where the pad, its 0.4 mm escape and a 0.3 mm track meet; same-net copper, no clearance at stake, not resolved; 1 `silk_edge_clearance`: J1's own silkscreen outline runs past the board edge where the connector overhangs it (the stock footprint).

## Next

The backglass board, the small FR-4 parts as a panel, firmware (the pin map is `geometry.gpio_map`), Gerbers, BOM and
placement once the blank and remembered LCSC numbers are checked, the printed parts cut for the pockets `check_fit.py`
lists.
