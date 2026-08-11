# Merlin 1D Reconstruction — Component Provenance & Confidence Map

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Every component carries source, type, confidence, and geometry status. Full
citations in [RESEARCH.md](RESEARCH.md). Per-part inventory in
[HIERARCHY.md](HIERARCHY.md) — part labels embed their geometry status
(`__photogrammetric`, `__schematic`, `__decorative`, `__placeholder`,
`__nonfunctional`).

**Geometry status key:** `measured` — from a published figure (scale only) ·
`photogrammetric estimate` — proportions from public photos · `schematic` —
textbook/topology-level · `decorative` — visual richness with no source basis ·
`unknown` — real detail not public; labeled placeholder.

**Source shorthand:** `SX-UG` = Falcon User's Guide 2025-05-09 · `NASA` =
CRS-6 press kit · `NASM` = Smithsonian Merlin 1D record · `WIKI` =
en.wikipedia.org/wiki/SpaceX_Merlin (index) · `PHOTOS` = SpaceX Flickr /
Commons / museum photos (URLs in RESEARCH.md §3) · `COMMUNITY` = forum/
aggregator estimates.

## Exterior (`merlin1d.step.py`)

| Component group | Sources | Type | Confidence | Geometry status |
|---|---|---|---|---|
| Overall scale (exit Ø1040, engine body ≈2.48 m, model incl. feed lines 2.92 m) | WIKI (0.92 m exit, uncited), NSF photo-scaling 0.93–1.10 m, NASM display ≤~2.7 m | index + photogrammetric + museum | Low–Medium | measured band (scale only) |
| `nozzle_liner`/`regen_jacket` + throat | ε=16 (COMMUNITY, multiply attested), regen milled-copper liner (SX-UG, NASA), Rao 80% textbook contour | official (cooling) + community (ratio) | Medium (form), Low (contour) | schematic; shell thickness decorative |
| `bell_stiffener_band_*`, `heat_tint_band_*`, exit ring | PHOTOS | photo | Low | decorative |
| `chamber_*`, `injector_dome` | PHOTOS; pintle TYPE official (SX-UG) — element geometry NOT modeled | photo + official (type only) | Low (shape) | photogrammetric estimate; **no element detail** |
| `thrust_cone`, gimbal block/pins/ears, mount plate | PHOTOS; gimbaled TVC official (SX-UG) | photo + official | Medium (existence), Low (shape) | simplified exterior |
| `tvc_*` brackets/housings/rod ends | SX-UG + NASA (kerosene-hydraulic TVC, two actuators per photos) | official (system) + photo | Medium/Low | photogrammetric estimate / schematic |
| `turbopump_housing`, volutes, `turbine_housing`, inlet dome | SX-UG + NASA (single-shaft dual-impeller GG cycle), PHOTOS for side-mount position | official (topology) + photo | High (topology), Low (size/position) | exterior placeholder, **no internals** |
| `gas_generator_*` | cycle official (SX-UG/NASA); placement photo-derived | official + photo | High (existence), Low (placement/shape) | exterior placeholder, **no internals** |
| `turbine_exhaust_duct`, skirt, bellows, brackets, heat shield | EXPLAINER + PHOTOS (distinctive dark duct beside bell) | explainer + photo | Medium (existence), Low (routing) | photogrammetric estimate |
| `lox/rp1_main_feed_line`, interface flanges, discharge/regen ducts, manifold | SX-UG (feed existence), PHOTOS | official + photo | Low (routing) | schematic routing |
| `*_main_valve_*` | PHOTOS; internals deliberately absent | photo | Low | schematic, **no internals** |
| `engine_controller_enclosure`, harness runs/clamps, `sensor_module_*` | WIKI (per-engine controller), PHOTOS | index + photo | Low | photogrammetric placeholder / decorative |
| `teateb_*` (ignition line, canister) | SX-UG (TEA-TEB ignition official) | official (existence) | Medium (existence), Low (shape) | schematic placeholder |
| All bolt rings, clamps, bellows convolutions | none (visual richness) | — | — | decorative |

## Cutaway interior (`merlin1d_cutaway.step.py`)

All interior parts are schematic/inferred/non-functional, translucent, and
labeled as such. Cycle topology (High confidence): SX-UG + NASA + explainers.
No geometric fidelity claimed anywhere below.

| Component | Represents | Geometry status |
|---|---|---|
| `hot_gas_expansion_volume`, `main_chamber_combustion_volume` | combustion gas path (orange) | schematic |
| `regen_cooling_band__simplified_annulus` | RP-1 regenerative cooling jacket (amber) — real channels **unknown** | schematic |
| `schematic_injector_region__no_element_detail` | plain disk; pintle internals deliberately **not modeled** | unknown (placeholder) |
| `lox/rp1_pump_placeholder_volume`, `turbine_placeholder_volume` | featureless volumes; turbomachinery internals deliberately **not modeled** | unknown (placeholder) |
| `gas_generator_placeholder_volume` | featureless volume; GG internals deliberately **not modeled** | unknown (placeholder) |
| `*_feed_flow`, `*_discharge_flow`, `turbine_exhaust_flow` | GG-cycle flow arrows (LOX=blue, RP-1=amber, hot gas=orange) | schematic |

## Exploded (`merlin1d_exploded.step.py`)

Same parts as the exterior; explode offsets and `explode_guide_*__annotation`
rods are presentational only.

## Confidence map (summary)

- **High:** thrust/Isp/throttle/propellants/cycle topology/regen-liner/
  pintle-type/TEA-TEB facts used for scale and labeling (official sources).
- **Medium:** side-pump layout, exhaust-duct existence, gimbal/TVC arrangement,
  ε=16.
- **Low:** every specific curve, duct route, proportion, and position beyond
  published figures — photogrammetric/schematic estimates.
- **Not modeled (unknown):** injector elements, pump/GG/valve internals,
  channel geometry, wall thicknesses, materials, schedules — RESEARCH.md §6.
