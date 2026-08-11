# Raptor 2 Reconstruction — Component Provenance & Confidence Map

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Every modeled component below carries: source URL(s), source type, confidence
(high/medium/low), and geometry status. Full citations and quotes live in
[RESEARCH.md](RESEARCH.md).

**Geometry status key:**
- `measured` — dimension from a published figure (scale only, no shape detail)
- `photogrammetric estimate` — proportions inferred from public photographs
- `schematic` — textbook/topology-level representation, no claimed fidelity
- `decorative` — purely visual detail with no source basis
- `unknown` — real detail not public; represented by a labeled placeholder

**Source shorthand** (full URLs in RESEARCH.md): `SX-R3` / `SX-R12` = SpaceX X
posts 1819772716339339664 / 1819795288116330594 (Aug 2024) · `IAC17` = Musk IAC
2017 presentation · `SX-ARC` = archived spacex.com/starship page ·
`FAA-G` = FAA Appendix G plume analysis · `EA-CMP` =
everydayastronaut.com/spacex-raptor-engine-comparison/ · `EA-RAP` =
everydayastronaut.com/raptor-engine/ · `WIKI` = en.wikipedia.org/wiki/SpaceX_Raptor
(index only) · `COMMONS` = commons.wikimedia.org Category:Raptor_(rocket_engine) ·
`NSF` = nasaspaceflight.com Raptor articles · `PHOTOS` = SpaceX/Commons/EA/NSF
public photos as a set.

## Exterior model (`raptor2.step.py`)

| Component (label) | Sources | Source type | Confidence | Geometry status |
|---|---|---|---|---|
| Overall envelope (height 3100, exit Ø1300) | SX-ARC, IAC17 via WIKI | official (archived) | High (R1-era) / Medium (as R2) | measured (scale only) |
| `nozzle_bell_inner_liner` + `regen_jacket` | FAA-G (ε=34.34), EA-CMP (same exit, wider throat), PHOTOS | regulatory + explainer | Medium (form), Low (contour) | schematic (Rao 80% bell approximation); shell thickness decorative |
| `heat_tint_band_*` | test/flight photos (COMMONS, SpaceX Flickr) | photo | Low | decorative |
| `nozzle_exit_stiffener_ring` | PHOTOS | photo | Low | photogrammetric estimate |
| `nozzle_fuel_manifold_ring`, `ch4_regen_downcomer_*` | EA-RAP + Techsight (regen path exists), PHOTOS | explainer + photo | Low | schematic routing |
| `chamber_inner_liner`, `combustion_chamber_envelope` | PHOTOS; chamber Ø470 community-derived | photo/community | Low | photogrammetric estimate; thickness decorative |
| `injector_head_dome` | PHOTOS | photo | Medium (existence/position), Low (shape) | photogrammetric estimate; **no element detail** |
| `thrust_cone`, `thrust_cone_gusset_*` | PHOTOS | photo | Low | photogrammetric estimate / schematic |
| `gimbal_block`, cross pins, ears, mount plate, bosses | PHOTOS; 15° gimbal range EA-CMP | photo + explainer | Medium (existence), Low (shape) | simplified exterior |
| `ox/fuel_turbopump_housing` | WIKI (twin-shaft FFSC), PHOTOS, community cycle diagrams (COMMONS SVGs) | index + photo | Medium (layout), Low (size/position) | exterior placeholder, **no internals** |
| `ox/fuel_preburner_dome` | same | index + photo | Medium (existence), Low (shape) | exterior placeholder, **no internals** |
| `ox/fuel_pump_volute` | PHOTOS | photo | Low | simplified exterior |
| `lox/ch4_main_inlet_pipe`, vehicle interface flanges | PHOTOS | photo | Low | photogrammetric estimate |
| `lox/ch4_main_valve_housing` + actuator | EA-CMP ("valves combined into valve plates"), PHOTOS | explainer + photo | Low | schematic, **no internals** |
| `ox/fuel_preburner_exhaust_duct`, head flanges | cycle topology (EA-RAP, WIKI), PHOTOS | explainer + photo | Medium (topology), Low (routing) | schematic routing |
| `lox_main_feed_duct` | same | explainer + photo | Low | schematic routing |
| `tvc_clevis_bracket_*`, pins, actuator housings | PHOTOS; gimbal range EA-CMP | photo + explainer | Low | photogrammetric estimate / schematic |
| `engine_controller_enclosure` | EA-CMP (R2 integrated controller), PHOTOS | explainer + photo | Low | photogrammetric placeholder |
| `harness_conduit_*` | PHOTOS (R2 much cleaner than R1 per EA-CMP) | photo | Low | decorative |

## Cutaway model (`raptor2_cutaway.step.py`) — additional schematic interior

All interior components are **schematic / inferred / non-functional**,
translucent, and carry those words in their labels. None claims dimensional or
mechanical fidelity. Cycle topology sources: EA-RAP, EA cycles article,
Techsight schematic, WIKI. Confidence on topology: High. Confidence on any
geometry: none claimed (status `schematic` or `unknown`).

| Component (label) | Represents | Geometry status |
|---|---|---|
| `hot_gas_expansion_volume`, `main_chamber_combustion_volume` | combustion gas path (orange) | schematic |
| `regen_cooling_band__simplified_annulus` | methane regenerative cooling jacket (green) | schematic; real channel geometry **unknown** |
| `schematic_injector_region__no_element_detail` | plain disk placeholder — injector internals are deliberately **not modeled** | unknown (placeholder) |
| `ox/fuel_turbopump_placeholder_volume` | featureless volumes; turbomachinery internals deliberately **not modeled** | unknown (placeholder) |
| `ox/fuel_rich_preburner_placeholder_volume` | featureless domes (blue/green); preburner internals deliberately **not modeled** | unknown (placeholder) |
| `*_propellant_inlet_flow`, `*_rich_gas_flow_to_injector`, `lox_feed_flow`, `ch4_regen_supply_flow` | FFSC flow arrows as tubes (LOX/ox-rich = blue, CH4/fuel-rich = green) | schematic |

## Exploded model (`raptor2_exploded.step.py`)

Same components as the exterior model; explode offsets and guide rods are
presentational annotations only (`explode_guide_*__annotation`).

## Raptor Vacuum variant (`raptor2_vac.step.py`)

Derived variant: the sea-level powerhead groups above, unchanged, plus an
extended `rvac_nozzle_bell_group`.

| Component (label) | Sources | Source type | Confidence | Geometry status |
|---|---|---|---|---|
| `rvac_nozzle_*` (ε≈80 extended bell, exit Ø ~2.15 m modeled) | ε≈80 Musk statement via EA Starbase interview (WIKI-indexed); exit 2.4 m announced figure (WIKI-indexed); bell length/contour = Rao 80% derivation | official-via-index + derived | Medium (ratio) / Low (contour, length) | schematic |
| `rvac_nozzle_extension_seam_ring`, `rvac_heat_tint_band` | public RVac photos | photo | Low | decorative |
| Fixed mount (real RVac is not gimbaled) | Wikipedia index | index | High (fact) | mount block kept as the SL simplified placeholder — **not** an RVac mount reconstruction |

## Confidence map (summary)

- **High:** engine-class envelope numbers used for scale (height, exit
  diameter, masses, thrust, chamber pressure) — official SpaceX figures.
- **Medium:** FFSC twin-pump layout, existence/position of gimbal, injector
  head, preburner-on-pump stacks, valve plates.
- **Low:** every specific curve, radius, duct route, bracket, and proportion in
  this model that is not one of the published envelope numbers. These are
  photogrammetric/schematic estimates.
- **Not modeled (unknown):** injector elements, turbopump/preburner/valve
  internals, wall thicknesses, cooling channel geometry, materials, control
  hardware — see RESEARCH.md §6.
