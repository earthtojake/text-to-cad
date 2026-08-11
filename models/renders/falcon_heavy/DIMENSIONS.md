# Falcon Heavy Reconstruction — Dimensions

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

Coordinates: vehicle centerline = **Z**, first-stage Merlin exit plane =
**Z = 0**, +Z up. Units mm, full scale. Side boosters at X = ±3660.

## Publicly sourced anchors (scale only)

| Quantity | Public value | Model value | Source | Confidence |
|---|---|---|---|---|
| Vehicle height | 70 m | Z = 0 → 70,000 | SpaceX Falcon Heavy page / User's Guide | High |
| Width (3 cores) | 12.2 m | core centers ±3,660; body extent ±5.9 m, legs/raceways to ~±6.1 m | SpaceX | High (nominal) |
| Core diameter | 3.66 m | 3,660 | SpaceX / User's Guide | High |
| Fairing | 5.2 m dia × 13.1 m | 5,200 × 13,100 | SpaceX / User's Guide | High |
| Engines | 27 × Merlin 1D (845 kN SL each) + 1 MVac | 27 + 1 instances | User's Guide | High |

## Photogrammetric / schematic estimates (LOW confidence)

| Quantity | Model value | Method |
|---|---|---|
| Booster tank top / interstage top | Z = 42,000 / 48,500 | photo proportion of stage stations |
| Octaweb outer engine circle | r = 1,290 | cluster-fit: 2·r·sin(22.5°) ≥ exit Ø with r + exit/2 ≤ 1,830 |
| Engine exit (vehicle copy) | 960 mm | cluster-fit refinement of the public 0.93–1.10 m photo band (linked model uses 1,040) |
| MVac exit / skirt length | 2,900 / 2,700 mm | public range 2.4–3.3 m (conflicting); schematic two-cone bell |
| Grid fins ~1.45 × 2.0 m; legs ~11.5 m stowed | — | photo proportion; leg span "60 ft deployed" claim informs length |
| S1 RP-1 tank (lower) Z 3,000–17,000; LOX (upper) 17,500–41,100 | — | public statements LOX-forward; volumes schematic |
| Tank bands, raceway runs, decal panels, attach blocks | — | decorative/schematic from photos |

All internal volumes are labeled schematic/non-functional; tank walls,
separation hardware, avionics, COPV counts/positions, and feed routing are
not modeled (see RESEARCH.md Known Unknowns).

**Stack-closure note (per RESEARCH.md §1.2):** unofficial component lengths
(booster 41.2–42.6 m, interstage ~4.5 m, S2 ~12.6 m, fairing 13.1–13.2 m) sum
past the official 70.0 m because the MVac recesses into the interstage and the
fairing wraps the S2 forward end. This model anchors the official 70.0 m
total and stretches the interstage station band (6.5 m) to house the MVac
derivative — a documented schematic choice, not a sourced dimension.
