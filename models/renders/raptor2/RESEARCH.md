# SpaceX Raptor Engine — Public-Source Research Dossier

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

**Subject:** SpaceX Raptor full-flow staged-combustion methalox engine (Starship/Super Heavy). **Default modeling subject: Raptor 2, sea-level variant.**
**Purpose:** Educational, non-functional CAD reconstruction from public sources only.
**Compiled:** 2026-07-01. All facts carry: value → source URL(s) → source type → confidence.

**Source-type key:** `OFFICIAL` = SpaceX / Musk statements · `REG` = regulatory (FAA/NASA) · `EXPLAINER` = reputable explainer (Everyday Astronaut, NASASpaceflight) · `WIKI-IDX` = Wikipedia used as an index to primary refs · `COMMUNITY` = community/photogrammetric estimate.

**Method note:** `spacex.com/vehicles/starship/` was fetched but serves a JavaScript-only shell (no extractable text); its figures are cited here via the Wikipedia index and the Internet Archive capture of the older SpaceX Starship page. The two SpaceX X posts of 3 Aug 2024 and the Musk X posts were not directly fetchable (X login wall) but their URLs and full quoted text surfaced verbatim in search results and are corroborated by NextBigFuture, NASASpaceflight, SlashGear, and EONMSK coverage.

---

## 1. Overall Dimensions and Mass

### 1.1 Engine height / length

| Value | Source | Type | Confidence |
|---|---|---|---|
| **3.1 m (10 ft)** length, Raptor family (sea-level) | Archived SpaceX Starship page: https://web.archive.org/web/20190930163150/https://www.spacex.com/starship (via Wikipedia ref: https://en.wikipedia.org/wiki/SpaceX_Raptor) | OFFICIAL (archived) via WIKI-IDX | **High** for Raptor 1-era; **Medium** as applied to Raptor 2/3 (SpaceX has not re-published per-variant height) |
| "~13 ft (4 m) tall" appears in some secondary summaries | e.g. secondary aggregator sites surfaced in search | COMMUNITY/secondary | **Low** — likely includes mounting hardware or is an error; prefer 3.1 m |

> **Correction to briefing assumption:** the briefing stated SpaceX published Raptor 3 height 3.1 m / diameter 1.3 m in the Aug 2024 X posts. The verified text of those posts (thrust, Isp, engine mass, engine + commodities mass — see §1.4) does **not** contain height/diameter. The 3.1 m / 1.3 m figures trace instead to the archived spacex.com Starship page (length) and Musk's 2017 IAC presentation (diameter). Treat 3.1 m × 1.3 m for Raptor 3 as *inferred family-level*, not variant-specific.

### 1.2 Nozzle exit / envelope diameter

| Value | Source | Type | Confidence |
|---|---|---|---|
| **1.3 m (4 ft 3 in)** diameter, sea-level Raptor | Musk, "Making Life Multiplanetary" IAC 2017 presentation: https://www.youtube.com/watch?v=tdUX3ypDVwI&t=22m34s (via Wikipedia ref) | OFFICIAL via WIKI-IDX | **High** (Raptor 1 design intent); **Medium** for Raptor 2 |
| Raptor 1 and Raptor 2 have the **same nozzle exit diameter** (throat widened instead) | Everyday Astronaut, "Raptor 1 vs Raptor 2: What did SpaceX change?": https://everydayastronaut.com/spacex-raptor-engine-comparison/ | EXPLAINER | **High** |
| Overall envelope width ≈ nozzle exit Ø plus flanking turbopump assemblies; ~1.3 m quoted as the governing diameter | Same sources as above; photo interpretation | COMMUNITY (photo-derived) | **Medium** |

### 1.3 Dry mass (engine only, sea-level variants) — OFFICIAL SpaceX figures

Source: SpaceX X posts, 3 Aug 2024 —
Raptor 3 specs: https://x.com/SpaceX/status/1819772716339339664
Raptor 1/2 stats: https://x.com/SpaceX/status/1819795288116330594
Corroboration: https://www.nextbigfuture.com/2024/08/spacex-reveals-raptor-3-engine-and-specifications.html · https://www.eonmsk.com/2024/08/03/spacex-raptor-1-vs-raptor-2-vs-raptor-3/ · https://www.slashgear.com/1658725/space-x-raptor-3-engine-details-everything-we-know/

| Variant | Engine mass | Engine + vehicle-side commodities & hardware | Type | Confidence |
|---|---|---|---|---|
| Raptor 1 | **2,080 kg** | **3,630 kg** | OFFICIAL | **High** |
| Raptor 2 | **1,630 kg** | **2,875 kg** | OFFICIAL | **High** |
| Raptor 3 | **1,525 kg** | **1,720 kg** | OFFICIAL | **High** |

SpaceX framing (per the same posts, quoted by NextBigFuture): Raptor 3 is 36% lighter / +51% thrust vs Raptor 1; 7% lighter / +21% thrust vs Raptor 2.

### 1.4 Thrust (sea-level variants) — OFFICIAL

| Variant | SL thrust | Source | Confidence |
|---|---|---|---|
| Raptor 1 | **185 tf** (1.81 MN) | SpaceX X post 1819795288116330594 (above); NASASpaceflight: https://www.nasaspaceflight.com/2022/01/raptor-2-starbase-update/ | **High** |
| Raptor 2 | **230 tf** (2.26 MN) SL; 258 tf vac (per spacex.com via Wikipedia) | SpaceX X post 1819795288116330594; Wikipedia index: https://en.wikipedia.org/wiki/SpaceX_Raptor | **High** |
| Raptor 3 | **280 tf** at reveal (Aug 2024); Wikipedia (citing https://www.spacex.com/updates#starship-v3) lists 250 tf current-operational with 280–306 tf targets | SpaceX X post 1819772716339339664; WIKI-IDX | **High** (280 tf demonstrated); **Medium** (operational rating) |

---

## 2. Nozzle Geometry and Performance (public/estimated)

### 2.1 Expansion (area) ratio

| Value | Source | Type | Confidence |
|---|---|---|---|
| **ε = 34.34** (sea-level Raptor) | FAA Appendix G, Exhaust Plume Calculations (Sierra Engineering & Software, 2019), submitted for SpaceX environmental review: https://www.faa.gov/space/stakeholder_engagement/spacex_starship/media/Appendix_G_Exhaust_Plume_Calculations.pdf (via Wikipedia refs) | **REG** | **High** for the ~2019 (Raptor 1-era) configuration; **Medium** for Raptor 2 |
| ε = 36 used to match a 1,300 mm exit in an independent CFD reconstruction of Raptor 2 | ResearchGate: https://www.researchgate.net/publication/394009342_Advanced_CFD_Simulation_of_Internal_Flow_Dynamics_in_the_Raptor_2_Combustion_Chamber_and_Nozzle_by_YAZIDI_Hamza | COMMUNITY | **Low** |
| ε = 40 assumed in a 2019 reverse-engineering study | ExRocketMan blog: https://exrocketman.blogspot.com/2019/09/reverse-engineered-raptor-engine.html | COMMUNITY | **Low** |
| ε ≈ 80 (Raptor Vacuum) | Musk in Everyday Astronaut Starbase tour interview: https://www.youtube.com/watch?v=SA8ZBJWo73E (via Wikipedia ref) | OFFICIAL via WIKI-IDX | **Medium** |

**Working value for CAD: ε ≈ 34–40, best single value 34.34 (FAA).**

### 2.2 Throat diameter — NO official figure exists; estimates only

| Value | Basis | Source | Type | Confidence |
|---|---|---|---|---|
| **218.6 mm** (8.604 in) | Reverse-engineered ballistics, ε=40, Pc=4,400 psia (~303 bar), 440 klbf SL | https://exrocketman.blogspot.com/2019/09/reverse-engineered-raptor-engine.html | COMMUNITY | **Low** |
| **~217 mm** | ε=36 with 1,300 mm exit (CFD study geometry) | ResearchGate CFD study (URL above) | COMMUNITY | **Low** |
| **~222 mm** | Arithmetic: 1,300 mm exit ÷ √34.34 (FAA ε + SpaceX exit Ø) | Derived in this dossier from REG + OFFICIAL inputs | COMMUNITY (derived) | **Low** |
| **~235–250 mm** | Derived from F = Cf·Pc·At with 230 tf, 300 bar, Cf ≈ 1.6–1.75 (Raptor 2, widened throat) | Derived in this dossier; consistent with EA statement that Raptor 2 "widened the throat" at constant exit Ø (https://everydayastronaut.com/spacex-raptor-engine-comparison/) | COMMUNITY (derived) | **Low** |

> Public estimates cluster at **~215–225 mm for Raptor 1** and **~235–250 mm for Raptor 2** (throat opened, exit unchanged, so effective ε dropped below 34). Ongoing community discussion: NASASpaceflight forum Raptor thread, https://forum.nasaspaceflight.com/index.php?topic=53555.560. All values LOW confidence — the CAD model uses **240 mm** for the Raptor 2 schematic and labels it an estimate.

### 2.3 Chamber pressure

| Variant | Value | Source | Type | Confidence |
|---|---|---|---|---|
| Raptor 1 | **250 bar** operational (330 bar demonstrated in tests per Musk statements) | Musk IAC 2017 (https://www.youtube.com/watch?v=tdUX3ypDVwI) via WIKI-IDX; EA comparison article | OFFICIAL via WIKI-IDX / EXPLAINER | **High** |
| Raptor 2 | **300 bar** ("highest of any rocket engine") | EA comparison: https://everydayastronaut.com/spacex-raptor-engine-comparison/; EA video cited by Wikipedia: https://www.youtube.com/watch?v=E7MQb9Y4FAE; Wikipedia infobox | OFFICIAL (Musk statements) via EXPLAINER/WIKI-IDX | **High** |
| Raptor 3 | **350 bar** achieved in test, May 2023 ("Raptor V3 just achieved 350 bar chamber pressure (269 tons of thrust)"): https://x.com/elonmusk/status/1657249739925258240; Wikipedia infobox lists **330 bar** operational | OFFICIAL / WIKI-IDX | **High** (350 bar test); **Medium** (330 bar operational) |

### 2.4 Specific impulse

| Variant | SL Isp | Vac Isp | Sources | Confidence |
|---|---|---|---|---|
| Raptor 1 | ~327–334 s (estimates/Musk presentation) | **350 s** (SpaceX X post) | https://x.com/SpaceX/status/1819795288116330594; Wikipedia index; ExRocketMan estimate 334.4 s SL / 360.4 s vac | **Medium** — see note |
| Raptor 2 | ~327 s (Wikipedia, from Musk presentation) | **347 s** (SpaceX X post); RVac variant ~380 s (spacex.com via Wikipedia) | Same as above | **Medium** |
| Raptor 3 | — | **350 s** (SpaceX X post) | https://x.com/SpaceX/status/1819772716339339664 | **High** (as stated) |

> **Note/dispute:** SpaceX's Aug 2024 posts give unqualified "specific impulse" (350/347/350 s) for the sea-level variants — almost certainly **vacuum Isp of the SL-nozzle engine**. Sea-level-ambient Isp is ~327–334 s per Musk presentation figures (via Wikipedia) and independent analysis (ExRocketMan). The ExRocketMan study explicitly argues 330 s SL and 380 s vac "cannot both apply to the same engine configuration" — the 380 s figure belongs to the ε≈80 Raptor Vacuum. Model annotation should use: SL variant ≈ 327 s SL / ~347–350 s vac.

### 2.5 Other flow parameters (for schematic annotation)

| Parameter | Value | Source | Type | Confidence |
|---|---|---|---|---|
| Propellants | Liquid CH₄ / LOX (subcooled) | All sources | OFFICIAL | High |
| Mixture ratio | **3.6 (≈78% O₂ / 22% CH₄ by mass)** | FAA Appendix G + FAA Draft PEA: https://www.faa.gov/space/stakeholder_engagement/spacex_starship/media/Draft_PEA_for_SpaceX_Starship_Super_Heavy_at_Boca_Chica.pdf (via Wikipedia refs) | **REG** | **High** |
| Total mass flow | ~650 kg/s (≈510 kg/s O₂ + ≈140 kg/s CH₄) | Wikipedia (calculated from FAA-cited thrust/Isp) | WIKI-IDX | Medium |
| Throttle range | ~40–100% | Musk: https://twitter.com/elonmusk/status/1295553672454311941 (via Wikipedia ref) | OFFICIAL | High |
| Gimbal range | 15° (Y and Z axes), unchanged Raptor 1→2 | EA comparison article | EXPLAINER | Medium |
| Engines per vehicle | Super Heavy: **33 Raptors** ("total thrust of 8877 tons") | https://x.com/elonmusk/status/1657249739925258240 | OFFICIAL | High |

---

## 3. Exterior Architecture (from public photos — qualitative)

All statements in this section are photo/schematic interpretation unless noted: **COMMUNITY (photogrammetric), Low–Medium confidence**, suitable for a schematic-fidelity CAD exterior only.

**Reference imagery (verified URLs):**
- SpaceX official Flickr, Raptor test firing (McGregor, Sept 2016): https://www.flickr.com/photos/spacex/29916104756
- Wikimedia Commons category (19 files): https://commons.wikimedia.org/wiki/Category:Raptor_(rocket_engine) — key files: `SpaceX_sea-level_Raptor_at_Hawthorne_-_2.jpg` (Raptor 1 on display), `SpaceX_Merlin_and_sea-level_Raptor_at_Hawthorne.jpg` (scale vs Merlin), `A_person_viewing_Raptor_Vacuum.jpg` (RVac, human scale), `Raptor_test_firing,_2015-09-25.jpg`, `Raptor-test-9-25-2016.jpg`, `SpaceX's_Raptor_oxygen_preburner_testing_at_Stennis_(2015).jpg`, plus community cycle diagrams `Raptor_2_Full_Flow_Staged_Combustion_Cycle_Estimate.svg` and `Raptor_Engine_Unofficial_Combustion_Scheme.svg`
- SpaceX X posts of 3 Aug 2024 (URLs in §1.3) include official side-by-side photos of Raptor 1 vs 2 vs 3
- EA comparison article (side-by-side render + annotated figures): https://everydayastronaut.com/spacex-raptor-engine-comparison/
- NASASpaceflight Raptor 3 reveal article (photos): https://www.nasaspaceflight.com/2024/08/flight-5-6-preparations-raptor-3/ · Raptor 3 at McGregor (2025): https://www.nasaspaceflight.com/2025/08/raptor-3-ramps-spacex-mcgregor/ · Raptor lineage: https://www.nasaspaceflight.com/2016/10/its-propulsion-evolution-raptor-engine/

**Layout (twin-shaft FFSC, documented architecture — Medium-High confidence for topology, Low for exact positions):**
- Wikipedia (index) describes "a twin-shaft staged combustion cycle that uses both oxidizer-rich and fuel-rich preburners" — i.e., **two independent turbopump assemblies**, one per propellant. Public photos and community schematics consistently show the **oxidizer turbopump + ox-rich preburner stack on one side** of the thrust chamber and the **fuel (CH₄) turbopump + fuel-rich preburner stack on the opposite side**, each feeding down into the main injector head. (WIKI-IDX + COMMUNITY, Medium)
- **Gimbal mount at top:** engine hangs from a compact gimbal block above the injector dome; thrust-vector-control actuator attach points flank the powerhead. Gimbal authority 15° per EA. (EXPLAINER + photo interpretation, Medium)
- **Main propellant valves** sit high on the powerhead where vehicle-side LOX/CH₄ feedlines meet the pump inlets; in Raptor 2, "many valves were combined into valve plates" (EA, direct quote), so model valve plates rather than discrete valve bodies. (EXPLAINER, Medium)
- **Regen-cooled bell:** visible fine axial channel texture / brazed jacket on chamber and nozzle exterior; nozzle is a fixed bell (no extendable skirt) on SL variant. (photo interpretation, Medium)

**Raptor 1 → Raptor 2 visual delta** (EA comparison article, direct quotes; EXPLAINER, High):
- Raptor 1 has a "Christmas tree" look — dense external sensor harnesses and plumbing; Raptor 2 "looks borderline incomplete — a large amount of plumbing and sensors have been removed."
- Development pressure/temperature sensors deleted; valves consolidated into valve plates; torch igniters in the main chamber eliminated (preburner gases ignite the main chamber "hypergolically" under temperature/pressure); far fewer flanges (welded joints instead).
- CAD note: Raptor 1 carried externally visible controller/electronics boxes; Raptor 2 presents a much cleaner powerhead with integrated shielding, consistent with EA's note that de-cluttering made the engine "more flame and heat proof: a clear step toward SpaceX's goal of removing all engine shrouding from the booster."

**Raptor 2 → Raptor 3 visual delta** (NASASpaceflight reveal coverage + secondary reports; EXPLAINER, Medium-High):
- Raptor 3 is almost entirely **smooth**: "much of the external plumbing moved internally or removed altogether, with a lot of the internal plumbing consisting of regenerative cooling channels built into the engine's case" (NSF, via search-indexed text).
- "All the small plumbing and wiring had to be either deleted or incorporated into the primary structure... regenerative cooling was added where there was no existing fluid or gas flow"; consequently Raptor 3 **needs no engine heat shield and no fire-suppression system** (NSF; also https://wallstreetpit.com/119380-no-shield-no-problem-musk-unveils-raptor-3s-game-changing-design/, https://www.teslaoracle.com/2024/08/08/raptor-3-starship-engine-is-lighter-less-complicated-but-more-powerful-and-reusable/). Enabled partly by additive manufacturing (https://www.voxelmatters.com/elon-musk-confirms-new-raptor-3-optimization-was-made-possible-by-am/).

---

## 4. Functional Flow — Full-Flow Staged Combustion (schematic level)

Textbook-level description for color-coded flow paths; sources: Everyday Astronaut "Is SpaceX's Raptor engine the king of rocket engines?" (https://everydayastronaut.com/raptor-engine/), EA Rocket Engine Cycles (https://everydayastronaut.com/rocket-engine-cycles/), Wikipedia index, Techsight animated schematic (https://techsight.co/index.php/2021/06/24/raptor-rocket-engine-animated-schematic-infographic/). Type: EXPLAINER/WIKI-IDX. Confidence: **High** (cycle topology is publicly established); no proprietary detail included.

**LOX path:** vehicle LOX main valve → LOX turbopump → majority flow to **oxygen-rich preburner** (burned with a small CH₄ bleed) → hot O₂-rich gas drives the **LOX-side turbine** → ALL of it continues as warm gaseous oxidizer into the **main injector**.

**CH₄ path:** vehicle CH₄ main valve → fuel turbopump → split: (a) **regenerative cooling** — "sending the cryogenic methane around the outside of the main combustion chamber to keep it cool" and through "cooling channels milled into" the nozzle walls, after which "the warmed liquid methane then flows to the preburner" (Techsight, direct quotes); (b) flow to the **fuel-rich preburner** (burned with a small LOX bleed) → hot CH₄-rich gas drives the **fuel-side turbine** → ALL of it continues as warm gaseous fuel into the main injector.

**Defining FFSC properties (EA/Wikipedia):** *all* propellant passes through a preburner and turbine — nothing is dumped overboard; both propellants arrive at the chamber **gas-gas** ("since both the fuel and oxidizer arrive in the combustion chamber as a hot gas, there's better combustion" — EA), enabling a smaller/lighter chamber; preburner temperatures are lower than single-preburner staged combustion for the same power, aiding reuse; no interpropellant turbine seal problem ("less need of that crazy sealing system" — EA). Ox-rich hot section requires SpaceX's in-house **SX500 superalloy**, "capable of over 800 bar of hot oxygen-rich gas" (EA quoting Musk). Ignition: spark-torch on Raptor 1; Raptor 2 deleted the main-chamber torch igniters (EA).

**Film cooling:** frequently asserted in community schematics for the chamber wall/throat region, but **not explicitly confirmed** in any source fetched for this dossier — treat as COMMUNITY, **Low** confidence; render as optional/annotated-uncertain in the flow diagram.

---

## 5. Variant Comparison Table (sea-level variants)

Primary sources: SpaceX X posts (S1 = https://x.com/SpaceX/status/1819772716339339664, S2 = https://x.com/SpaceX/status/1819795288116330594), Musk X post (M1 = https://x.com/elonmusk/status/1657249739925258240), Wikipedia index (W = https://en.wikipedia.org/wiki/SpaceX_Raptor), EA comparison (EA = https://everydayastronaut.com/spacex-raptor-engine-comparison/), NSF reveal (N = https://www.nasaspaceflight.com/2024/08/flight-5-6-preparations-raptor-3/).

| Parameter | Raptor 1 | Raptor 2 | Raptor 3 |
|---|---|---|---|
| SL thrust | **185 tf** [S2, official, High] | **230 tf** [S2, official, High] | **280 tf** at reveal [S1, official, High]; 250 tf operational / 280–306 tf target [W→spacex.com/updates, Medium] |
| Specific impulse (as posted by SpaceX; ≈vac of SL variant) | 350 s [S2, High] | 347 s [S2, High] | 350 s [S1, High] |
| SL-ambient Isp | ~327–334 s [W (Musk pres.) + ExRocketMan, Medium/Low] | ~327 s [W, Medium] | not published |
| Engine mass | 2,080 kg [S2, High] | 1,630 kg [S2, High] | 1,525 kg [S1, High] |
| Engine + commodities | 3,630 kg [S2, High] | 2,875 kg [S2, High] | 1,720 kg [S1, High] |
| Chamber pressure | 250 bar [W (IAC 2017)/EA, High] | 300 bar [EA/W, High] | 330 bar oper. [W, Medium]; 350 bar tested [M1, High] |
| Height | 3.1 m [W→archived spacex.com, High for R1] | ~3.1 m (family, inferred) [Medium] | not separately published [Low] |
| Diameter (nozzle exit) | 1.3 m [W→Musk IAC 2017, High] | same exit as R1 [EA, High] | not separately published; visually similar [Low] |
| T/W | ~89 [W calc, Medium] | ~141 [W calc, Medium] | ~164–187 [W calc, Medium] |
| Visual character | "Christmas tree" — dense external plumbing, dev sensors, external controller boxes, torch igniters, many flanges [EA, High] | Much cleaner: sensors deleted, valve plates, no chamber torch igniters, fewer flanges, integrated shielding [EA, High] | Nearly smooth: plumbing internalized into regen-cooled case, no heat shield, no fire-suppression, welded monolith look, AM-enabled [N + secondaries, Medium-High] |

---

## 6. Known Unknowns — excluded or schematic-only in the CAD model

Not publicly disclosed by SpaceX; nothing reliable exists even at estimate level:

1. **Main injector design** — element type (community assumes gas-gas coaxial swirl), element count, pattern, dome internals.
2. **Turbopump internals** — impeller/inducer geometry, shaft speeds, bearing and seal arrangements, turbine blade design.
3. **Preburner internals** — injector elements, mixture ratios per preburner, ignition hardware details.
4. **Wall thicknesses** — chamber liner, jacket, nozzle, all structural members.
5. **Regen cooling channel geometry** — channel count, cross-sections, routing, manifold internals.
6. **Valve internals** — valve-plate porting, actuation mechanisms, sequencing.
7. **Materials specifics** — SX500 composition/processing; which parts are printed vs cast vs machined.
8. **Film-cooling arrangement** (existence widely assumed, geometry unknown).
9. **Exact throat diameter and internal nozzle contour** (bell parameters, contraction ratio) — model from the ε and exit-Ø estimates in §2 only.
10. **Engine controller/avionics** — architecture, sensor suite, harness routing (Raptor 3 hides these entirely).
11. **Raptor 3 per-variant dimensions and vacuum-variant specifics** beyond thrust/mass/Isp posts.

**CAD policy:** exterior form from public photos (schematic fidelity); internals only as color-coded FFSC flow schematic per §4; every §2 nozzle number labeled "public estimate."

---

## Sources

**Official SpaceX / Musk (X posts; text verified via search index and secondary coverage):**
- https://x.com/SpaceX/status/1819772716339339664 — Raptor 3 specs (280 tf / 350 s / 1,525 kg / 1,720 kg), 3 Aug 2024
- https://x.com/SpaceX/status/1819795288116330594 — Raptor 1 & 2 stats (185 tf/2,080 kg/3,630 kg; 230 tf/1,630 kg/2,875 kg), 3 Aug 2024
- https://x.com/elonmusk/status/1657249739925258240 — Raptor V3 350 bar / 269 tf; 33 Raptors on Super Heavy, May 2023
- https://twitter.com/elonmusk/status/1295553672454311941 — throttle capability (via Wikipedia ref)
- https://web.archive.org/web/20190930163150/https://www.spacex.com/starship — archived SpaceX Starship page (3.1 m length)
- https://www.spacex.com/vehicles/starship/ — fetched; JS-only shell, cited via Wikipedia index
- https://www.spacex.com/updates#starship-v3 — Raptor 3 thrust figures (via Wikipedia ref)
- https://www.youtube.com/watch?v=tdUX3ypDVwI&t=22m34s — Musk IAC 2017 (1.3 m diameter, 250 bar)
- https://www.youtube.com/watch?v=SA8ZBJWo73E — Musk/EA Starbase tour (RVac ε≈80)
- https://www.flickr.com/photos/spacex/29916104756 — SpaceX Flickr, Raptor test firing 2016

**Regulatory (FAA):**
- https://www.faa.gov/space/stakeholder_engagement/spacex_starship/media/Appendix_G_Exhaust_Plume_Calculations.pdf — ε=34.34, MR 3.6
- https://www.faa.gov/space/stakeholder_engagement/spacex_starship/media/Draft_PEA_for_SpaceX_Starship_Super_Heavy_at_Boca_Chica.pdf — propellant/mixture data

**Reputable explainers:**
- https://everydayastronaut.com/raptor-engine/ — "Is SpaceX's Raptor engine the king of rocket engines?" (FFSC cycle, SX500)
- https://everydayastronaut.com/spacex-raptor-engine-comparison/ — Raptor 1 vs 2 changes
- https://everydayastronaut.com/rocket-engine-cycles/ — cycle background
- https://www.youtube.com/watch?v=ALiNmzoo1_E and https://www.youtube.com/watch?v=E7MQb9Y4FAE — EA videos (via Wikipedia refs)
- https://www.nasaspaceflight.com/2024/08/flight-5-6-preparations-raptor-3/ — Raptor 3 reveal (direct fetch 403; content via search index)
- https://www.nasaspaceflight.com/2022/01/raptor-2-starbase-update/ — Raptor 1/2 thrust
- https://www.nasaspaceflight.com/2016/10/its-propulsion-evolution-raptor-engine/ — Raptor lineage
- https://www.nasaspaceflight.com/2025/08/raptor-3-ramps-spacex-mcgregor/ — Raptor 3 testing photos

**Wikipedia index + Commons:**
- https://en.wikipedia.org/wiki/SpaceX_Raptor — index; underlying refs extracted above
- https://commons.wikimedia.org/wiki/Category:Raptor_(rocket_engine) — 19 public images (filenames in §3)

**Community estimates / secondary:**
- https://exrocketman.blogspot.com/2019/09/reverse-engineered-raptor-engine.html — throat 218.6 mm, ε=40 study
- https://www.researchgate.net/publication/394009342_Advanced_CFD_Simulation_of_Internal_Flow_Dynamics_in_the_Raptor_2_Combustion_Chamber_and_Nozzle_by_YAZIDI_Hamza — ε=36 / 1,300 mm exit
- https://www.researchgate.net/publication/363367182_Preliminary_design_of_a_Raptor-like_engine — Raptor-like design study
- https://forum.nasaspaceflight.com/index.php?topic=53555.560 — NSF forum Raptor thread
- https://techsight.co/index.php/2021/06/24/raptor-rocket-engine-animated-schematic-infographic/ — animated FFSC schematic
- https://www.nextbigfuture.com/2024/08/spacex-reveals-raptor-3-engine-and-specifications.html — X-post transcription
- https://www.eonmsk.com/2024/08/03/spacex-raptor-1-vs-raptor-2-vs-raptor-3/ — side-by-side comparison
- https://www.slashgear.com/1658725/space-x-raptor-3-engine-details-everything-we-know/ — Raptor 3 summary
- https://www.teslaoracle.com/2024/08/08/raptor-3-starship-engine-is-lighter-less-complicated-but-more-powerful-and-reusable/ — Raptor 3 design coverage
- https://wallstreetpit.com/119380-no-shield-no-problem-musk-unveils-raptor-3s-game-changing-design/ — no-heat-shield coverage
- https://www.voxelmatters.com/elon-musk-confirms-new-raptor-3-optimization-was-made-possible-by-am/ — additive manufacturing note
- https://spaceexplored.com/2024/08/07/spacex-shows-off-new-iteration-of-its-starships-raptor-rocket-engine/ — Raptor 3 reveal coverage
- https://www.inverse.com/innovation/spacex-raptor-2-engine-specs — Raptor 2 specs coverage
