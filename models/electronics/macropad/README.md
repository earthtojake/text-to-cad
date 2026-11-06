# Nine: a 3x3 RP2040 macropad, board and case designed together

Nine is a nine-key mechanical macropad with a knob: an RP2040 with 16 MB of QSPI flash, USB-C, nine
hot-swap MX switches each with its own RGB LED shining through the switch, and an EC11 rotary
encoder with a push switch. Its 3D-printed case (a tray and an integrated switch plate) is generated
from the board file: the switch cut-outs, the screw bosses, the encoder window, the USB-C opening
and the BOOT/RESET pinholes are all read from `macropad.kicad_pcb`, so moving a part on the board
and running the case again moves the case's feature with it.

Why it is interesting to watch: a familiar, desirable object goes from a schematic to a routed,
DRC-clean two-layer board to a printable case and an exploding assembly, every step a prompt.

## The parts

| Ref | Part | Why |
| --- | --- | --- |
| U1 | RP2040 (QFN-56) | dual Cortex-M0+, native USB 1.1 full speed, 30 GPIO |
| U2 | W25Q128JVSIQ, 16 MB QSPI flash (SOIC-8) | the RP2040 boots from it |
| Y1 | 12 MHz crystal, ABM8-272-T3 (3225), 15 pF loads, 1 k on XOUT | RP2040's reference design values |
| U3 | AP2112K-3.3 LDO, 600 mA | 3.3 V from USB 5 V |
| J1 | GCT USB4105-GF-A, USB-C 2.0 receptacle | with 5.1 k Rd on CC1/CC2 (R1, R2): a USB-C sink |
| U4 | Nexperia PRTR5V0U2X | ESD clamps on D+/D- (shunt type, so the pair runs straight past it) |
| F1 | 500 mA polyfuse | VBUS to +5V |
| SW1-SW9 | Kailh CPG151101S11 MX hot-swap sockets | 19.05 mm pitch, plate-mount MX switches |
| D1-D9 | SK6812MINI-E reverse-mount RGB | under each switch's LED window, chained |
| U5 | 74AHCT1G125 | 3.3 V -> 5 V data for the LEDs (VIH 0.7 VDD = 3.5 V) |
| SW10 | Alps EC11E with switch, 20 mm shaft | the knob |
| SW11, SW12 | Omron B3U-1000P | BOOTSEL and RESET, pressed through the tray |
| TP1-TP4 | test pads | SWCLK, SWDIO, GND, 3V3 |
| H1-H6 | M2 holes | four between the keys, two in the back corners |

**Direct wiring, no matrix.** Nine keys, three encoder lines and the LED data use 13 of the RP2040's
30 GPIOs, so each key has its own pin (internal pull-up, switch to ground): no diodes (nine fewer
parts), every combination of keys reads without ghosting, and the firmware is a plain GPIO read. A
3x3 matrix would save 3 pins the board does not need.

**Every SMD part is on the bottom.** The hot-swap sockets and the reverse-mount LEDs have to be there
anyway, so the whole board assembles in one SMT pass; the top holds only the switches (in their
sockets) and the encoder. Two copper layers: the bottom carries the parts, the signals and power, the
top is a ground pour crossed only by the key lines in channels between the key columns (under the
switches' plastic) and a few short hops.

## The board

| | |
| --- | --- |
| Size | 59.0 x 83.5 mm, 1.6 mm FR-4, rounded corners r 3 mm |
| Layers | 2 (1 oz); both are ground pours |
| Parts | 73 footprints: 63 to assemble (all SMD on the bottom; the encoder is through-hole), 6 M2 holes, 4 test pads |
| Nets | 67 |
| Routing | 371 tracks, 1384 mm of copper, 81 vias; 0 unconnected |
| ERC | clean, 0 warnings (`cad kicad_sch erc macropad.kicad_sch`) |
| DRC | 0 errors; 40 warnings, all `lib_footprint_mismatch`: KiPy rounds a turned or flipped footprint's local coordinates by a nanometre (`7.499999`), so KiCad no longer finds 40 of them equal to their library's |
| Rules | JLCPCB standard 2-layer, read 2026-11-04 from the pcb skill's table of jlcpcb.com/capabilities: 0.15 mm space (fab 0.10), 0.2 mm signal tracks, 0.3/0.6 mm vias, 0.3 mm copper to edge (0.2 at the LEDs' own cut-outs, the fab's limit) |

Hierarchical schematic: the root (`macropad.kicad_sch`) and three sheets, `usb_power` (USB-C, CC,
ESD, polyfuse, LDO), `mcu` (RP2040, flash, crystal, boot, reset, SWD, decoupling) and `keys`
(switches, encoder, level shifter, LEDs, holes). GPIO map: ENC_SW GP0, ENC_B GP1, ENC_A GP2,
KEY9/6/3 GP3/4/5, KEY8/5/2 GP9/10/11, KEY7/4/1 GP26/27/29, LED data GP28. The map was chosen from
the board: each group leaves the RP2040 on the side facing where it goes, in the order it arrives.

The RP2040's own ring (between its pads and its exposed pad) carries two rails, 1V1 from VREG_VOUT
to both DVDD pins and 3V3 to IOVDD 1, 10 and 22, which keeps the USB pair and the QSPI fan-out
uncrossed on a two-layer board.

KiCad's library has no MX hot-swap footprint and no 3D model for a keyboard switch or an EC11, so the
project carries its own: `macropad.pretty` holds the hot-swap socket's footprint (drawn from the Kailh
CPG151101S11 land pattern, mirrored for the bottom) and KiCad's EC11 footprint naming a model, and
`src/vendor_parts.py` draws both models. Check the socket's land pattern against a real socket before
ordering.

Review (guided, not a fab's CAM check): DRC clean against the rules above; every pad on its
schematic pin's net, all track segments at 45-degree steps, no track narrower than its current
(+5V/VBUS 0.5 mm for 0.6 A), each decoupler within 3 mm of its pin and ground under every point of
the USB pair (`check_macropad.py`); USB pair skew 0.6 mm (connector side) and 1.1 mm (MCU side),
immaterial at full speed's 83 ns bits. Items for a person: C13 (USB_VDD + IOVDD 49) sits 4.5 mm from
its pins (the spot beside them holds the USB pair and the QSPI fan-out); DVDD 50 has no cap of its own
(it is ringed to VREG_VOUT 45's 1 uF and DVDD 23's 100 nF); IOVDD 22's cap C9 is placed by pin 33;
the LED supply (0.54 A at full white) exceeds USB 2.0's 500 mA: firmware must cap brightness. The
stock SK6812MINI-E footprint's pads sit 0.247 mm from its own cut-out, so a custom rule allows 0.2 mm
(JLCPCB's limit) for the LEDs; its pin numbers differ from the OPSCO datasheet's, but symbol and
footprint agree and each pad sits where the mirrored top view puts its function. Not checked: Gerbers
in a Gerber viewer, impedance, the BOM's sourcing beyond the LCSC numbers given, the hot-swap land
pattern against a physical socket.

## The case

Printed in PLA or PETG on an FDM printer, all parts without supports:

- **Tray** (floor down): 2 mm floor 5.4 mm under the board, 2.4 mm walls 0.4 mm off the board's
  edge, six bosses (6 mm) with M2 x 3 mm heat-set insert holes (3.2 mm) under the board's holes, a
  13 mm USB-C slot at the receptacle, 2.5 mm pinholes under BOOT and RESET.
- **Plate** (top face down): 1.5 mm, its top 5.0 mm above the board (MX), a 14.1 mm cut-out at each
  key, the encoder body's window, 4.6 mm spacer bosses down to the board at each hole (M2 clearance
  2.4 mm), NINE stencilled beside the knob.
- **Keycaps** (top down, x9): one shape, legend-free, 18 mm base, 12.6 mm top, 7.6 mm tall, MX cross
  4.2 x 1.35 mm; `keycap_body(dish=...)` scoops the top (flat by default, so it prints face down).
- **Knob** (top down): 19 mm, 24 grip flutes, a D-bore for the EC11's 6 mm shaft, a pointer groove.

Hardware: six M2 x 10 mm button-head screws (through the plate, its spacer and the board into the
tray's inserts), six M2 x 3 mm heat-set inserts, four stick-on rubber feet, nine MX-style switches.

Everything the case is built around comes from `macropad.kicad_pcb` through
`src/lib/board_geometry.py`: the outline and its corner radius, the six holes, the nine switch
positions, the encoder's shaft and body (and its rotation, which turns the knob's D-bore), the USB
receptacle's x and mating face, the two buttons.

## Files

| Path | What |
| --- | --- |
| `macropad.kicad_pro`, `.kicad_pcb`, `.kicad_dru`, `macropad.kicad_sch` (+ `usb_power`, `mcu`, `keys` `.kicad_sch`) | the KiCad project (KiCad 10.99 format), the source |
| `macropad.pretty/`, `fp-lib-table`, `sym-lib-table` | the project's footprints and its library tables (KiCad's stock libraries through `${KICAD10_FOOTPRINT_DIR}` and `${KICAD10_SYMBOL_DIR}`) |
| `check_macropad.py` | the board's own checks |
| `scripts/` | how the board was made, re-runnable: footprints, schematic, rules, netlist import, placement, routing, silkscreen |
| `src/` | the case: `vendor_parts.py` (the socket, the EC11 and an MX switch), `case.py`, `assembly.py`, `check_fit.py`, `exports.py`, `lib/board_geometry.py` |

Nothing generated is committed: the footprints' 3D models (`macropad.3dshapes/`), the fabrication
files (`fab/`), the board's STEP and the case's files (`STEP/`, `XBF/`, `GLB/`, `3MF/`, `DXF/`) are
written by the commands below, and `.gitignore` keeps them out of Git.

## Rebuild

From this folder, with the `cad` command. KiCad's stock libraries are named through
`${KICAD10_SYMBOL_DIR}` and `${KICAD10_FOOTPRINT_DIR}`, which ERC, DRC and the generators read from the
environment: set them to KiCad's own folders first, or ERC counts every stock symbol as a missing library
and DRC every stock footprint. KiCad's 3D library needs nothing: the board's 3D view and its exports find
it.

```bash
export KICAD10_SYMBOL_DIR=/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols      # macOS
export KICAD10_FOOTPRINT_DIR=/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints

# the 3D models KiCad's library lacks: run this before opening the board in 3D or exporting its STEP or GLB
cad run src/vendor_parts.py                # macropad.3dshapes/: the hot-swap socket and the EC11

# check the board as it is
cad kicad_sch erc macropad.kicad_sch
cad kicad_pcb drc macropad.kicad_pcb
cad run check_macropad.py                  # prints nothing when the board is clean

# make the board again from its sources (each step states the board it wants; rerunning is harmless)
python3 scripts/gen_footprints.py          # macropad.pretty
python3 scripts/gen_schematic.py           # the four sheets
python3 scripts/step0_rules.py             # JLCPCB rules, netclasses, custom rules
cad run scripts/step1_import.py            # the schematic's netlist onto the board
cad run scripts/step2_place.py             # outline, every part's place, side and angle
cad run scripts/route.py                   # every track and via, then the pours
cad run scripts/step4_silk.py              # silkscreen

# fabrication files
for k in gerbers drill pos bom pdf; do cad kicad_pcb export macropad.kicad_pcb --to $k -o fab/$k; done
cad kicad_sch export macropad.kicad_sch --to pdf -o fab/schematic
cad kicad_pcb export macropad.kicad_pcb --to dxf -o DXF     # the outline and drilled holes
cad kicad_pcb export macropad.kicad_pcb --to glb -o GLB     # the board with its parts, to look at

# the case, read from the board: its STEP with every part, converted once to an xbf
cad kicad_pcb export macropad.kicad_pcb --to step -o STEP   # STEP/macropad.step
cad step export STEP/macropad.step XBF/macropad.xbf
cad run src/case.py                        # tray, plate, keycap, knob and their print orientations
cad run src/assembly.py                    # nine (with its explode) and nine_exploded
cad run src/check_fit.py                   # overlap volumes and clearances against the board's STEP
cad run src/exports.py                     # 3MF/ and STEP/ of each printed part, STEP/nine.step, GLB/nine.glb
cad threemf dfm 3MF/tray.3mf --process printing --angle-limit 45   # and plate, keycap, knob
```

`gen_footprints.py`, `gen_schematic.py` and `step0_rules.py` write the files they make byte for byte as
committed; the layout steps leave the same board, its tracks under new ids.

## The case's checks

**Fit** (`src/check_fit.py`, against KiCad's STEP of the board with every part): 297 pairs of solids
whose boxes meet, overlap volume 0 for all (tray, plate, switches, keycaps and knob each against
every board solid; switches, keycaps and knob against the plate; tray against plate). The board
rests on the tray's bosses (distance 0) with 0.4 mm to the tray's walls; the tray's floor is
2.0 mm under the lowest bottom part (the USB-C receptacle, z -3.4); the plate's underside is
3.59 mm above the bare board (MX: 3.5 plus the copper); each keycap is 1.2 mm clear of its switch;
the knob's D-bore sits on the EC11's shaft with the bore turned to the encoder's rotation.

**Printing** (`cad threemf dfm 3MF/<part>.3mf --process printing --angle-limit 45`; FDM limits
from the cad skill's printing reference: 1.2 mm supported wall, 45 degrees, 10 mm bridge):

| Part | Overhangs under 45 deg | Walls min / p05 | Support | Result |
| --- | --- | --- | --- | --- |
| tray (floor down) | 0 mm2 | 1.38 / 2.0 mm | 0 | pass |
| plate (top down) | 0 mm2 | 0.79 / 1.18 mm | 0 | review: the thin sample is the acute inside corner of the stencil N; the plate is 1.5 mm |
| keycap (top down) | 0 mm2 | 0.54 / 0.95 mm | 0 | review: the MX cross (4.2 x 1.35 mm) inside the 5.5 mm stem leaves 0.54 mm at the cross's ends; the stem cannot grow (it travels into the switch's 5.6 mm opening). Print with a 0.25 mm nozzle, or in resin |
| knob (top down) | 3 mm2 (the 1 mm pointer groove, on the bed face) | 1.2 / 5.15 mm | 3 mm3 | pass |

What the check found and what changed: the tray's foot recesses (220 mm2 of 0.8 mm ceilings and
1.0 mm floors) are gone (stick-on feet instead) and the screw pilots stop 1.4 mm above the bed; the
plate's corner spacers at H5/H6 thinned to 0.55 mm against the tray's corner and are gone (the wall
carries the plate there); the engraved NINE (43 mm2 of ceilings face down) is now a through stencil;
the knob's flutes run full height (no ceilings), and its pointer groove, first modelled 0.1 mm under
the top face (a sealed void under a 0.1 mm skin), is open on the top. Not measured by the check:
minimum hole (the paperclip holes are 2.5 mm, the screw holes 2.4 mm, both over FDM's 2.0), bridges
(none), fit of the heat-set inserts (3.2 mm holes for M2 x 3 inserts, the insert maker's figure).

## Demo video script (about 3 minutes)

Record the CAD app (or the CAD Viewer) beside the agent's chat. Every prompt is what the person types;
the agent runs the skills. Pre-build everything once the day before so each shot replays warm.

| # | Prompt (typed to the agent) | What the viewer shows | Length | The one thing |
| --- | --- | --- | --- | --- |
| 1 | "Design a 3x3 macropad: RP2040, USB-C, hot-swap MX keys with per-key RGB, a knob. Start with the schematic." | The root sheet, then a double-click into MCU: the RP2040 with its flash, crystal and decoupling | 25 s | A real hierarchical schematic, ERC clean, from one sentence |
| 2 | "Why direct wiring and not a matrix?" (then) "Show me the keys sheet." | Keys & LEDs sheet: nine switches, the LED chain through the 74AHCT1G125 | 15 s | The agent reasons about pins (13 of 30) and parts (no diodes) |
| 3 | "Lay out the board: keys at 19.05 mm, everything SMD on the bottom, two layers, JLCPCB rules." | Board view, bottom side: sockets, LEDs, the RP2040 strip; the Nets tab, pick a net (KEY5) to light its path through the F.Cu channel | 30 s | 371 tracks routed by hand-written geometry, DRC 0 errors |
| 4 | "Show it in 3D." | The corner's 2D/3D button: the board with every part's model, sockets and LEDs underneath | 15 s | Real KiCad 3D, including the parts KiCad had no models for |
| 5 | "Now design a printable case around it: tray with heat-set inserts, a 1.5 mm switch plate, keycaps and a knob." | The assembly: tray, board, plate, switches, caps, knob | 25 s | The case is read from the board file: holes, keys, USB, encoder |
| 6 | "Play the explode." | Playbar: layers lift in order (board, plate, switches, caps, knob) and settle back | 15 s | Six layers, one motion, no joints faked |
| 7 | "Make the board 6 mm longer at the front and rebuild everything." | The board grows (outline and pours), DRC still clean; the case's tray and plate follow on rebuild | 30 s | One board edit, the case follows: the board is the source of truth |
| 8 | "Check the case for printing and give me the files." | DFM summary per part (no supports in print orientation), the 3MF list | 15 s | Manufacturing checks and fab files in the same breath |
| 9 | "Does it fit? Any interference with the board?" | Check output: 0 overlap volume over every pair, clearances listed | 10 s | A measured fit, not a picture |

Shot 7, how to do it live: set `Y1` in `scripts/board_common.py` from 131.0 to 137.0, run
`cad run scripts/step2_place.py`, `cad run scripts/route.py`, `cad kicad_pcb drc macropad.kicad_pcb`,
export the STEP and the xbf again, `cad run src/assembly.py`. The tray and plate grow from 89.1 to
95.1 mm and DRC stays clean. Set it back to 131.0 afterwards. (Moving the USB receptacle or a key is
what the case reads too, but the hand routing is laid out around their places, so a move needs
`scripts/route_strip.py` revised: the board side of that shot is not a one-line change.)

Things to know before recording: run `cad run src/vendor_parts.py` first, or the sockets and the
encoder stand as blocks in 3D; build everything once (cold builds take seconds, warm ones are
instant); the fit check takes over a minute, so run it before the take and show its output.
