# SpaceX Falcon Heavy — Educational Public-Source Reconstruction

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

A museum/documentary-style full-vehicle CAD package of the SpaceX Falcon
Heavy, built exclusively from public sources and **reusing the Merlin 1D
package** (`models/renders/merlin1d/`) as a linked subassembly: 27 sea-level
Merlin instances in three 8-around-1 octaweb clusters, plus a Merlin Vacuum
derivative on the second stage. Everything proprietary (tank walls, weld
schedules, separation internals, avionics, COPV counts/placement, feed
routing, engine internals) is deliberately **not modeled**; internals are
schematic, translucent, labeled placeholders.

## Models (~2,150 named parts each via instancing; see HIERARCHY.md)

| Entry | Contents |
|---|---|
| `falcon_heavy.step.py` | Full stack: three cores (white livery, black interstage, soot-tone bands, decal panels), 27 linked Merlin 1D engines, side-booster nosecones, grid fins, stowed landing legs, raceways + clamps, attach hardware, MVac second stage, 5.2 m fairing |
| `falcon_heavy_cutaway.step.py` | Center core + S2 + fairing sectioned 270° (opening +Y): schematic LOX/RP-1 volumes (blue/amber), transfer tube, domes, COPV-like placeholders, octaweb frames, avionics + separation placeholders, payload adapter + payload placeholder |
| `falcon_heavy_exploded.step.py` | Boosters outboard, stage/fairing lifted, guide rods |
| `falcon_common.py` / `merlin_common.py` | Vehicle library + vendored linked engine library (source of truth: `models/renders/merlin1d/merlin_common.py`) |

Exports beside each entry: `.step`, `.iges`, `.stl`, `.obj`, `.glb`
(native parametric source = the `.step.py`). Helpers: `export_extras.py`,
`gen_hierarchy.py`, `gen_engine_map.py`.

## Documentation

- [RESEARCH.md](RESEARCH.md) — cited dossier (dimensions, structure, engine
  layout, MVac, known unknowns).
- [PROVENANCE.md](PROVENANCE.md) — per-group source/confidence/geometry status.
- [DIMENSIONS.md](DIMENSIONS.md) — published anchors vs estimates + methods.
- [HIERARCHY.md](HIERARCHY.md) — generated part hierarchy.
- [ENGINE_INSTANCES.md](ENGINE_INSTANCES.md) — generated 27+1 engine map.
- `renders/` — full-stack hero, orthographic views, 27-engine underside,
  cutaway, exploded, engine-cluster closeups.

## Fidelity statement

Published envelope figures (70 m × 12.2 m, 3.66 m cores, 5.2 × 13.1 m
fairing, 27 × 845 kN engines) set **scale and counts only**. Station
positions, internal volumes, and every bracket beyond them are photogrammetric
or schematic estimates with LOW confidence. The engine cluster embeds one
documented derivation: nine bells inside a 3.66 m circle bound the exit
diameter to ≤ ~1.0 m, refining the vendored engine copy to 960 mm within the
public 0.93–1.10 m band.
