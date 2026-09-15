# Bambu Lab Local LAN Protocol Notes

Use this reference only when planning or debugging against a real local printer.
Bambu does not provide this skill with a stable public local-print API
contract, so treat these as observed FTPS/MQTT behaviors.

## Required Inputs

- Validated plain `.gcode`.
- Printer LAN IP/hostname.
- Printer access code.
- Printer serial for MQTT topic `device/{serial}/request`; fetch it from the
  printer TLS certificate with `serial` or let `send` fetch/cache it.
- Handoff mode: `template-project`, `plain`, or `bambox-project`.

Workspace-root `bambu-printers.json` stores printer IDs, hostnames, access codes, models,
and cached serials. It is local config and should be ignored by Git.

## Transport

- FTPS upload: implicit TLS on port `990`.
- MQTT control/status: TLS on port `8883`.
- Username: `bblp`.
- Password: printer access code.
- TLS verification is off by default because local printers commonly use
  device/self-signed certificates.
- The helper rejects public IPs/hostnames unless `--allow-nonprivate-host` is
  set.
- FTPS data connections may require TLS session reuse. The helper reuses the
  control TLS session for uploads and listings.

## MQTT Topics

- Request topic: `device/{serial}/request`.
- Report topic: `device/{serial}/report`.
- `status --push-all` subscribes to reports, then publishes `pushing.pushall`
  to request a full state report.
- Publishing a start payload is a request, not proof of accepted motion.

## Handoff Payloads

### Template Project

Validated on an A1 Mini during local LAN debugging:

1. Start from a validated plain `.gcode`.
2. Copy a known-good same-printer `.gcode.3mf` template.
3. Replace `Metadata/plate_N.gcode` and update `Metadata/plate_N.gcode.md5`.
4. Upload the resulting `.gcode.3mf` to FTPS root, not `cache/`.
5. Publish `print.project_file` with root FTP URL.

Representative payload:

```json
{
  "print": {
    "command": "project_file",
    "param": "Metadata/plate_1.gcode",
    "project_id": "0",
    "profile_id": "0",
    "task_id": "0",
    "subtask_id": "0",
    "subtask_name": "job",
    "url": "ftp:///job.gcode.3mf",
    "md5": "PROJECT_MD5_UPPERCASE",
    "timelapse": false,
    "bed_type": "auto",
    "bed_levelling": true,
    "flow_cali": true,
    "vibration_cali": false,
    "layer_inspect": true,
    "use_ams": false,
    "ams_mapping": ""
  }
}
```

### Plain G-code

The plain path uploads `cache/<job>.gcode` and publishes:

```json
{
  "print": {
    "command": "gcode_file",
    "param": "cache/job.gcode"
  }
}
```

On the tested A1 Mini, byte-for-byte verified uploads still produced
`gcode_file` failure/idle behavior. Use this path only for diagnostics or
printer firmware where it has been validated.

### Bambox Project

The optional `bambox-project` path packages plain G-code into `.gcode.3mf` for
enabled profiles, validates the archive, uploads it to FTPS root, and publishes
the same `project_file` shape as template projects. Current enabled profile is
`p1s-0.4`; A1/A1 Mini are disabled until a validated bambox profile exists.

## Observed Failure Modes

- **Direct G-code rejected:** MQTT report after `gcode_file` may include
  `{"command":"gcode_file","result":"fail","reason":"error string"}`. Stop and
  use a project handoff.
- **Direct G-code ignored:** uploaded file exists, HMS is empty, target
  temperatures stay at zero, and `gcode_state` remains `IDLE`. Do not keep
  cycling path variants.
- **Project in `cache/` fails:** `project_file` can be accepted and then fail
  with `print_error: 83935248` / `0500-C010`. Clear the error and upload project
  files to FTPS root with `ftp:///<name>.gcode.3mf`.
- **HTTP/file URLs inert:** `file:///sdcard/cache/...` and local HTTP URLs may
  be accepted without fetching or starting. Do not use them for this workflow.
- **Bambu/Orca project export crash:** GUI-backed CLI project export on macOS
  can crash inside AppKit/BambuStudio. Use slicer CLI only for plain `.gcode`.
- **Stale printer state:** after LAN Only/Developer Mode changes, clear errors
  and power-cycle. Status can retain stale `FAILED`/HMS values.
- **Storage unavailable:** if FTPS auth works but upload fails with `553`, or
  status reports no SD/storage, resolve storage before MQTT start.

Use `clear-error --execute` only after the underlying cause is fixed. It
publishes `print.clean_print_error` and does not start motion.
