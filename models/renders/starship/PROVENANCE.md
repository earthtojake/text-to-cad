# Starship / Super Heavy Reconstruction — Component Provenance & Confidence Map

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Pinned version: **V2 / Block 2** (see [RESEARCH.md](RESEARCH.md) §0 and
[VARIANTS.md](VARIANTS.md)). Geometry status key as in
[`../raptor2/PROVENANCE.md`](../raptor2/PROVENANCE.md): `measured` (published
figure, scale only) / `photogrammetric estimate` / `schematic` / `decorative`
/ `unknown` (placeholder). Source shorthand: `[S#]` refs resolve in
RESEARCH.md.

## Booster (`super_heavy.step.py`)

| Component (label) | Sources | Type | Confidence | Geometry status |
|---|---|---|---|---|
| Envelope (Ø9000, body 69200 + ring 1800 = 71 m) | S1 via S3/S4 | official-via-index | High (71 m) / Low (body-vs-ring split) | measured (scale only) |
| `booster_barrel`, `booster_aft_skirt` | S4, photos S22-S26 | index + photo | High (existence) / Low (stations) | photogrammetric estimate; shell thickness decorative |
| `booster_*_ring_seam_*` | RING_H 1.83 m ring construction, S4/S10 | index/explainer | Medium | decorative |
| `booster_common_dome`, `forward_dome`, `thrust_dome` | S4 (tank order LOX aft / CH4 fwd) | index | High (order) / Low (positions, shape) | schematic |
| `grid_fin_*` (4, fixed, ~5x2.5 m) | S4 (count, fixed, electric), S15/S16 (size est.) | index + explainer | High (count) / Low (size, clocking, lattice) | photogrammetric estimate; lattice decorative |
| `booster_chine_*` (4, on aft tank, house COPVs/batteries) | S4 | index | High (existence) / Low (shape) | photogrammetric estimate |
| `booster_raceway_*` | photos | photo | Low | schematic routing |
| `booster_catch_hardpoint_*` | S24 + catch coverage | photo | Medium (existence) / Low (shape) | photogrammetric estimate |
| `booster_copv_*` | S4 (COPVs in chines) | index | Low (position/size) | photogrammetric placeholder |
| `hot_stage_ring_group` (1.8 m vented, ~9 t, jettisoned; modeled attached) | S4, S28, S42 | index + explainer | High | photogrammetric estimate; vent posts decorative |
| `raptor_sl_booster_r*__instance` (33: 3+10 gimbal, 20 fixed) | S3/S4 (counts, gimbal split); ring radii photo packing | index + derived | High (counts) / Low (radii) | linked subassembly (see ../raptor2/PROVENANCE.md) |
| `booster_engine_bay_manifold_*`, `*_mount_block*` | cycle/feed existence S4/S12 | index/explainer | Low | schematic, non-functional |
| `booster_lox/ch4_tank_volume`, `downcomer`, `sump` | S4 (order, downcomer existence), volumes derived from 3400 t | index + derived | High (topology) / Medium (volumes) | schematic, translucent |
| `booster_skirt_stringer_*`, `avionics_module_*` | none (interior unknown) | — | — | unknown (labeled placeholders) |

## Ship (`starship_ship.step.py`)

| Component (label) | Sources | Type | Confidence | Geometry status |
|---|---|---|---|---|
| Envelope (Ø9000 x 52100) | S3/S5/S13 | official-via-secondary | High | measured (scale only) |
| `ship_barrel`, `ship_aft_skirt`, `ship_nosecone` | S5, photos | index + photo | High (existence) / Low (ogive profile) | photogrammetric estimate |
| `ship_*_ring_seam_*` | ring construction | index | Medium | decorative |
| `ship_common_dome`, `forward_dome`, `thrust_dome` | S5 (LOX aft / CH4 fwd order) | index | High (order) / Low (positions) | schematic |
| `aft_flap_*` (2, ~180° windward-biased) | S5, S13, photos | index + official-via-secondary | High (existence/arrangement) / Low (shape) | photogrammetric estimate |
| `forward_flap_*__v2_leeward_140deg` (2, smaller, tip-ward, ~140° included) | S13 (official Flight 7 text), S5 | official-via-secondary | High (arrangement) / Low (shape) | photogrammetric estimate |
| `*_flap_fairing_*` | photos | photo | Low | schematic |
| `tps_windward_band_*`, `tps_nosecone_windward` (~18,000 tiles, windward, 1400°C) | S5, S13 | index + official-via-secondary | High (coverage) / Low (boundary) | schematic (smooth field) |
| `tps_hex_tile_*` (featured array, 100+ instanced hex tiles) | tile shape public in photos | photo | Medium (shape) / n/a (layout symbolic) | decorative |
| `ship_leeward_raceway` | photos | photo | Low | schematic routing |
| `raptor_sl_ship_*__instance` (3, gimbal, center) | S5 | index | High | linked subassembly |
| `raptor_vac_ship_*__instance` (3, fixed, 120°) | S5, S6 (ε~80, exit 2.4 m announced / 2.15 m modeled) | index | High (count) / Medium (size) | linked subassembly (derived variant, see ../raptor2/PROVENANCE.md) |
| `ship_lox/ch4_tank_volume`, `ch4_downcomer` | S5, S13 (feedline existence); volumes derived from 1500 t | index + derived | High (topology) / Medium (volumes) | schematic, translucent |
| `ship_nose_lox_header`, `ship_ch4_header_below_nose_lox` | S5/S33 (V2 both-in-nose) | index + community | Medium | schematic placeholder |
| `ship_payload_bay_volume` (614 m³) | S5 | index | Medium | schematic |
| `ship_avionics_module_*`, `flap_root_actuator_placeholder_*`, mount blocks | none (internals unknown) | — | — | unknown (labeled placeholders) |

## Stack models

`starship_stack.step.py` composes the two assemblies + hot-stage ring;
`starship_cutaway.step.py` sections hull shells 270° (opening +Y/leeward) and
adds the schematic interiors; `starship_exploded.step.py` applies
presentational offsets and guide rods (`*__annotation`). Engine instances are
linked, unmodified Raptor subassemblies — full per-instance placement in
[INSTANCE_MAP.md](INSTANCE_MAP.md); part tree in [HIERARCHY.md](HIERARCHY.md).

## Confidence map (summary)

- **High:** stack/booster/ship envelope dimensions, engine counts and gimbal
  split, tank order, flap/fin/chine/ring existence and arrangement, TPS
  coverage side, hot-stage ring existence (all used for scale/topology only).
- **Medium:** payload bay volume, header-tank consolidation (V2), RVac exit
  size, derived tank volumes, catch hardpoints.
- **Low:** every specific station height, ring radius, fin/flap/chine
  proportion, duct route, and placeholder position — photogrammetric or
  schematic estimates.
- **Not modeled (unknown):** everything in RESEARCH.md §7 — wall construction,
  feedline routing, actuation internals, TPS attachment, avionics, engine
  mount detail. Present only as labeled translucent placeholders.
