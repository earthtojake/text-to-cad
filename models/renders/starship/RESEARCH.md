# Starship / Super Heavy — Public-Source Dossier for Educational CAD Reconstruction

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

**Prepared:** July 2026. **Scope:** exterior-geometry / schematic-level facts only, for a non-functional educational model. Raptor engine internals are explicitly out of scope (covered by `models/renders/raptor2/RESEARCH.md`). All facts from public online sources; each carries a source reference [S#], a source type (OFFICIAL / REG / EXPLAINER / WIKI-IDX / COMMUNITY), and a confidence rating.

**Method note:** `spacex.com/vehicles/starship` and `spacex.com/updates/starship-v3` were fetched directly and both render as empty JavaScript shells with no static content [S1][S2]. Official SpaceX figures are therefore cited as quoted/indexed by Wikipedia and by outlets that reproduce SpaceX's own update text (Leonard David's blog reproduces SpaceX's official Flight 7 upgrade text [S13]; Teslarati reproduces the official V3 update content [S14]). These are marked OFFICIAL-via-secondary.

---

## 0. Version landscape and recommendation

### Version/flight history (as of July 2026)

| Flight | Date | Booster / Ship | Version | Outcome (booster / ship) |
|---|---|---|---|---|
| 1 (IFT-1) | 2023-04-20 | B7 / S24 | Block 1 | Destroyed (AFTS) before staging |
| 2 | 2023-11-18 | B9 / S25 | Block 1 | Booster lost after boostback / ship AFTS |
| 3 | 2024-03-14 | B10 / S28 | Block 1 | Booster lost low / ship lost on reentry |
| 4 | 2024-06-06 | B11 / S29 | Block 1 | Both controlled splashdowns |
| 5 | 2024-10-13 | B12 / S30 | Block 1 | First tower catch / ship on-target splashdown |
| 6 | 2024-11-19 | B13 / S31 | Block 1 | Booster diverted to water / ship splashdown |
| 7 | 2025-01-16 | B14 / S33 | **Block 2 ship debut** | Booster caught / ship destroyed on ascent |
| 8 | 2025-03-06 | B15 / S34 | Block 2 | Booster caught / ship lost on ascent |
| 9 | 2025-05-27 | B14-2 / S35 | Block 2 (first booster reflight) | Booster lost / ship broke up |
| 10 | 2025-08-26 | B16 / S37 | Block 2 | Booster splashdown / ship full success, deployed 8 Starlink simulators |
| 11 | 2025-10-13 | B15-2 / S38 | Block 2 | Booster splashdown / ship full success |
| 12 | 2026-05-22 | B19 / S39 | **Block 3 (V3) debut**, Pad 2 | Booster lost after abnormal post-staging flip, high-speed water impact / ship deployed 22 Starlink simulators, survived reentry, Indian Ocean splashdown |

Sources: [S7] WIKI-IDX (list of launches, fetched), [S8] WIKI-IDX (Flight 12 article, fetched), [S17][S19][S38] EXPLAINER. Confidence: high.

- V3/Block 3 status: one flight (Flight 12); FAA declared the Super Heavy failure a **mishap on 2026-05-27** and grounded Starship pending investigation [S8][S37]. REG/WIKI-IDX, high. Flight 13 (B20/S40, second V3) in preparation, July–August 2026 timeframe [S17 search-indexed]. Medium.

### Recommendation: model V2 / Block 2 (as flown Flights 7–11, 2025)

Justification:
1. **Most complete official documentation.** SpaceX published an itemized official description of the Block 2 ship changes for Flight 7 (flap redesign, +25% propellant, feedline changes, tile changes) [S13, OFFICIAL-via-secondary]. Dimensions are stable and cross-confirmed: ship 52.1 m, booster 71 m, stack ~123.1 m [S3][S4][S5, WIKI-IDX indexing SpaceX figures].
2. **Five flights of imagery** including two tower catches and two end-to-end successful missions (Flights 10, 11) with the payload-deploy system demonstrated — abundant official photos of every exterior feature.
3. **V3 is not yet well-pinned.** It has flown once, is grounded under an FAA mishap investigation, and its published figures still disagree across sources (booster propellant 3,650 vs 4,050 t; thrust 8,250 vs 9,240 tf) [S3][S4][S31][S32]. Geometry (3-fin arrangement, integrated hot-stage dome) is known qualitatively but with few dimensioned references.
4. **V1 is retired** (last flight Nov 2024). It is equally well-photographed and its dims are kept below as the reference baseline, but modeling a retired variant is less useful; V2 also shares the V1 booster's external geometry almost entirely, so a V2 model covers most of V1 for free.

**Variant assumption for the model:** V2 stack = Block 1-geometry Super Heavy (71 m incl. ring, 33 × Raptor 2, 4 grid fins, jettisonable 1.8 m hot-stage ring modeled attached) + Block 2 ship (52.1 m, repositioned forward flaps). See VARIANTS.md.

---

## 1. Stack dimensions

| Quantity | V1 / Block 1 (Flights 1–6) | V2 / Block 2 (Flights 7–11) | V3 / Block 3 (Flight 12+) | Source / type / confidence |
|---|---|---|---|---|
| Total stack height | 121.3 m (398 ft) | ~123.1–123.3 m (Wikipedia gives 123.1 m) | 124.4 m | [S3][S5][S30][S31] OFFICIAL-via-WIKI-IDX; high |
| Diameter (both stages) | 9 m (30 ft) | 9 m | 9 m | [S3][S4][S5] OFFICIAL-via-WIKI-IDX; high |
| Super Heavy height | 71 m (233 ft), of which 1.8 m is the vented interstage (69 m without it) | 71 m (booster externally near-identical to Block 1) | 72.3 m (237 ft) | [S4][S31] WIKI-IDX; high |
| Ship height | 50.3 m (165 ft) | 52.1 m (171 ft) (+~1.8 m over Block 1, per official Flight 7 text) | 52.1 m implied (124.4 − 72.3) | [S3][S5][S13] OFFICIAL-via-secondary + WIKI-IDX; high (V1/V2), medium (V3) |
| Hot-stage/interstage ring | 1.8 m tall vented ring, ~9 t, added from Flight 2 | Same, jettisoned in flight (see §4) | No separate ring — function integrated into booster forward dome | [S4][S14][S42] WIKI-IDX + OFFICIAL-via-secondary; high |
| Fully-fueled stack mass | ~5,000 t | ~5,300 t (11.7 M lb) | not published (>5,600 t derived) | [S3][S39] WIKI-IDX; medium |

---

## 2. Engine layout (instancing-critical)

### Super Heavy — 33 Raptors
- **Ring arrangement: 3 inner + 10 middle + 20 outer.** [S3][S4] WIKI-IDX, high.
- **Gimbaling: the inner 13 (3 center + 10 middle ring) gimbal; the outer 20 are fixed.** The outer 20 are lit by ground-support equipment and cannot relight in flight; landing burns use subsets of the inner 13. [S4] WIKI-IDX, high.
- V1/V2 engines: Raptor 2, 230 tf each. V3: Raptor 3, 250 tf initial rating. [S6][S14][S31]; high/medium.
- **Ring radii — PHOTOGRAMMETRIC/DERIVED ESTIMATE, no official figures exist.** From official underside photos (e.g. [S23][S26]) with a sea-level Raptor envelope Ø 1.3 m [S6], geometric packing gives: outer ring PCD ≈ 7.4–7.9 m; middle ring PCD ≈ 4.2–5.0 m; inner cluster PCD ≈ 1.6–2.2 m. Confidence: **low** (modeling estimates). COMMUNITY/derived.

### Ship — 3 sea-level + 3 vacuum
- **3 sea-level Raptors, center cluster, gimbaling** (electric TVC from Flight 3 onward). [S5] WIKI-IDX, high.
- **3 Raptor Vacuum (RVac), fixed, mounted at 120° spacing**, interleaved with the sea-level cluster, nozzles close to the 9 m mold line. [S5] WIKI-IDX, high (count/fixed), medium (exact clocking).
- **RVac public specs:** nozzle exit diameter **2.4 m (7.9 ft)** announced (community photo-estimates ~2.3 m) [S6] WIKI-IDX, medium; expansion ratio **~80** [S6] (traces to Musk statement), medium; thrust Raptor 2 RVac **258 tf**, Isp ~380 s vac [S6][S14], high; engine length **not published** — RVac visibly longer than the 3.1 m SL engine (~4.5–4.7 m community photo-estimates, low; the model derives ~4.4 m from the ε=80 Rao approximation, labeled schematic).
- V3 ship: still 6 engines [S8], high; a 9-engine ship is a future Block 4 concept only [S3], medium.

---

## 3. Tank architecture (schematic level)

### Super Heavy
- **Section order, aft → forward: engines/thrust section → LOX tank → common dome → CH4 tank → vented interstage.** LOX is the lower/aft tank. [S4] WIKI-IDX, high.
- Propellant capacity: **3,400 t total ≈ 2,700 t LOX + 700 t CH4** (Block 1/2). V3 figures disputed (3,650–4,050 t). [S1 via S4][S3][S32]; high (V1/V2), low-medium (V3).
- Derived volumes for modeling (LOX ≈ 1.14 t/m³ subcooled, CH4 ≈ 0.44 t/m³): LOX ≈ 2,400 m³, CH4 ≈ 1,600 m³. Derived, medium.
- **Common dome** separates the tanks. A single **methane downcomer** runs from the CH4 tank down through the LOX tank to the engine manifolds (V3: "substantially larger transfer tube"). [S4][S12][S14]; high (existence), medium (V3 sizing).
- Booster dry mass: ~275 t. [S4] WIKI-IDX, low-medium.

### Ship (Block 2 pinned)
- **Section order, aft → forward: engine bay → LOX tank → common dome → CH4 tank → payload bay → nosecone.** LOX aft. [S5] WIKI-IDX, high.
- Propellant: Block 1 **1,200 t**; Block 2 **1,500 t ≈ 1,170 t LOX + 330 t CH4** (+25% per official Flight 7 text). [S5][S13]; high.
- **Header tanks:** LOX header **forms the tip of the nosecone**; CH4 header at/near the common dome on Block 1, described as **attached directly below the nose LOX header** in the Block 2 configuration — model both-in-nose for V2, medium confidence. [S5][S33]; medium.
- **Payload bay:** Block 2 bay shortened from 5 barrel rings to 3 (~5.5 m); volume **614 m³** (Block 2) vs 1,100 m³ (2020 Users Guide V1-concept). [S5][S29][S34][S35]; medium.
- Ship feedlines: CH4 downcomer through the LOX tank; Block 2 added vacuum-jacketed feedlines and a new RVac fuel feedline system (official text). [S13]; high (existence).

---

## 4. Exterior features

### Grid fins (booster)
- **V1/V2: 4 stainless-steel, electrically actuated grid fins, ~3 t each**, near the top of the booster just below the vented interstage; remain extended during ascent. [S4] WIKI-IDX, high. Size: ≈ **5 m wide × 2.5 m tall** (explainer estimate). [S15][S16] EXPLAINER, medium-low. Angular spacing approximately uniform (exact clocking vs catch-pin axis undocumented). COMMUNITY, low.
- **V3: 3 grid fins in a 90°/90°/180° "T" arrangement, ~50% larger**, mounted lower, doubling as lift/catch hardware. [S14][S15][S16][S11]; high (count), medium (dimensions).

### Hot-staging ring
- Introduced Flight 2: **1.8 m tall vented interstage, ~9 t**, internal dome shielding the booster forward dome. [S4][S28]; high.
- From Flight 4 onward the ring is **jettisoned after boostback shutdown**; modeled attached. [S4][S42]; high.
- V3: no separate ring (integrated). [S14]; high.

### Booster raceways, chines, COPVs
- **Four aerodynamic chines** on the aft LOX tank from B7 onward, housing batteries, **COPVs for engine spin-start, and CO2 fire-suppression tanks**. [S4] WIKI-IDX, high. External raceway routing not documented — modeled schematically. COMMUNITY, low.

### Ship flaps
- **4 flaps: 2 forward (nosecone) + 2 aft.** [S5] WIKI-IDX, high.
- **Block 2 forward flaps: smaller, shifted toward the tip, moved leeward** to ≈ **140° included angle** between the pair (vs 180° on Block 1 and on the aft flaps). Official rationale: cut reentry heating on hinges, simplify mechanisms, stop pitch-up tendency. [S5][S13]; high.
- Aft flaps: geometry essentially carried over in Block 2. [S29][S10] EXPLAINER, medium.

### Thermal protection
- **≈18,000 black hexagonal ceramic tiles** on the **windward side**, rated ~**1,400 °C**. [S5] WIKI-IDX, high.
- Block 2: latest-generation tiles plus an **ablative backup layer** underneath (official Flight 7 text). [S13]; high.

### Nosecone and payload door
- Conical nosecone with heavy internal reinforcement at the forward-flap roots; LOX header in tip. [S5][S10]; medium-high.
- **"Pez-dispenser" slot-style leeward payload door**: first in-space deployment Flight 10 (8 Starlink simulators); Flight 12 deployed 22. [S9][S25][S8]; high.

---

## 5. Mass / performance (annotation only)

| Quantity | V1 | V2 | V3 | Source / confidence |
|---|---|---|---|---|
| Liftoff thrust | 7,590 tf (33 × 230 tf) ≈ 74.4 MN | 74–81 MN reported range | 8,250 tf initial; 9,240 tf target | [S3][S6][S14][S31]; high (V1), medium (V2/V3) |
| Ship thrust | 12.25 MN | ~14.4–15.7 MN | ~15.4 MN | [S3][S6]; medium |
| Stack liftoff mass | ~5,000 t | ~5,300 t | not published | [S3][S39]; medium |
| Payload to LEO (reusable) | 100–150 t design; ~15 t demonstrated-era | ~35 t (per-block table) | ~100 t claimed | [S1 via S3][S31][S32]; medium |
| FAA-documented residuals | — | up to ~101 t (ship) / ~74 t (booster) at landing | — | [S21] REG; high |

---

## 6. Key public imagery

- SpaceX Flickr photostream: https://www.flickr.com/photos/spacex/ [S22] OFFICIAL
- "Starship and Super Heavy Stack": https://www.flickr.com/photos/spacex/51369631902 [S23] OFFICIAL
- SpaceX on X (@SpaceX) flight galleries: https://x.com/spacex OFFICIAL
- SpaceX official cutaway diagrams (indexed): https://futurism.com/the-byte/spacex-diagrams-starship-super-heavy [S45]
- Booster underside, 33 engines (SpaceX photo, republished): https://www.space.com/space-exploration/private-spaceflight/33-hungry-spacex-raptors-from-below-space-photo-of-the-day-for-sept-1-2025 [S26]
- Wikimedia Commons: https://commons.wikimedia.org/wiki/Category:SpaceX_Starship and https://commons.wikimedia.org/wiki/File:SpaceX_Starship_Booster_Back_at_its_Perch_IFT-5.jpg [S24]
- V3 grid fins: https://www.teslaoracle.com/2025/08/16/spacex-reveals-grid-fins-of-the-next-gen-starship-super-heavy-booster/ [S15]
- Everyday Astronaut Flight 5 (annotated): https://everydayastronaut.com/starship-super-heavy-flight-5/ [S28]

---

## 7. Known unknowns (NOT public — modeled only as schematic placeholders)

- Tank wall construction: ring/stringer layout details, weld lands, wall thicknesses.
- Exact engine mount geometry: ring pitch radii, engine clocking, thrust-structure internals, hold-down interfaces.
- Feedline/manifold routing: downcomer diameter/route, LOX sump geometry, valve/manifold layout, autogenous pressurization plumbing.
- Header-tank exact volumes and internal mounting.
- Flap actuation internals, hinge seal design.
- TPS attachment system, underlayment, tile thickness map, per-region tile counts.
- Grid-fin actuator internals and exact fin airfoil/lattice dimensions.
- Avionics locations, battery/COPV sizes, raceway contents.
- Hot-stage ring internal dome/vent structure.
- Catch-pin dimensions and load paths.
- Payload door mechanism internals.
- Exact V3 as-flown masses and Raptor 3 flight thrust setting.

---

## Modeling assumptions summary (pinned V2 configuration)

- Stack: 9.00 m OD; booster body 69.2 m + 1.8 m vented hot-stage ring = 71 m; ship 52.1 m; total 123.1 m.
- Booster: aft LOX + forward CH4 over common dome; 4 chines on aft tank; 4 grid fins (~5 × 2.5 m est.) below interstage; 33 engines — 3 (gimbal) r≈0.95 m / 10 (gimbal) r≈2.3 m / 20 (fixed) r≈3.82 m (all radii photogrammetric estimates, LOW).
- Ship: aft LOX + forward CH4 main tanks; nose LOX header with CH4 header below it; 3-ring payload bay (~614 m³) with leeward door (not modeled open); 2 forward flaps at ~140° leeward included angle near tip; 2 aft flaps at 180°; windward hex-tile TPS field; 3 gimbaling SL Raptors center + 3 fixed RVacs (exit Ø ≈ 2.15 m modeled from ε=80 derivation; announced 2.4 m figure noted) at 120°.
- Packing note: 20 outer engines × the published 1.3 m engine diameter cannot pack at the photographed outer-ring radius without ~0.1 m lip contact — the published diameter is the powerhead envelope; the real bell exit is likely ≤1.22 m. The model keeps the published figure and accepts minor lip contact, documented in DIMENSIONS.md.

---

## Sources

Fetched directly:
- [S1] https://www.spacex.com/vehicles/starship/ — OFFICIAL (JS shell; figures via indexes)
- [S2] https://www.spacex.com/updates/starship-v3 — OFFICIAL (JS shell)
- [S3] https://en.wikipedia.org/wiki/SpaceX_Starship — WIKI-IDX
- [S4] https://en.wikipedia.org/wiki/SpaceX_Super_Heavy — WIKI-IDX
- [S5] https://en.wikipedia.org/wiki/SpaceX_Starship_(spacecraft) — WIKI-IDX
- [S6] https://en.wikipedia.org/wiki/SpaceX_Raptor — WIKI-IDX
- [S7] https://en.wikipedia.org/wiki/List_of_Starship_launches — WIKI-IDX
- [S8] https://en.wikipedia.org/wiki/Starship_flight_test_12 — WIKI-IDX
- [S10] https://ringwatchers.com/article/v2-ship-june-2024 — EXPLAINER
- [S13] https://www.leonarddavid.com/spacex-starship-flight-7-features-significant-upgrades/ — OFFICIAL-via-secondary
- [S14] https://www.teslarati.com/spacex-unveils-sweeping-starship-v3-upgrades-ahead-may-19-launch/ — OFFICIAL-via-secondary
- [S27] https://everydayastronaut.com/spacex-raptor-engine-comparison/ — EXPLAINER

From search results (titles/snippets verified in-search):
- [S9] https://en.wikipedia.org/wiki/Starship_flight_test_10 — WIKI-IDX
- [S11] https://ringwatchers.com/article/booster-grid-fins — EXPLAINER
- [S12] https://ringwatchers.com/article/prop-dist-29v33 — EXPLAINER
- [S15] https://www.teslaoracle.com/2025/08/16/spacex-reveals-grid-fins-of-the-next-gen-starship-super-heavy-booster/ — EXPLAINER
- [S16] https://www.nextbigfuture.com/2025/08/spacex-starship-has-built-new-grid-fins-for-the-super-heavy-booster.html — EXPLAINER
- [S17] https://www.nasaspaceflight.com/2026/05/starship-flight-12-block-3-pad-2/ — EXPLAINER
- [S18] https://www.nasaspaceflight.com/2025/01/starship-flight-7-block-2/ — EXPLAINER
- [S19] https://spaceflightnow.com/2026/05/12/spacex-targets-may-19-for-debut-of-starship-super-heavy-version-3-launch-pad-2/ — EXPLAINER
- [S20] https://www.faa.gov/space/stakeholder_engagement/spacex_starship — REG
- [S21] https://www.faa.gov/media/94346 — REG (Final Tiered EA)
- [S22] https://www.flickr.com/photos/spacex/ — OFFICIAL
- [S23] https://www.flickr.com/photos/spacex/51369631902 — OFFICIAL
- [S24] https://commons.wikimedia.org/wiki/File:SpaceX_Starship_Booster_Back_at_its_Perch_IFT-5.jpg — WIKI-IDX
- [S25] https://www.satellitetoday.com/launch/2025/08/27/starships-payload-milestone-in-test-flight-gives-a-preview-of-v3-starlink-launches/ — EXPLAINER
- [S26] https://www.space.com/space-exploration/private-spaceflight/33-hungry-spacex-raptors-from-below-space-photo-of-the-day-for-sept-1-2025 — EXPLAINER (SpaceX photo)
- [S28] https://everydayastronaut.com/starship-super-heavy-flight-4/ and https://everydayastronaut.com/starship-super-heavy-flight-5/ — EXPLAINER
- [S29] https://www.theweeklyspaceman.com/articles/starship-flight-8-what-to-expect — EXPLAINER
- [S30] https://www.scientificamerican.com/article/spacex-launches-starship-v3-the-worlds-most-powerful-and-tallest-rocket-ever/ — EXPLAINER
- [S31] https://www.space.com/space-exploration/launches-spacecraft/the-worlds-biggest-rocket-how-spacexs-new-starship-v3-differs-from-its-predecessors — EXPLAINER
- [S32] https://orbitaltoday.com/2026/05/15/spacex-starship-v3-differences-from-v1-v2/ — EXPLAINER
- [S33] https://starship-spacex.fandom.com/wiki/Starship_Lexicon — COMMUNITY
- [S34] https://spacex.relayto.com/e/starship-users-guide-37uiuuepbks0x — OFFICIAL (Users Guide mirror)
- [S35] https://www.eoportal.org/other-space-activities/starship-of-spacex — EXPLAINER
- [S36] https://spaceflightnow.com/2025/01/04/spacex-to-attempt-first-payload-deployment-engine-reuse-during-starship-flight-7/ — EXPLAINER
- [S37] https://keeptrack.space/x-report/spacex-brief-2026-05-28 — EXPLAINER (FAA grounding)
- [S38] https://www.cnn.com/2026/05/21/science/live-news/spacex-starship-flight-12-version-3-launch — EXPLAINER
- [S39] https://tesorb.com/starship-v3-upgrades-explained/ — EXPLAINER
- [S40] https://space.skyrocket.de/doc_lau/super-heavy-starship.htm — WIKI-IDX (Gunter's)
- [S41] https://www.space.com/news/live/spacex-starship-missions-updates — EXPLAINER
- [S42] https://en.wikipedia.org/wiki/Starship_flight_test_8 and https://en.wikipedia.org/wiki/Starship_flight_test_4 — WIKI-IDX
- [S43] https://en.m.wikipedia.org/wiki/Starship_flight_test_9 — WIKI-IDX
- [S44] https://starship-spacex.fandom.com/wiki/Super_Heavy_Booster — COMMUNITY
- [S45] https://futurism.com/the-byte/spacex-diagrams-starship-super-heavy — EXPLAINER (indexes official diagrams)
