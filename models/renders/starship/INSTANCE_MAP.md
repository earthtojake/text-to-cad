# Raptor Engine Instance Map

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**


Linked subassemblies from `models/renders/raptor2` (raptor2_common). Coordinates are
stage-local (mm): booster engines in booster frame (aft plane Z=0), ship engines
in ship frame; in the stack the ship frame sits at Z=+71,000 mm (69,200 body +
1,800 ring). Azimuth = engine local +X (turbopump axis) heading. Ring radii are
photogrammetric estimates (LOW confidence); counts and gimbal split are
documented (HIGH).


## Super Heavy — 33 x Raptor 2 sea-level

| # | Label | Ring | x (mm) | y (mm) | az (deg) | Gimbal |
|---|---|---|---|---|---|---|
| 1 | `raptor_sl_booster_r1_01__instance` | 1 | 950 | 0 | 0.0 | yes |
| 2 | `raptor_sl_booster_r1_02__instance` | 1 | -475 | 823 | 120.0 | yes |
| 3 | `raptor_sl_booster_r1_03__instance` | 1 | -475 | -823 | 240.0 | yes |
| 4 | `raptor_sl_booster_r2_04__instance` | 2 | 2187 | 711 | 18.0 | yes |
| 5 | `raptor_sl_booster_r2_05__instance` | 2 | 1352 | 1861 | 54.0 | yes |
| 6 | `raptor_sl_booster_r2_06__instance` | 2 | 0 | 2300 | 90.0 | yes |
| 7 | `raptor_sl_booster_r2_07__instance` | 2 | -1352 | 1861 | 126.0 | yes |
| 8 | `raptor_sl_booster_r2_08__instance` | 2 | -2187 | 711 | 162.0 | yes |
| 9 | `raptor_sl_booster_r2_09__instance` | 2 | -2187 | -711 | 198.0 | yes |
| 10 | `raptor_sl_booster_r2_10__instance` | 2 | -1352 | -1861 | 234.0 | yes |
| 11 | `raptor_sl_booster_r2_11__instance` | 2 | -0 | -2300 | 270.0 | yes |
| 12 | `raptor_sl_booster_r2_12__instance` | 2 | 1352 | -1861 | 306.0 | yes |
| 13 | `raptor_sl_booster_r2_13__instance` | 2 | 2187 | -711 | 342.0 | yes |
| 14 | `raptor_sl_booster_r3_14__instance` | 3 | 3820 | 0 | 0.0 | no |
| 15 | `raptor_sl_booster_r3_15__instance` | 3 | 3633 | 1180 | 18.0 | no |
| 16 | `raptor_sl_booster_r3_16__instance` | 3 | 3090 | 2245 | 36.0 | no |
| 17 | `raptor_sl_booster_r3_17__instance` | 3 | 2245 | 3090 | 54.0 | no |
| 18 | `raptor_sl_booster_r3_18__instance` | 3 | 1180 | 3633 | 72.0 | no |
| 19 | `raptor_sl_booster_r3_19__instance` | 3 | 0 | 3820 | 90.0 | no |
| 20 | `raptor_sl_booster_r3_20__instance` | 3 | -1180 | 3633 | 108.0 | no |
| 21 | `raptor_sl_booster_r3_21__instance` | 3 | -2245 | 3090 | 126.0 | no |
| 22 | `raptor_sl_booster_r3_22__instance` | 3 | -3090 | 2245 | 144.0 | no |
| 23 | `raptor_sl_booster_r3_23__instance` | 3 | -3633 | 1180 | 162.0 | no |
| 24 | `raptor_sl_booster_r3_24__instance` | 3 | -3820 | 0 | 180.0 | no |
| 25 | `raptor_sl_booster_r3_25__instance` | 3 | -3633 | -1180 | 198.0 | no |
| 26 | `raptor_sl_booster_r3_26__instance` | 3 | -3090 | -2245 | 216.0 | no |
| 27 | `raptor_sl_booster_r3_27__instance` | 3 | -2245 | -3090 | 234.0 | no |
| 28 | `raptor_sl_booster_r3_28__instance` | 3 | -1180 | -3633 | 252.0 | no |
| 29 | `raptor_sl_booster_r3_29__instance` | 3 | -0 | -3820 | 270.0 | no |
| 30 | `raptor_sl_booster_r3_30__instance` | 3 | 1180 | -3633 | 288.0 | no |
| 31 | `raptor_sl_booster_r3_31__instance` | 3 | 2245 | -3090 | 306.0 | no |
| 32 | `raptor_sl_booster_r3_32__instance` | 3 | 3090 | -2245 | 324.0 | no |
| 33 | `raptor_sl_booster_r3_33__instance` | 3 | 3633 | -1180 | 342.0 | no |

## Ship — 3 x Raptor 2 SL (gimbal) + 3 x Raptor Vacuum (fixed)

| # | Label | Variant | x (mm) | y (mm) | az (deg) | Gimbal |
|---|---|---|---|---|---|---|
| 1 | `raptor_sl_ship_01__instance` | Raptor 2 SL | 0 | 1300 | 90.0 | yes |
| 2 | `raptor_sl_ship_02__instance` | Raptor 2 SL | -1126 | -650 | 210.0 | yes |
| 3 | `raptor_sl_ship_03__instance` | Raptor 2 SL | 1126 | -650 | 330.0 | yes |
| 4 | `raptor_vac_ship_01__instance` | Raptor Vacuum (derived) | 2555 | 1475 | 30.0 | no (fixed) |
| 5 | `raptor_vac_ship_02__instance` | Raptor Vacuum (derived) | -2555 | 1475 | 150.0 | no (fixed) |
| 6 | `raptor_vac_ship_03__instance` | Raptor Vacuum (derived) | -0 | -2950 | 270.0 | no (fixed) |

Engine metadata (sources, confidence, geometry status) is inherited from
[`../raptor2/PROVENANCE.md`](../raptor2/PROVENANCE.md); the RVac variant is a
documented schematic derivation (eps~80 bell on the SL powerhead).
