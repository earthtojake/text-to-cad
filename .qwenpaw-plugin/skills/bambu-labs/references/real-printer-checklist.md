# Real Printer Checklist

Use this before any `--execute` run against a physical Bambu Lab printer.

## Credentials And Network

- Confirm the printer IP/hostname is on the trusted local network.
- Confirm LAN Only/Developer Mode is enabled when the printer exposes it,
  especially on A1/A1 Mini.
- Store the access code in workspace-root `bambu-printers.json` with `config set`; do not
  print it in final messages.
- Fetch/cache serial with `serial` or `config set --fetch-serial`.
- Run `status --push-all` and verify the intended printer responds.
- If LAN settings changed after failed starts, clear stale errors and
  power-cycle before retrying.

## Job

- Confirm `$gcode` generated and validated the plain `.gcode`.
- Confirm scale, orientation, supports, material profile, nozzle, and bed type.
- For A1 Mini LAN start, prefer `--handoff template-project` with a known-good
  same-printer `.gcode.3mf` template.
- Use `--handoff plain` only for diagnostics or firmware where `gcode_file` is
  already validated.
- Use `--handoff bambox-project` only when the exact printer/nozzle profile is
  enabled by the script.
- For project handoffs, upload to FTPS root and use `ftp:///<name>.gcode.3mf`.

## Physical Printer

If the current user request explicitly asks to print or start the job, treat that
request as live-start authorization for this checklist. State these physical
checks before the live command and proceed if automated validation and printer
status are healthy. Ask for another confirmation only when the request intent is
ambiguous or a validation/status check raises concern.

- Build plate is installed, clear, clean, and appropriate for the material.
- No failed-print remnants, loose tools, tape scraps, or debris are in the
  printer.
- Filament is loaded and appropriate for the sliced file.
- Operator is nearby for heat-up, homing, and first-layer observation.
- Camera or direct observation is available.

## First Live Sequence

1. Run the exact `send` command without `--execute` and inspect the plan.
2. Run `send --action upload --execute` first.
3. Check status/UI/storage if possible.
4. Re-run the dry `send --action upload-start` plan.
5. Run `send --action upload-start --execute --confirm-start-print` when the
   user explicitly asked to print/start, or after confirmation when intent is
   unclear.
6. Poll status and watch the printer until the first layer is clearly normal.

If status reports `print_error` or HMS after a failed attempt, stop. Resolve the
cause, optionally run `clear-error --execute`, then poll status before retrying.
