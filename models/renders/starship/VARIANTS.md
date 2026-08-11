# Variant Notes — Why V2 / Block 2, and V1/V3 Deltas

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

## Pinned: V2 / Block 2 (Flights 7–11, 2025)

Chosen because it has (1) itemized official change documentation (SpaceX
Flight 7 upgrade text), (2) stable cross-confirmed dimensions (9 m × 123.1 m;
ship 52.1 m; booster 71 m incl. 1.8 m ring), and (3) five flights of official
imagery including two booster catches and two fully successful missions
(Flights 10, 11). Full sourcing in [RESEARCH.md](RESEARCH.md) §0.

## Modeled configuration assumptions

- Booster externally carries over Block 1 geometry (documented): 33 × Raptor 2
  (13 gimbal / 20 fixed), 4 grid fins, 4 chines, vented 1.8 m hot-stage ring
  **modeled attached** (in flight it is jettisoned after boostback).
- Ship is Block 2: 52.1 m, forward flaps smaller/tip-ward/leeward (~140°
  included angle), 3-ring payload bay (~614 m³), both header tanks in the
  nose, windward TPS with ablative backup layer (backup layer not visually
  modeled).
- Engines are Raptor 2 family models from `models/renders/raptor2` — the RVac is
  a documented schematic derivation (ε≈80 bell on the SL powerhead).

## V1 / Block 1 deltas (retired, Flights 1–6)

- Ship 50.3 m (stack 121.3 m); 5-ring payload bay (~1,100 m³ concept volume).
- Forward flaps larger, mounted at ~180° (windward plane), closer to mid-nose.
- Both headers not consolidated in nose (CH4 header at common dome).
- IFT-1 flew without the hot-stage ring; ring added from Flight 2.

## V3 / Block 3 deltas (one flight, grounded under FAA mishap review as of July 2026)

- Stack 124.4 m; booster 72.3 m with **integrated** hot-staging section (no
  jettisonable ring); **3 grid fins** in a 90/90/180° "T", ~50% larger, mounted
  lower, doubling as catch hardware.
- Raptor 3 engines (250 tf initial rating); substantially larger booster
  transfer tube; docking drogues + propellant-transfer connections on the ship.
- Published propellant/thrust figures still disagree across sources — a key
  reason V3 was not pinned.
