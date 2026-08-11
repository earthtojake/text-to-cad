# SpaceX Merlin 1D — Educational Public-Source Reconstruction

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

A museum/documentary-style CAD package of the SpaceX Merlin 1D sea-level
engine (Falcon 9 / Falcon Heavy first stage), reconstructed exclusively from
public sources — the SpaceX Falcon User's Guide, NASA press material, the
Smithsonian NASM flown-engine record, public photos, and reputable explainers.
Everything proprietary (pintle injector elements, turbopump/gas-generator
internals, cooling channels, wall thicknesses, valve internals, schedules) is
deliberately **not modeled**; hidden internals appear only as simplified,
translucent placeholder volumes labeled `schematic`/`inferred`/`nonfunctional`.

## Models (each ~260–275 named parts; see HIERARCHY.md)

| Entry | Contents |
|---|---|
| `merlin1d.step.py` | Exterior: Rao-approximation bell with stiffener bands and restrained heat tint, chamber + injector dome (pintle type noted, no elements), gimbal/TVC structure, side-mounted single-shaft turbopump + gas-generator placeholders, the distinctive turbine-exhaust duct, feed lines/valves, TEA-TEB ignition hardware, controller/harness, dense decorative hardware (bolt rings, flanges, bellows, clamps, sensors) |
| `merlin1d_cutaway.step.py` | 270° quarter-section (opening +Y) with color-coded gas-generator-cycle schematic: **blue** LOX, **amber** RP-1, **orange** hot gas, **translucent gray** inferred placeholders |
| `merlin1d_exploded.step.py` | Exploded educational view with translucent guide rods |
| `merlin_common.py` | Shared parametric geometry library (not an entry) |

Exports beside each entry: `.step`, `.iges`, `.stl`, `.obj`, `.glb` (native
parametric source = the `.step.py` itself). Regenerate IGES/OBJ with
`export_extras.py`; regenerate `HIERARCHY.md` with `gen_hierarchy.py`.

## Documentation

- [RESEARCH.md](RESEARCH.md) — full public-source dossier (per-fact URLs,
  source types, confidence, variant table, known unknowns §6).
- [PROVENANCE.md](PROVENANCE.md) — per-component source/confidence/geometry
  status + confidence map.
- [DIMENSIONS.md](DIMENSIONS.md) — sourced anchors vs photogrammetric
  estimates with methods.
- [HIERARCHY.md](HIERARCHY.md) — generated part hierarchy (~800 parts across
  the three models, repeats collapsed).
- `renders/` — hero, orthographic set, nozzle view, cutaway (plain +
  annotated), transparent overlay, exploded views, subsystem closeups.

## Fidelity statement

Only published figures (thrust, Isp, chamber pressure, expansion ratio, mass,
museum display envelope) anchor this model — and they set **scale and labels
only**. Every curve, duct route, and proportion beyond them is a
photogrammetric or schematic estimate with LOW confidence, and every part
label carries its geometry status. A Merlin Vacuum visual derivative was not
modeled: its published record (165:1 nozzle, niobium skirt) is variant-level
only, with conflicting public exit-diameter figures (see RESEARCH.md §5).
