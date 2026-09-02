# KiCad mechanical handoff

Load this reference when a KiCad board must be inspected in an enclosure,
chassis, robot, or other mechanical assembly.

## Trigger the handoff only for mechanical changes

Export or refresh STEP when any of these change:

- board outline, thickness, cutouts, or edge geometry;
- mounting holes, slots, or mechanical keepouts;
- footprint placement or orientation;
- connector, switch, LED, sensor, heatsink, or other external envelope;
- a footprint's 3D model, offset, rotation, or scale.

An annotation, net label, routing-only change that does not alter the physical
board, or an ERC cleanup alone does not require a new mechanical export.

## Prepare mechanically honest footprints

Prefer an exact project-local or standard KiCad 3D model when it exists and is
suitable. Use `${KIPRJMOD}` or another portable KiCad variable in footprint
model references. Confirm model offsets and orientation in KiCad rather than
correcting them in the downstream assembly.

When an exact vendor model is unavailable or produces an open/inconclusive mesh
in the downstream checker, create a documented closed collision envelope for
the mechanically relevant extents. Keep the envelope conservative and label it
as an envelope, not an exact cosmetic model. A visual model and a collision
envelope may coexist when their roles are explicit.

## Validate before export

Run ERC and DRC first when their source scopes exist:

```bash
kicad-cli sch erc --exit-code-violations --format json \
  --output /tmp/kicad-erc.json path/to/project.kicad_sch

kicad-cli pcb drc --exit-code-violations --format json \
  --output /tmp/kicad-drc.json path/to/project.kicad_pcb
```

Then export a populated STEP:

```bash
kicad-cli pcb export step --force \
  --output path/to/controller.step \
  path/to/controller.kicad_pcb
```

On some macOS KiCad builds, stderr can mention source-file attributes or an
output-open failure even though the command exits zero and creates the STEP.
Judge the operation by all three facts: exit status, output existence, and a
successful downstream import. Retain the stderr warning in the report rather
than pretending it did not occur.

Confirm that the export contains the board and every mechanically required
component. A non-empty file is not enough proof of a populated board.

## Build the larger assembly in its owning source

Import the KiCad STEP into the enclosure or robot source; do not hand-edit it.
Place the board with explicit datums or transforms and keep the enclosure,
chassis, or system model responsible for that placement.

Many interference checkers compare assembly occurrences. A populated KiCad
STEP naturally contains intentional internal contacts such as a connector
mounted on its PCB. For an external board-versus-enclosure check, preserve the
original populated export for inspection but group its board and mounted
components into one `controller_board_from_kicad` subsystem occurrence in the
combined assembly. This prevents intentional PCB-internal mounting contacts
from hiding the external clearance question. Do not fuse away geometry merely
to force a pass.

Name the external assembly occurrences for diagnosis, for example:

- `controller_board_from_kicad`
- `enclosure_blocking_usb_c`
- `enclosure_with_usb_c_cutout`

## Downstream check

When Burr is requested and installed, open the folder containing the combined
STEP assembly with `$burr`. Burr owns visualization and the external
assembly-interference result; KiCad continues to own ERC, DRC, placement, and
the board export.

For a repair loop:

1. Retain a negative assembly that intentionally blocks the connector.
2. Confirm the checker reports the board subsystem against the blocking
   enclosure.
3. Add the cutout or clearance in mechanical source.
4. Regenerate a positive assembly.
5. Confirm the checker completes with no findings across the intended pairs.
6. Capture the same camera view for fail and pass when visual evidence matters.

If the downstream result is incomplete because a component mesh is open, do not
claim clearance. Repair or replace the offending collision representation, then
rerun the check.

## Reporting boundary

Report ERC and DRC independently from the mechanical result. A complete handoff
can support: “KiCad ERC and DRC passed; the populated board exported; Burr found
the expected blocked-connector failure and passed the repaired board/enclosure
pair.” It cannot by itself support electrical function, connector durability,
tolerance-stack, thermal, motion, or fabrication claims.
