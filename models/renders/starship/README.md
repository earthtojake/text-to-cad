# SpaceX Starship / Super Heavy — Educational Public-Source Reconstruction

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

A museum/documentary-style CAD package of the full Starship / Super Heavy
launch system, pinned to **V2 / Block 2** (as flown Flights 7–11, 2025) and
reconstructed exclusively from public sources. The 39 Raptor engines are
**linked subassemblies** instanced from the sibling
[`models/renders/raptor2`](../raptor2/README.md) package (33 sea-level on the
booster, 3 sea-level + 3 derived Raptor Vacuum on the ship). Everything
proprietary (tank wall construction, feedline routing, flap/fin actuation,
TPS attachment, avionics, engine mounts, valve/manifold detail) is deliberately
**not modeled**; hidden internals appear only as dense but simplified,
translucent placeholder volumes labeled `schematic` / `placeholder` /
`nonfunctional`.

## Models

| Entry | Contents |
|---|---|
| `super_heavy.step.py` | Booster: 9 m × 69.2 m body, 33 engine instances (3+10 gimbal rings + 20 fixed), 4 grid fins, 4 chines, raceways, catch hardpoints, COPV placeholders |
| `starship_ship.step.py` | Ship: 9 m × 52.1 m, 3 SL + 3 RVac instances, V2 leeward forward flaps + aft flaps, windward TPS field with instanced hex-tile array, leeward raceway |
| `starship_stack.step.py` | Full 123.1 m stack: booster + vented hot-stage ring + ship |
| `starship_cutaway.step.py` | 270° hull section (opens leeward/+Y) with dense schematic internals: LOX/CH4 tank volumes, downcomers, nose header tanks, payload volume, avionics, stringers, engine-bay manifolds and mounts |
| `starship_exploded.step.py` | Stage-separation exploded view: ship / hot-stage ring / booster / engine clusters / flaps / TPS / internals, with guide rods |
| `starship_common.py` | Shared parametric library (helper, not an entry) |

Coordinates: centerline = Z, aft engine-exit plane Z = 0, +Z up, windward = −Y.
Units mm, full scale. ~2,560 solids in the stack model (instanced).

## Documentation

- [RESEARCH.md](RESEARCH.md) — version pinning, per-fact sources + confidence,
  flight history, known unknowns (§7)
- [VARIANTS.md](VARIANTS.md) — why V2, and V1/V3 deltas
- [PROVENANCE.md](PROVENANCE.md) — per-component source/confidence/geometry-status
  table + confidence map
- [DIMENSIONS.md](DIMENSIONS.md) — sourced dimensions vs photogrammetric
  estimates (with methods), packing note
- [INSTANCE_MAP.md](INSTANCE_MAP.md) — all 39 Raptor instance placements
- [HIERARCHY.md](HIERARCHY.md) — generated part tree
- `renders/` — render suite (hero, orthographic, engine clusters, cutaway,
  transparent, exploded, detail closeups)

## Color coding

LOX / oxygen-rich = blue · methane / fuel-rich = green · hot gas = orange/red ·
stainless hull = neutral metal · TPS = matte charcoal · inferred internals =
translucent gray · placeholders = semi-transparent and labeled.

## Fidelity statement

Only the published envelope numbers (9 m diameter, stage heights, engine
counts, propellant masses) are sourced measurements — and they set scale and
topology only. Every station height, ring radius, fin/flap proportion, and
duct route beyond them is a photogrammetric or schematic estimate with LOW
confidence, and all internals are non-functional placeholders. This package is
an educational visualization of publicly documented architecture, not an
engineering model of the vehicle.
