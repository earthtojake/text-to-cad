# R1T modular topper digital prototype

This directory contains a source-controlled, STEP-first build123d engineering
prototype. Phase 2 adds a conceptual master topper volume to the nonproprietary
vehicle reference envelopes. It is not production-ready, structurally
validated, or fitment-trustworthy.

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

Run the Phase 2 concept-envelope checks with:

```bash
../../.venv/bin/python cad/phase2_checks.py
```

## Parameter provenance

Every major dimension is a `Parameter` in `cad/parameters.py` with one of:
`MEASURED`, `MANUFACTURER REFERENCE`, `ESTIMATED`, `DESIGN DECISION`, or
`PLACEHOLDER REQUIRING SCAN`.

Checkpoint 1 targets a 2022 Gen 1 R1T. It contains three
manufacturer-reference bed-envelope values: length, exposed cargo width, and
maximum bed height. They are corroborated where possible by Rivian's 2022
material, but come from the September 2025 R1T Upfitting Guide and must be
checked on the target vehicle. Rail, cab, port, control, and swept-envelope
geometry remains provisional. After scanning, update the affected parameter
records and their provenance, regenerate, inspect, and review every view before
advancing fitment geometry.

## Known limitations

See `reports/OPEN_ITEMS.md` and `references/measurement_requirements.md`.
The cab is a block envelope and vehicle interfaces are placeholders. The blue
topper solid is an external silhouette/design volume only; it is not a shell or
mold surface. No hatch mechanism, module interface, structure, load rating,
mounting geometry, seal, or tooling exists yet.

The visual surrogate is driven by five editable cross-sections in
`cad/parameters.py`. See `references/visual_reference_sources.md` for the
official imagery and CC-BY artist mesh used only as proportion references.
Replace those section rows with common-coordinate scan slices later; the loft,
assembly, export, and validation workflow can remain unchanged.

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
