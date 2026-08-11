# Starship / Super Heavy Reconstruction — Dimensions

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Coordinates: per-vehicle centerline = **Z**, aft (nozzle exit) plane = **Z=0**,
+Z up. Stack model: booster body Z 0–69,200; hot-stage ring 69,200–71,000;
ship local frame offset +71,000 (stack top 123,100). Windward = **−Y**.
Units mm, full scale.

## Publicly sourced dimensions (scale only)

| Quantity | Value | Model value | Source | Confidence |
|---|---|---|---|---|
| Stack height (V2) | 123.1 m | 123,100 mm | Wikipedia index of SpaceX figures | High |
| Diameter | 9 m | 9,000 mm | SpaceX via index | High |
| Booster height | 71 m (incl. 1.8 m ring) | 69,200 + 1,800 mm | Wikipedia index | High (71) / Low (split) |
| Ship height (V2) | 52.1 m | 52,100 mm | official Flight 7 text via secondary | High |
| Hot-stage ring | 1.8 m, ~9 t | 1,800 mm | Wikipedia index | High |
| Engine counts | 33 booster (13 gimbal) + 3 SL + 3 RVac ship | same | Wikipedia index | High |
| RVac exit diameter | 2.4 m announced | 2,146 mm (ε=80 derivation; see note) | Wikipedia index / derived | Medium |
| Barrel ring height | ~1.83 m | RING_H 1,830 mm (seam spacing) | public build coverage | Medium |
| Propellant (booster / ship) | 3,400 t / 1,500 t | tank volumes sized to match | index + official text | High |
| Payload bay volume (V2) | 614 m³ | annotation on payload volume | Wikipedia index | Medium |

## Photogrammetric / derived estimates (LOW confidence — labeled estimates)

| Quantity | Model value | Method |
|---|---|---|
| Engine ring radii | 950 / 2,300 / 3,820 mm | packing analysis of official underside photos with the published 1.3 m engine envelope |
| Tank station heights | booster LOX top 38,500; CH4 top 65,200; ship LOX top 21,000; CH4 top 33,200 | derived from propellant masses (LOX 1.14 t/m³, CH4 0.44 t/m³) at 9 m barrel section |
| Grid fin size | 2,600 × 3,300 × 320 mm | explainer estimates (~5 × 2.5 m class) scaled to barrel photos |
| Flap outlines, chine/raceway sections, ogive profile, skirt heights, dome aspects | see `starship_common.py` constants | proportion matching against official photos |
| Shell/dome thicknesses | 40–85 mm | **decorative only** — real wall construction is not public and is deliberately not represented |

### Packing note (documented artifact)

Twenty outer engines at the published 1.3 m engine diameter cannot pack at the
photographed outer-ring radius without ~0.1 m lip contact (spacing ≈ 1.2 m).
The published 1.3 m is the powerhead envelope; the real bell exit is likely
≤1.22 m. The model keeps the published engine geometry, so adjacent outer-ring
nozzle lips intersect slightly — visible only in extreme close-up, retained in
favor of the published figure.

## Reference physical data (annotation only, not geometry)

| Quantity | V2 value | Source |
|---|---|---|
| Liftoff thrust | ~74–81 MN (33 × Raptor 2) | Wikipedia index |
| Stack liftoff mass | ~5,300 t | Wikipedia index |
| TPS | ~18,000 hex tiles, windward, ~1,400 °C | Wikipedia index |
| Payload to LEO | ~35 t demonstrated-era (100+ t design goal) | per-block tables via index |
