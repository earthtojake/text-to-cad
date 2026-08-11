# Falcon Heavy Reconstruction — Component Provenance & Confidence Map

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Citations in [RESEARCH.md](RESEARCH.md); per-part inventory in
[HIERARCHY.md](HIERARCHY.md); engine placements in
[ENGINE_INSTANCES.md](ENGINE_INSTANCES.md). Labels embed geometry status
(`__photogrammetric`, `__schematic`, `__decorative`, `__placeholder`,
`__nonfunctional`, `__linked`).

| Component group | Sources | Type | Confidence | Geometry status |
|---|---|---|---|---|
| Overall envelope (70 m × 12.2 m, core 3.66 m, fairing 5.2×13.1 m) | SpaceX FH page / User's Guide | official | High | measured (scale only) |
| `merlin1d_instance_*` ×27 | linked from `models/renders/merlin1d/` (vendored `merlin_common.py`); its PROVENANCE.md applies per instance; reduced decorative detail; cluster-fit exit 960 mm | linked model | per linked docs | linked subassembly |
| `*_engine_cluster__octaweb_9x` layout | "octaweb" publicly named (SpaceX/NASA); outer circle radius cluster-fit derived; tangential pump orientation inferred from packing | official (pattern) + derived | Medium (pattern), Low (radius/orientation) | photogrammetric estimate |
| `mvac_engine__linked_derivative_schematic` | Merlin powerhead linked; 165:1 nozzle official (User's Guide); niobium skirt public; exit 2.4–3.3 m conflicting → 2.9 m schematic | official (facts) + estimate (shape) | Medium/Low | schematic derivative |
| Tank barrels, white livery, black interstage, nosecones | SpaceX photos (Flickr/Commons), User's Guide figure | official imagery | Medium (form), Low (stations) | photogrammetric estimate |
| Grid fins (4/booster, titanium) | public statements + photos; size community-estimated | official (existence) + community | Medium/Low | photogrammetric; lattice schematic |
| Landing legs (4/core, stowed) | public statements/photos; "60 ft span" claim | official (existence) | Medium/Low | photogrammetric estimate |
| Booster nose/aft attach hardware | photos (existence); internals deliberately absent | photo | Low | schematic, **no internals** |
| Raceways, tank bands, decal/flag panels, clamps | photos | photo | Low | decorative |
| S1/S2 LOX & RP-1 tank volumes, domes, transfer tube | publicly stated LOX-forward arrangement (Wikipedia-indexed, press kits); volumes NOT dimensioned | index | Medium (order), Low (size) | schematic, non-functional |
| COPV-like placeholders | COPVs in LOX tank publicly known (AMOS-6 reporting); count/placement NOT public | official reporting | Medium (existence) | supported placeholder, **counts/positions invented** |
| Octaweb frames, avionics modules, separation block, payload adapter/payload | existence public at word-level; all geometry invented | index | Low | schematic placeholder, **no internals** |
| Fairing shell, seams, base ring | published envelope + photos | official | High (envelope), Low (details) | measured envelope + decorative |

## Confidence map (summary)

- **High:** published envelope figures and engine counts — used for scale only.
- **Medium:** octaweb pattern, LOX-forward tank order, grid fin/leg existence,
  MVac facts.
- **Low:** every station position, internal volume, bracket, and proportion
  beyond published figures.
- **Not modeled:** tank walls, weld schedules, separation internals, avionics
  architecture, COPV counts/placement, feed routing, engine internals
  (see linked merlin1d docs), pressurization/control logic.
