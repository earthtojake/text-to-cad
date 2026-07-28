# R1T modular topper digital prototype

This directory contains a source-controlled, STEP-first build123d engineering
prototype. Checkpoint 1 includes nonproprietary vehicle reference envelopes
only. It is not production-ready, structurally validated, or fitment-trustworthy.

## Regenerate

Create the repository CAD environment per `CONTRIBUTING.md`, then run from this
directory:

```bash
../../.venv/bin/python cad/exports.py
```

The script generates:

- `outputs/step/R1T_TOPPER_ASSEMBLY.step`
- hidden adjacent CAD Viewer GLB/topology sidecars
- stable orthographic and three-quarter PNGs under `outputs/renders/`

Run the Checkpoint 1 source checks with:

```bash
../../.venv/bin/python cad/checkpoint1_checks.py
```

## Parameter provenance

Every major dimension is a `Parameter` in `cad/parameters.py` with one of:
`MEASURED`, `MANUFACTURER REFERENCE`, `ESTIMATED`, `DESIGN DECISION`, or
`PLACEHOLDER REQUIRING SCAN`.

Checkpoint 1 contains no measured or manufacturer-reference vehicle values.
After scanning, update the affected parameter records and their provenance,
regenerate, inspect, and review every view before advancing the envelope.

## Known limitations

See `reports/OPEN_ITEMS.md` and `references/measurement_requirements.md`.
The cab is a block envelope, interfaces are placeholders, and no topper shell,
hatch mechanism, module interface, structure, load rating, or tooling exists
yet.

## CAD Explorer / CAD Viewer

Start CAD Viewer with the repository's `cad-viewer` skill and use the repository
`models/` directory as `?dir=`. Select
`r1t_topper/outputs/step/R1T_TOPPER_ASSEMBLY.step`.

Stable follow-up references use the selector tokens returned by:

```bash
../../.venv/bin/python ../../skills/cad/scripts/inspect refs \
  outputs/step/R1T_TOPPER_ASSEMBLY.step --facts --planes --positioning
```

Selector tokens are local to this STEP file and should be paired with its
viewer link in revision requests.
