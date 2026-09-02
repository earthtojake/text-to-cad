# KiCad → Burr connector-clearance fixture

This fixture proves a narrow, real handoff:

1. KiCad owns a small controller PCB and its USB-C mechanical envelope.
2. KiCad ERC and DRC complete with zero violations.
3. KiCad exports a populated `controller.step`.
4. Mechanical source places that board in an enclosure.
5. Burr catches a front wall blocking the connector.
6. Burr passes the same assembly after a source-level connector cutout.

The schematic is intentionally electrically empty. This is a mechanical
integration fixture, not a functioning controller circuit, and its clean ERC
result must not be presented as proof of electrical function.

## Source and derived files

| Path | Role |
| --- | --- |
| `controller.kicad_pro` | KiCad project settings |
| `controller.kicad_sch` | intentionally empty, ERC-clean schematic |
| `controller.kicad_pcb` | 40 × 25 mm PCB with a USB-C envelope at the front edge |
| `Burr.pretty/USB_C_Mechanical.kicad_mod` | project-local footprint |
| `Burr.3dshapes/USB_C_Mechanical.step.py` | closed mechanical envelope source |
| `kicad_enclosure.py` | shared enclosure and populated-board import source |
| `assembly_fail.step.py` | enclosure with the connector blocked |
| `assembly_pass.step.py` | enclosure with the connector cutout |
| `*.step` | generated artifacts retained with the fixture |

The USB-C body is deliberately a documented collision envelope, not a cosmetic
vendor model. Screening detailed stock KiCad connector models exposed open mesh
faces in the downstream STEP tessellation, which correctly made Burr return
`incomplete`. The closed envelope keeps this fixture about connector clearance
without pretending that an inconclusive vendor mesh passed.

## Tested toolchain

- KiCad CLI 10.0.6
- repository Python environment (`./.venv/bin/python`)
- Burr 0.31.0

Use the installed `kicad-cli` executable. On macOS it may live inside the KiCad
app bundle rather than on `PATH`.

## Regenerate and validate

From the repository root, set `KICAD_CLI` to the discovered executable, then:

```bash
./.venv/bin/python skills/cad/scripts/gen \
  models/integrations/kicad-burr/Burr.3dshapes/USB_C_Mechanical.step.py \
  --write

"$KICAD_CLI" sch erc \
  --exit-code-violations \
  --format json \
  --output /tmp/kicad-burr-erc.json \
  models/integrations/kicad-burr/controller.kicad_sch

"$KICAD_CLI" pcb drc \
  --exit-code-violations \
  --format json \
  --output /tmp/kicad-burr-drc.json \
  models/integrations/kicad-burr/controller.kicad_pcb

"$KICAD_CLI" pcb export step \
  --force \
  --output models/integrations/kicad-burr/controller.step \
  models/integrations/kicad-burr/controller.kicad_pcb

./.venv/bin/python skills/cad/scripts/gen \
  models/integrations/kicad-burr/assembly_fail.step.py \
  models/integrations/kicad-burr/assembly_pass.step.py \
  --write
```

Read both JSON reports. The expected result is zero ERC violations, zero DRC
violations, and zero unconnected items. Also confirm that `controller.step`
imports with both PCB and USB-C solids; file existence alone is not enough.

KiCad 10.0.6 on macOS can emit a misleading source-attribute/output-open
message on stderr while still exiting zero and creating a valid STEP. Preserve
that warning in reports, but verify the exit status, artifact, and downstream
import before deciding whether the export succeeded.

The CAD generator creates ignored `__cadgen__` render caches. Burr 0.31.0 and
earlier may discover those GLBs if they remain below the served folder; current
Burr ignores `__cadgen__` as generated output.

## Inspect in Burr

```bash
burr models/integrations/kicad-burr
```

Select `assembly_fail.step`, open **Checks**, and select the finding. Expected:

```text
fail
1 interfering component pair detected
controller_board_from_kicad × enclosure_blocking_usb_c
```

Then select `assembly_pass.step`. Expected:

```text
pass
No assembly interference detected across 1 pairs
```

For PR or review evidence, capture paired front views without cropping away
Burr's result and retain the matching result JSON. Keep those review artifacts
under `/tmp` or attach them to the PR; repository policy intentionally excludes
review media and reports from `models/`.

The combined assembly intentionally groups the detailed KiCad PCB and mounted
connector into one `controller_board_from_kicad` occurrence. That preserves the
geometry while preventing the connector's intended contact with its own PCB
from obscuring the external board-versus-enclosure question.

## Trust boundary

This fixture proves that the checked KiCad files pass the CLI rule sets used,
that a populated board STEP was exported, and that Burr distinguishes this
specific blocked connector from this specific repaired cutout. It does not
prove a functional circuit, minimum clearance, tolerance stack, connector
durability, motion, thermal performance, manufacturability, or safety.
