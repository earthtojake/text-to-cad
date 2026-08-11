# SpaceX Raptor 2 — Educational Public-Source Reconstruction

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

A museum/documentary-style CAD package of the SpaceX Raptor 2 sea-level engine
(Starship / Super Heavy), reconstructed exclusively from public sources —
official SpaceX statements, FAA regulatory filings, and reputable public
explainers. Everything proprietary (injector elements, turbopump internals,
preburner internals, cooling channel geometry, wall thicknesses, valve
internals, materials, control hardware) is deliberately **not modeled**;
hidden internals appear only as simplified, translucent placeholder volumes
labeled `schematic` / `inferred` / `nonfunctional`.

## Models

| Entry | Contents |
|---|---|
| `raptor2.step.py` | Exterior assembly: Rao-approximation nozzle bell with heat-tint bands, chamber envelope, injector head dome, thrust cone + gimbal mount, twin turbopump/preburner exterior placeholders, main valve plates, visible ducting, TVC brackets, controller + harness |
| `raptor2_cutaway.step.py` | Quarter-section (270° shells, opening toward +X) with color-coded FFSC flow schematic: **blue** = LOX/oxygen-rich, **green** = methane/fuel-rich, **orange** = hot combustion gas, **translucent gray** = inferred placeholders |
| `raptor2_exploded.step.py` | Exploded educational view with translucent guide rods |
| `raptor2_vac.step.py` | Derived Raptor Vacuum variant: identical simplified powerhead with the nozzle extended to ε≈80 (Musk statement, MEDIUM confidence; bell geometry a schematic Rao derivation, LOW; ~4.39 m tall, exit Ø ~2.15 m vs the 2.4 m announced figure). Fixed-mount engine; the mount block remains the same simplified placeholder. Used as a linked subassembly by [`../starship`](../starship/README.md) |
| `raptor2_common.py` | Shared parametric geometry library (helper module, not an entry) |

Coordinates: centerline = Z, nozzle exit plane Z = 0, engine extends +Z,
thrust acts along −Z. Units mm, full scale (3100 mm tall).

## Documentation

- [RESEARCH.md](RESEARCH.md) — full public-source dossier with per-fact URLs,
  source types, confidence ratings, variant comparison (Raptor 1/2/3), and the
  known-unknowns list (§6).
- [PROVENANCE.md](PROVENANCE.md) — per-component source/confidence/geometry-status
  table and the summary confidence map.
- [DIMENSIONS.md](DIMENSIONS.md) — publicly sourced dimensions vs
  photogrammetric estimates (with methods), and annotation-only physical data.
- `renders/` — generated review renders (hero, orthographic, nozzle,
  cutaway, exploded views).

## Why Raptor 2 (not 1 or 3)

Raptor 2 sea-level is the default subject: it has the strongest public factual
record (official thrust/mass posts, 300 bar chamber pressure statements,
detailed public change-log vs Raptor 1 via Everyday Astronaut) while remaining
externally photographable. Raptor 3's dimensions are not separately published,
and its smooth internalized design hides most documentable features
(see RESEARCH.md §5 for the sourced variant comparison).

## Fidelity statement

Only the envelope numbers (height, exit diameter, masses, thrust, chamber
pressure) are sourced measurements — and they set **scale only**. Every curve,
duct route, and proportion beyond them is a photogrammetric or schematic
estimate with LOW confidence. This package is an educational visualization of
publicly documented architecture, not an engineering model of the engine.
