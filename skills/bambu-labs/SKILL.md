---
name: bambu-labs
description: Dry-run, upload, and cautiously initiate local Bambu Lab print jobs from validated plain `.gcode`, using Bambu LAN FTPS/MQTT handoffs.
---

# Bambu Labs

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill for local-network Bambu Lab print handoffs after a plain `.gcode`
file already exists and has been validated. This skill does not slice models.

## Safety Rules

- Default to dry-run plans. Real printer traffic requires `--execute`.
- Never start a print without `--execute --confirm-start-print`.
- Pause and cancel controls are live printer requests; default to dry-run plans.
  Canceling a print requires `--execute --confirm-cancel-print`.
- Treat an explicit user request to print or start a specific job as live-start
  authorization; do not pause for a second confirmation solely for physical
  checks. Still validate the G-code, inspect the dry-run payload, read printer
  status, prefer upload-only before upload-start, state the physical checks, and
  stop if validation/status/intent is unsafe or ambiguous.
- Do not ask for the printer serial by default; fetch it from the printer TLS certificate with `serial` or let `send` cache it.
- Prefer workspace-root `bambu-printers.json` over repeating access codes in commands. The file is local config and should be ignored by Git.
- Before a live start, state the physical checks: clear build plate, correct plate/filament/nozzle, safe surroundings, and operator nearby.
- Publishing MQTT is only a start request. Confirm acceptance with printer status/UI and physical observation.

## CAD Viewer Handoff

After completing Bambu work that creates or modifies a local supported print artifact such as `.gcode` or `.3mf`, you must ALWAYS hand the explicit file path to `$cad-viewer` when that skill is installed. `$cad-viewer` must start CAD Viewer if it is not already running and return link(s) to the relevant created or updated file(s); if `$cad-viewer` is unavailable or startup fails, report that instead of silently omitting the handoff.

## Workflow

1. Generate and validate plain G-code with `$gcode`.
   If no slicer is installed, install OrcaSlicer and retry; do not treat the missing slicer as a blocker. On macOS, prefer `brew install --cask orcaslicer`.
2. Configure the printer. The user can either give the IP/access code in the thread and let the agent write JSON, or edit `bambu-printers.json` directly.
   For a new printer setup or onboarding request, read
   `references/new-printer-onboarding.md` first. Walk the user through the
   model-specific touchscreen steps to find the IP and LAN access code, and make
   **Enable LAN Only** plus **Enable Developer Mode** explicit before running
   local start workflows.

```bash
python scripts/bambu_lan_print.py config set \
  --printer a1-mini \
  --host 192.168.1.34 \
  --access-code 12345678 \
  --model a1-mini \
  --fetch-serial
```

Manual JSON shape:

```json
{
  "printers": {
    "a1-mini": {
      "host": "192.168.1.34",
      "access_code": "12345678",
      "model": "a1-mini"
    }
  }
}
```

On A1/A1 Mini, find the IP and LAN access code on the printer touchscreen under
network/LAN settings. Enable LAN Only and Developer Mode when offered, then
power-cycle before retrying local start commands.

3. Read status before live work:

```bash
python scripts/bambu_lan_print.py status \
  --printer a1-mini \
  --push-all \
  --wait-seconds 10
```

4. Dry-run the exact handoff, inspect the JSON payload, then run upload-only.
Only after upload succeeds should you run upload-start. If the user explicitly
asked to print or start the job, proceed to `upload-start --execute
--confirm-start-print` after the validation, status, and upload checks pass. If
the user only asked to prepare, slice, upload, or review, stop before the start
request.

## Handoff Modes

`--handoff template-project` is the validated A1 Mini path from this repo's LAN
debugging. It starts from validated plain `.gcode`, copies a known-good
same-printer `.gcode.3mf` template, replaces `Metadata/plate_N.gcode`, writes
the plate MD5, uploads the project to the FTPS root, and publishes
`print.project_file` with `url: ftp:///<name>.gcode.3mf`.

```bash
python scripts/bambu_lan_print.py send \
  --printer a1-mini \
  --gcode /tmp/job.gcode \
  --handoff template-project \
  --template-project /path/to/same-printer-template.gcode.3mf \
  --action upload-start
```

Execute after review when the user explicitly asked to print or start, or after
physical confirmation when intent is unclear:

```bash
python scripts/bambu_lan_print.py send \
  --printer a1-mini \
  --gcode /tmp/job.gcode \
  --handoff template-project \
  --template-project /path/to/same-printer-template.gcode.3mf \
  --action upload-start \
  --execute \
  --confirm-start-print
```

`--handoff plain` uploads `cache/<name>.gcode` and publishes
`print.gcode_file`. Keep it for diagnostics or printers/firmware where this is
known to work. On the tested A1 Mini, direct plain G-code was uploaded
successfully but `gcode_file` failed or was ignored, so do not use it as the
A1 Mini live-start path.

`--handoff bambox-project` packages plain `.gcode` with `bambox`, uploads the
`.gcode.3mf` project to FTPS root, and publishes `print.project_file`.
Currently enabled only for `p1s-0.4` with `PLA`, `ASA`, or `PETG-CF`.
Known but disabled until validated profiles exist: `a1-mini-0.4`, `a1-0.4`,
`x1c-0.4`, and `p1p-0.4`.

## Common Debugging Commands

Fetch/cache serial:

```bash
python scripts/bambu_lan_print.py serial \
  --printer a1-mini \
  --json
```

Clear a stale printer error after fixing the underlying cause:

```bash
python scripts/bambu_lan_print.py clear-error \
  --printer a1-mini \
  --execute
```

Use `--mqtt-qos 1 --wait-after-publish 10` on `send` when debugging whether the
printer acknowledged the MQTT publish and what status it reported immediately
afterward.

## Print Controls

For a running print, use dedicated print-control commands rather than ad hoc
MQTT snippets. These commands publish only a control request; they do not upload
files or start a new job. Read status after execution to confirm the printer
state changed.

Dry-run pause payload:

```bash
python scripts/bambu_lan_print.py pause \
  --printer a1-mini
```

Execute pause and collect printer reports:

```bash
python scripts/bambu_lan_print.py pause \
  --printer a1-mini \
  --execute \
  --mqtt-qos 1 \
  --wait-after-publish 10
```

Dry-run cancel payload. The Bambu LAN command sent to the printer is `stop`:

```bash
python scripts/bambu_lan_print.py cancel \
  --printer a1-mini
```

Execute cancel only when the user explicitly asks to cancel/stop the print or
after confirmation when intent is ambiguous:

```bash
python scripts/bambu_lan_print.py cancel \
  --printer a1-mini \
  --execute \
  --confirm-cancel-print \
  --mqtt-qos 1 \
  --wait-after-publish 10
```

## Failure Modes

- `gcode_file` returns `result: fail` or leaves the printer `IDLE`: plain G-code upload worked, but the firmware rejected or ignored direct local start. For A1 Mini, switch to `template-project`.
- Project uploaded under `cache/` starts then fails with `print_error: 83935248` or `0500-C010`: clear the error, upload project handoffs to FTPS root, and use `ftp:///<name>.gcode.3mf`.
- `file:///sdcard/cache/...` or local HTTP URLs appear accepted but nothing starts: stop using those URL forms for this workflow.
- Bambu Studio or OrcaSlicer project export crashes on macOS: do not keep retrying GUI-backed project export. Use OrcaSlicer for plain `.gcode`, then this skill for handoff.
- Stale `gcode_state: FAILED` or HMS after enabling Developer Mode: clear the printer error and power-cycle before retrying.
- FTPS login works but upload fails with `553` or missing `cache/`: check printer storage/SD card status before MQTT start.
- MQTT status works but start does not: confirm serial, access code, Developer Mode/LAN Only status, and the exact handoff payload before retrying.

Read `references/new-printer-onboarding.md` for new printer setup,
`references/local-lan-protocol.md` for protocol details, and
`references/real-printer-checklist.md` before first live use on a new printer.
