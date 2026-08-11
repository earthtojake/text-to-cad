# Raptor 2 Reconstruction — Dimensions

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Model coordinate convention: engine centerline = **Z axis**, nozzle exit plane
= **Z = 0**, engine body extends toward **+Z**, thrust acts along **−Z**.
Units: millimeters, full scale.

## Publicly sourced dimensions (used for scale)

| Quantity | Value | Model value | Source | Confidence |
|---|---|---|---|---|
| Engine height | 3.1 m | 3100 mm (Z = 0 → 3100) | archived spacex.com/starship via Wikipedia ref | High (R1-era) / Medium (R2) |
| Nozzle exit diameter | 1.3 m | 1300 mm | Musk IAC 2017 via Wikipedia ref; Everyday Astronaut: R2 keeps R1 exit Ø | High |
| Expansion ratio (R1-era) | ε = 34.34 | informs throat estimate only | FAA Appendix G | High (R1) / Medium (R2) |
| Gimbal range | 15° | mount proportions only | Everyday Astronaut comparison | Medium |

## Photogrammetric / community estimates (LOW confidence — labeled estimates)

| Quantity | Model value | Method | Confidence |
|---|---|---|---|
| Throat diameter | 240 mm | Community-derived for R2: F = Cf·Pc·At with 230 tf / 300 bar / Cf≈1.6–1.75, consistent with EA "widened throat at constant exit"; public estimates cluster 235–250 mm (R2), 215–225 mm (R1) | Low |
| Effective expansion ratio | ~29.3 | (650/120)², follows from throat estimate at fixed 1300 mm exit | Low |
| Bell length (throat→exit) | 1560 mm | Proportion from public side photos (~50% of engine height); contour is a textbook Rao 80% parabolic approximation (θn=33°, θe=8°) — NOT SpaceX data | Low |
| Chamber inner diameter | 470 mm | Scaled from public photos of the powerhead relative to the 1300 mm exit | Low |
| Chamber top (injector face) height | Z = 2160 mm | Photo proportion | Low |
| Turbopump housing Ø / offset | 340 mm Ø at ±430 mm from centerline | Photo proportion; twin-pump FFSC layout per Wikipedia/community diagrams | Low |
| Shell/jacket thicknesses | 8 + 12 mm | **Decorative only** — real wall thicknesses are not public and are deliberately not represented | n/a (decorative) |

All other feature dimensions (ducts, valve blocks, gimbal block, brackets,
flanges, conduits) are schematic proportions chosen for visual plausibility
against public photographs; none is a sourced dimension.

## Reference physical data (annotation only, not geometry)

| Quantity | Raptor 2 value | Source |
|---|---|---|
| Sea-level thrust | 230 tf (2.26 MN) | SpaceX X post 1819795288116330594 |
| Chamber pressure | 300 bar | Musk statements via EA/Wikipedia |
| Engine mass | 1630 kg | SpaceX X post 1819795288116330594 |
| Isp | ~327 s SL / 347 s vac | SpaceX post + Wikipedia (see RESEARCH.md §2.4 note) |
| Mixture ratio | 3.6 (O/F) | FAA Appendix G / Draft PEA |
| Propellants | subcooled CH₄ / LOX | all sources |
