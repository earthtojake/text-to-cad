# Layout: placing and routing a board that works

KiCad's DRC proves a board can be made; it does not prove the board works. These rules
cover what the checks cannot see. Look at every board you place (snapshot it, or show it).

## Before placing

- Fix the outline and the mounting holes first, from the enclosure when there is one (call
  the case's part model, or share its constants), so the board fits before anything is on it.
- Decide the stack: 2 layers for most robot boards; 4 (signal, ground, power, signal) for
  fast digital, RF, or dense microcontroller boards.
- Group the netlist into subcircuits (power input, regulator, MCU, each driver, each
  connector) and keep each group together on the board.

## Placement

- Connectors on the board's edges, mating side outward, with keepouts for the housings and
  cables that plug in. Mounting holes clear of copper (`board.hole` is unplated).
- Power path in a line: input connector → protection → regulator → its output caps → loads.
- Decoupling capacitors as close to their IC's power pin as the courtyards allow, on the
  same side, the small value nearest the pin.
- Crystals within a few millimetres of their MCU pins, nothing routed under them.
- Switching regulators: input cap, switch node and inductor in a tight loop; keep the switch
  node small and away from sensitive traces.
- Hot parts (regulators, motor drivers) near the edge or over a copper pour with vias to
  the other side.
- Leave space: courtyards may not overlap (a DRC error), and room for tracks between parts.
- Rotations of 0/90/180/270 unless the layout needs otherwise.
- Parts on the bottom only when the top is full or the design needs it; assembly costs more.

## Routing

- Ground: a pour on one layer (2-layer: usually `B.Cu`), the ground pins connected through
  vias next to their pads. Keep that pour unbroken under signals; a long track cutting the
  pour forces return currents around it.
- Power: wider tracks in a net class (`board.netclass("Power", track_width=0.5, ...)`):
  roughly 0.5 mm per amp on outer 1 oz copper for a modest temperature rise; calculate for
  real currents.
- Signals: default width, short and direct, 45-degree corners (a point list does this).
- Differential pairs (USB, CAN): equal lengths, side by side, no vias if possible.
- Vias: one per layer change, at least the rules' size; several for power and thermal paths.
- Route critical nets by hand first, then autoroute the rest ([routing](routing.md)).

## Reading the results

- Every DRC/ERC finding gives the items and their positions in the script's coordinates:
  go to that point in the script.
- Every build also lists review warnings: an IC power input (not a connector's, jumper's, test point's or hole's, nor an unfitted part's) with no capacitor to ground
  (decoupling missing), or whose nearest one is more than 3 mm away, pad centre to pad centre
  (decoupling far), and a net whose narrowest track is thinner than its `current=` needs
  (IPC-2221, 1 oz outer copper, 10 °C rise). They never block a build, strict validate or a
  fab export: read and fix them as a reviewer would. Give power nets a `current=`
  ([board API](board-api.md)) so the track check has something to read.
- A draft's ratsnest (the grey lines in the viewer) is what is left to route.
- After a clean build, snapshot the board (`cadgen pcb snapshot board.kicad_pcb tmp/b.png`)
  and look at it: crowding, a cap far from its pin, a connector facing inward are not errors.
