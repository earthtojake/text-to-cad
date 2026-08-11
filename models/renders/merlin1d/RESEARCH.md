# SpaceX Merlin 1D (Sea-Level) — Public-Source Research Dossier

> **Educational, non-functional public-source reconstruction. Not suitable for
> manufacture, propulsion, testing, or operational engineering.**

**Scope:** Merlin 1D sea-level engine as flown on Falcon 9 / Falcon Heavy Block 5 first stages ("Merlin 1D+", "M1D"). Compiled 2026-07-02 exclusively from public online sources. This dossier is for a non-functional, educational, exterior-plus-schematic CAD model. No proprietary data is included; anything not publicly stated is flagged as an estimate or listed under Known Unknowns.

**Source-type key:** `OFFICIAL` = SpaceX web/media · `SX-UG` = SpaceX Falcon User's Guide (rev. 2025-05-09 PDF, fetched and text-extracted) · `NASA` = NASA-hosted document · `MUSEUM` = museum collection record · `EXPLAINER` = reputable explainer (Everyday Astronaut, NASASpaceflight, Spaceflight Now, SpaceNews) · `WIKI` = Wikipedia used as an index to primary refs · `COMMUNITY` = forum/aggregator/photogrammetric estimate · `DERIVED` = arithmetic derived in this dossier from cited numbers (treat as estimate).

---

## 1. Overall Dimensions, Mass & Performance (current sea-level Merlin 1D, Block 5)

### 1.1 Dimensions & mass

| Fact | Value | Source(s) | Source type | Confidence |
|---|---|---|---|---|
| Engine length/height (M1D) | **No official figure published.** Widely circulated ~2.92 m (115 in) traces to the *Merlin 1C* length in the Wikipedia article, not a 1D-specific source | https://en.wikipedia.org/wiki/SpaceX_Merlin (lists "Length: 2.92 m" under Merlin 1C) | WIKI | **Low** (for applying 2.92 m to 1D) |
| Flown Merlin 1D envelope incl. museum display stand | 121.9 × 143.5 × 269.2 cm (4 ft × 4 ft 8½ in × 8 ft 10 in); 857.8 kg (1,891 lb) *with stand* — flown engine (Iridium-6 2018, SAOCOM 1A 2018, PSN VI 2019) | https://airandspace.si.edu/collection-objects/rocket-engine-liquid-fuel-merlin-1d/nasm_A20220606000 | MUSEUM (Smithsonian NASM) | **High** (as a measured display envelope; stand included, so bare-engine length ≤ ~2.7 m along that axis) |
| Engine/nozzle exit diameter (SL) | 0.92 m (3.0 ft) per Wikipedia infobox (uncited there); photo-scaling estimates 0.93–1.10 m | https://en.wikipedia.org/wiki/SpaceX_Merlin ; NSF forum photo-scaling discussions, e.g. https://forum.nasaspaceflight.com/index.php?topic=26388.160 | WIKI + COMMUNITY (photogrammetric) | **Low–Medium** (use ~0.92–0.95 m; officially unpublished) |
| Dry mass | 470 kg (1,030 lb) | https://en.wikipedia.org/wiki/SpaceX_Merlin, citing Tom Mueller (Merlin chief designer): https://www.quora.com/Is-SpaceXs-Merlin-1Ds-thrust-to-weight-ratio-of-150+-believable/answer/Thomas-Mueller-11 | WIKI-indexed; primary is Mueller (unofficial channel) | **Medium** |
| Mass (alt. aggregate) | "Gross mass 490 kg (1,080 lb)" | http://www.astronautix.com/m/merlin1d.html (via search snippets; site unreachable for direct fetch) | COMMUNITY (aggregator) | **Low** |

**CAD guidance:** anchor overall scale to the NASM display record and the ~0.92–0.95 m exit diameter; treat overall engine length ~2.5–2.9 m as a photogrammetric band, not a spec.

### 1.2 Thrust (current + uprating history)

| Fact | Value | Source(s) | Source type | Confidence |
|---|---|---|---|---|
| Current SL thrust per engine (Block 5) | **845 kN (190,000 lbf)** — "Each of the 27 first stage engines produces 845 kN (190,000 lbf) of thrust at sea level" | SpaceX Falcon User's Guide 2025-05-09: https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf | SX-UG (official) | **High** |
| Stage total (F9, SL) | Text: 7,605 kN (1,710,000 lbf); Table 2-1: **7,686 kN** (sea level) — table value ÷ 9 = **854 kN/engine**, the origin of "854 kN" seen in aggregators | Same User's Guide (both figures appear); 854 kN repeated at https://www.wevolver.com/specs/merlin-engine-merlin-1d-falcon-9-falcon-heavy and https://www.uc.edu/content/dam/refresh/cont-ed-62/olli/fall-23-class-handouts/SpaceX%204%20Falcon%20rockets%20and%20Engines.pdf | SX-UG + COMMUNITY echoes | **High** that both official figures exist; report thrust as **845–854 kN SL** |
| M1D vacuum thrust (first-stage engine) | ~914 kN (205,000 lbf) planned in May 2016 uprate; consistent with FH "thrust in vacuum 5,548,500 lbf" ÷ 27 = 205,500 lbf | https://en.wikipedia.org/wiki/SpaceX_Merlin ; UC OLLI handout (above) | WIKI + COMMUNITY, cross-checked | **Medium** |
| History — 2013 (F9 v1.1 debut) | 654 kN (147,000 lbf) SL → 716 kN (161,000 lbf) vac; flight-qualified Mar 2013 after 28 tests, 1,970 s | NASA CRS-6 press kit: https://www.nasa.gov/wp-content/uploads/2018/07/spacex_nasa_crs-6_presskit-2.pdf (p.18) ; https://spacenews.com/spacexs-merlin-1d-engine-achieves-flight-qualification/ ; https://www.nasaspaceflight.com/2013/03/falcon-9-boost-merlin-1d-engine-achieves-milestone/ | NASA + EXPLAINER | **High** |
| History — Nov 2013 Musk remark | Engine "operating at 85% of its potential"; anticipated ~730 kN (165,000 lbf) SL | https://en.wikipedia.org/wiki/SpaceX_Merlin citing http://forum.nasaspaceflight.com/index.php?topic=33335.msg1125118#msg1125118 | WIKI-indexed | **Medium** |
| History — Full Thrust era (2015–2017) | ~176,000 lbf (≈783 kN) per engine; Apr 2017 Musk: Block 5 = +7–8%, "from 176,000 lbf to 190,000 lbf" | https://en.wikipedia.org/wiki/Falcon_9_Block_5 ; https://en.wikipedia.org/wiki/Falcon_9_Full_Thrust | WIKI-indexed | **Medium–High** |
| History — Block 5 (May 2018) | 845 kN (190,000 lbf) goal achieved | https://en.wikipedia.org/wiki/SpaceX_Merlin citing https://twitter.com/SciGuySpace/status/994649495861432321 (Eric Berger, 2018-05-10) | WIKI-indexed / journalist | **High** |

### 1.3 Isp, chamber pressure, expansion ratio, throttle, T/W, propellants

| Fact | Value | Source(s) | Source type | Confidence |
|---|---|---|---|---|
| Specific impulse (M1D) | 282 s SL / 311 s vac (SpaceX 2013 Falcon 9 page, via Wikipedia); Everyday Astronaut: "282 to 311 seconds"; wevolver lists 283 s SL. Post-uprate values not officially republished | https://en.wikipedia.org/wiki/SpaceX_Merlin (cites http://www.spacex.com/falcon9.php#merlin_engine, 2013) ; https://everydayastronaut.com/raptor-engine/ ; https://www.wevolver.com/specs/merlin-engine-merlin-1d-falcon-9-falcon-heavy | OFFICIAL(2013, via WIKI) + EXPLAINER | **High** for 282/311 (2013-era); **Medium** as current values |
| Chamber pressure | 9.7 MPa (1,410 psi; "97 bar" per EA) — 2011-era figure; astronautix: 96 bar; wevolver claims 10.8 MPa (likely post-uprate estimate, unsourced) | https://en.wikipedia.org/wiki/SpaceX_Merlin (cites Aviation Week, 2011-08-11) ; https://everydayastronaut.com/raptor-engine/ ; http://www.astronautix.com/m/merlin1d.html | WIKI-indexed (trade press) + EXPLAINER; 10.8 MPa = COMMUNITY | **High** for ≈9.7 MPa (original 1D); **Low** for 10.8 MPa; model to ~9.7–10.8 MPa band |
| Expansion ratio (SL) | 16:1 | http://www.astronautix.com/m/merlin1d.html ("Area Ratio: 16"); UC OLLI handout; https://spacelaunchlive.com/articles/rocket-nozzle-types/ ; wevolver | COMMUNITY/EXPLAINER, multiply attested | **Medium–High** |
| Expansion ratio (MVac) | **165:1** — "a fixed 165:1 expansion nozzle" | SpaceX Falcon User's Guide 2025-05-09 | SX-UG (official) | **High** |
| Throttle range (M1D, current) | **190,000 → 108,300 lbf SL** (100% → 57%) | SX-UG 2025-05-09, Table 2-1 | SX-UG (official) | **High** |
| Throttle range (MVac, current) | 220,500 → 140,679 lbf (100% → ~64%) | Same table | SX-UG (official) | **High** |
| Older throttle claims | "to 40%" (2013 M1D); MVac "to 39% (360 kN)" | https://en.wikipedia.org/wiki/SpaceX_Merlin | WIKI | **Medium** (superseded by UG values) |
| Thrust-to-weight ratio claims | ">150" (SpaceX 2013 / NASA press kit); "155:1" (Spaceflight Now, 2015); "184" (Wikipedia infobox calc); "198:1" (Everyday Astronaut); "~200:1" (wevolver, UC handout) | NASA CRS-6 press kit ; https://spaceflightnow.com/2015/02/22/100th-merlin-1d-engine-flies-on-falcon-9-rocket/ ; https://en.wikipedia.org/wiki/SpaceX_Merlin ; https://everydayastronaut.com/raptor-engine/ | Mixed | **High** that claims span 150→~200 with uprating; no single canonical value |
| Propellants | LOX + RP-1 (rocket-grade kerosene); gas-generator cycle | SX-UG 2025 ("Rocket-grade kerosene and liquid oxygen as primary propellants"; Table 2-1 "Liquid, gas generator") | SX-UG (official) | **High** |
| Propellant conditioning (vehicle-level) | Subcooled LOX at 66.5 K; RP-1 chilled to 266.5 K — Falcon 9 Full Thrust onward | https://en.wikipedia.org/wiki/Falcon_9_Full_Thrust citing Musk tweet 2015-12-17 | WIKI-indexed (Musk) | **High** |
| Mixture ratio (O/F) | ~2.34–2.36 (wevolver: 2.36 SL / 2.38 MVac) — **not officially published** | https://www.quora.com/What-is-the-fuel-to-oxidiser-ratio-of-the-merlin-1d-vacuum-rocket-motor ; wevolver | COMMUNITY | **Low** |
| Propellant consumption (stage) | ~540 US gal/s for all nine engines (≈60 gal/s per engine) | https://spaceflightnow.com/2015/02/22/100th-merlin-1d-engine-flies-on-falcon-9-rocket/ | EXPLAINER | **Medium** |
| Total mass flow per engine | ≈305 kg/s at 845 kN / 282 s (ṁ = F/(Isp·g₀)) | — (arithmetic from cited values) | DERIVED | **Medium** |

---

## 2. Nozzle / Chamber Geometry — public estimates only (ALL low confidence)

No official throat, chamber, or bell dimensions have ever been published. Everything below is community/photogrammetric or derived and is labeled as an estimate in the model.

| Quantity | Estimate | Basis / Source | Type | Confidence |
|---|---|---|---|---|
| Nozzle exit diameter (SL) | 0.93–1.10 m (Wikipedia infobox: 0.92 m) | Forum photo-scaling, e.g. https://forum.nasaspaceflight.com/index.php?topic=26388.160 ; https://en.wikipedia.org/wiki/SpaceX_Merlin | COMMUNITY photogrammetric | **Low** |
| Throat diameter | ≈0.23–0.28 m — exit diameter ÷ √16, using 16:1 area ratio and 0.93–1.10 m exit | DERIVED from expansion ratio (§1.3) + exit estimate | DERIVED | **Low** |
| Chamber (barrel) diameter | Not publicly stated; photos show a compact barrel a bit wider than the throat under the injector dome | Photo inspection only (§3 photo list) | COMMUNITY/photogrammetric | **Low** |
| Bell proportions | Short bell consistent with 16:1 SL nozzle; regen-cooled full length (no separate radiative skirt on SL version) | SX-UG ("regeneratively cooled nozzle and thrust chamber"); photos in §3 | SX-UG + photos | **Medium** (qualitative) |
| Full-scale reference artifact | Smithsonian NASM flown Merlin 1D (envelope w/ stand 121.9 × 143.5 × 269.2 cm); image `nasm2023-05836` | https://airandspace.si.edu/collection-objects/rocket-engine-liquid-fuel-merlin-1d/nasm_A20220606000 ; https://airandspace.si.edu/multimedia-gallery/image/nasm2023-05836tif ; https://www.space.com/spacex-artifacts-smithsonian-air-space-museum | MUSEUM | **High** (as a scale/proportion reference) |
| Second full-scale reference | Cosmosphere (Hutchinson, KS): flight-proven Merlin from Koreasat-5A booster (2017-10-30, LC-39A) | https://cosmo.org/news/cosmospheres-rocket-gallery-to-feature-flight-proven-engine-from-spacexs-falcon-9/ | MUSEUM | **High** |
| Whole-booster references | Full Falcon 9 boosters displayed at Space Center Houston and KSC Visitor Complex | https://spacecenter.org/exhibits-and-experiences/spacex/ ; https://www.kennedyspacecenter.com/ | MUSEUM | **High** |

---

## 3. Exterior Architecture (qualitative, from public photos & official text)

| Feature | Public description | Source(s) | Type | Confidence |
|---|---|---|---|---|
| Cycle & pump layout | Gas-generator (open) cycle; "reliable turbopump design with a **single shaft for the liquid oxygen pump, the fuel pump, and the turbine**"; NASA press kit: "single-shaft, dual-impeller turbopump operating on a gas generator cycle." Turbopump assembly mounted beside the thrust chamber (photos) | SX-UG 2025 ; NASA CRS-6 press kit p.19 ; photos below | SX-UG + NASA + photos | **High** |
| Turbopump performance | ~36,000 rpm, ~10,000 hp (7,500 kW) | https://en.wikipedia.org/wiki/SpaceX_Merlin | WIKI-indexed | **Medium** |
| Turbopump heritage/materials (1A/1C-era) | Clean-sheet design by Barber-Nichols (2002): friction-welded shaft, Inconel 718 ends, integral aluminum RP-1 impeller; housings Inconel/aluminum/300-series stainless. (1D pump built in-house by SpaceX, derived design) | https://barber-nichols.com/products/rocket-engine-turbopumps/ ; https://barber-nichols.com/wp-content/uploads/2019/11/rocket_engine_turbopumps.pdf | Manufacturer | **Medium–High** (heritage; 1D details unpublished) |
| Gas generator | Small fuel-rich combustor feeding the turbine; mounted adjacent to turbopump/turbine inlet (photo-derived placeholder) | Cycle: SX-UG/NASA; explainer: https://ishan-roy.medium.com/how-do-spacexs-merlin-rocket-engines-work-638d3e7bd5b | Official (cycle) + COMMUNITY (placement) | Cycle **High**; placement **Low** |
| Turbine exhaust duct | Turbine exhaust dumped overboard through a separate duct/small nozzle routed down beside the main nozzle — the distinctive dark duct alongside the bell in M1D photos | Explainer (above); clearly visible in photos below | EXPLAINER + photos | **Medium** (qualitative); duct geometry photo-derived **Low** |
| Injector type | **Pintle injector** — "A pintle injector provides inherent combustion stability" (official); heritage: Apollo LM descent engine (TRW). Element geometry NOT public | SX-UG 2025 ; https://en.wikipedia.org/wiki/SpaceX_Merlin | SX-UG + WIKI | **High** (type only) |
| Gimbal & TVC | Gimbaled engines for pitch/yaw/roll. TVC actuators are hydraulic, using **high-pressure RP-1 from the turbopump as the working fluid**, returned to the low-pressure inlet (no separate hydraulic system). Gimbal block atop the dome; **two linear actuators per engine** (photos) | SX-UG 2025 ; NASA CRS-6 press kit p.19 ; photos below | SX-UG + NASA ; photos | System **High**; two-actuator arrangement **Medium** |
| Feed lines | LOX and RP-1 ducts from vehicle interface to pump inlets; LOX reaches the engine section via a double-wall transfer tube through the RP-1 tank (vehicle-level) | SX-UG 2025 ; photos | SX-UG + photos | **High** (existence); routing photo-derived **Low** |
| Cooling | "The regeneratively cooled nozzle and thrust chamber use a **milled copper alloy liner**"; kerosene is the regen coolant | SX-UG 2025 ; NASA CRS-6 press kit p.19 | SX-UG + NASA | **High** |
| Ignition | TEA-TEB (triethylaluminum–triethylborane) pyrophoric igniters; MVac carries dual-redundant TEA-TEB for restart | SX-UG 2025 ; https://en.wikipedia.org/wiki/SpaceX_Merlin | SX-UG + WIKI | **High** |
| Avionics/harness | Per-engine controller ("triple-redundant computer system per engine" per Wikipedia); visible boxes and cable harnesses on the powerhead in photos | https://en.wikipedia.org/wiki/SpaceX_Merlin ; UC OLLI handout | WIKI + COMMUNITY | **Medium** |
| Mounting | Octaweb thrust structure: 8 engines in a ring + 1 center | SX-UG 2025 ; NASA CRS-6 press kit p.19 | SX-UG + NASA | **High** |

**Specific public photo references (verified to exist):**
- Official SpaceX Flickr — Falcon 9 first stage in hangar, Merlin close-up (Jan 2016): https://www.flickr.com/photos/spacex/24175842635
- Steve Jurvetson Flickr — Octaweb + ring of Merlin 1D engines: https://www.flickr.com/photos/jurvetson/8975298066
- Wikimedia Commons category (25 files): https://commons.wikimedia.org/wiki/Category:Merlin_(rocket_engine)
- Commons — "SpaceX Testing Merlin 1D Engine In Texas.jpg" (SpaceX CC0, McGregor c.2012): https://commons.wikimedia.org/wiki/File:SpaceX_Testing_Merlin_1D_Engine_In_Texas.jpg
- Commons — "Merlin 1D engines and octaweb harness.jpg": https://commons.wikimedia.org/wiki/File:Merlin_1D_engines_and_octaweb_harness.jpg
- Smithsonian NASM display photo: https://airandspace.si.edu/multimedia-gallery/image/nasm2023-05836tif

---

## 4. Functional Flow (textbook-level, for the color-coded schematic)

Open **gas-generator cycle** (official or textbook only):

1. **LOX** (blue) and **RP-1** (amber) enter the single-shaft turbopump — LOX impeller on one end, RP-1 impeller on the other, turbine on the shaft (SX-UG; NASA CRS-6). Confidence: High.
2. A small fraction of both propellants is tapped to the **gas generator**, burned fuel-rich to keep turbine gas temperature low (cycle type: SX-UG/NASA — High; fuel-rich: standard GG practice, echoed by explainers — Medium).
3. GG combustion gas drives the **turbine**, then is **dumped overboard through the turbine-exhaust duct** beside the main nozzle — the open-cycle loss (EXPLAINER + photos — Medium/High).
4. **Main RP-1 flow** goes from the fuel pump **through the regenerative cooling channels of the chamber and nozzle** (milled copper-alloy liner) then to the **injector** (SX-UG + NASA — High).
5. **Main LOX flow** goes from the LOX pump directly to the **pintle injector** (type official; routing standard — Medium).
6. **Ignition:** TEA-TEB pyrophoric slug ignites the GG and main chamber; MVac dual-redundant for restart (SX-UG — High).
7. **Auxiliary tap:** high-pressure RP-1 also powers the **TVC hydraulic actuators**, returning to the pump inlet (SX-UG + NASA — High).
8. Mixture-ratio trim via servo-controlled valve per secondary sources (COMMUNITY — Low; modeled as generic valve placeholder).

---

## 5. Variant Notes: Merlin 1D (SL) vs Merlin Vacuum (MVac)

| Parameter | Merlin 1D (SL) | Merlin Vacuum (MVac) | Source / confidence |
|---|---|---|---|
| Role | F9/FH first stage, ×9 per core | F9/FH second stage, ×1 | SX-UG — High |
| Thrust | 845 kN (190,000 lbf) SL; ~914 kN vac | 981 kN (220,500 lbf) vac | SX-UG (845/981) — High; 914 kN — Medium (WIKI) |
| Isp | 282 s SL / 311 s vac | 348 s vac | SpaceX 2013 page via WIKI — High(2013)/Medium(current) |
| Expansion ratio | 16:1 | **165:1**, fixed non-deploying nozzle | 16:1 Medium-High; 165:1 SX-UG — High |
| Nozzle | Fully regen bell (milled copper-alloy liner) | Regen chamber + large **radiatively cooled niobium-alloy nozzle extension** ~2.7 m long, exit ~2.4 m per explainers (Wikipedia says 3.3 m — conflicting) | SX-UG (regen) — High; niobium: WIKI + https://www.elonx.net/spacex-stories-how-spacex-used-tin-snips-to-fix-a-rocket/ — Medium; exit dia — **Low** (2.4–3.3 m range) |
| Throttle | 100→57% (190,000→108,300 lbf) | 100→~64% (220,500→140,679 lbf) | SX-UG — High |
| Ignition | TEA-TEB | Dual-redundant TEA-TEB (restart) | SX-UG — High |
| Visual differences | Compact bell; turbine-exhaust duct beside nozzle; two TVC actuators | Huge thin-wall radiative skirt (bluish heat tint); GG duct vents near nozzle top; GN2 thrusters for roll | Photos (§3) — qualitative, Medium |
| 2023+ MVac option | Shorter nozzle variant (Transporter-7 debut): ~75% less nozzle material, ~10% less vacuum thrust | WIKI — Medium |

---

## 6. Known Unknowns (placeholders only / explicitly unmodeled)

1. **Injector element geometry** beyond "pintle type": pintle diameter, skip distance, slot/hole pattern, face design, film-cooling arrangement.
2. **Turbopump internals**: impeller/inducer geometry, turbine blade design and stage count, seal/purge package, bearing arrangement, exact 1D materials.
3. **Gas generator internals**: chamber size, injector, GG mixture ratio, turbine inlet temperature.
4. **Regen cooling channel dimensions**: channel count, cross-sections, wall thicknesses, jacket closeout method.
5. **Chamber contour**: exact chamber diameter, L*, contraction ratio, throat radius, bell contour coefficients (only 16:1 area ratio is attested).
6. **Valve internals & schedules**: valve types/sizes, ignition and startup/shutdown sequencing.
7. **Materials specifics** beyond "milled copper alloy liner", heritage pump materials, niobium MVac skirt.
8. **Gimbal range** (degrees) — not published; forum estimates only.
9. **Exact current mixture ratio, post-Block-5 chamber pressure, current-flight Isp** — 2013-era values are the last official ones.
10. **Engine controller internals**, sensor suite, harness routing specifics.
11. **Official engine length and dry mass for the Block 5 M1D** — best public anchors are the Mueller 470 kg figure and the NASM display record.

---

## Sources

**Official SpaceX / User's Guide**
- https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf — Falcon User's Guide rev 2025-05-09 (fetched, text-extracted; primary official source)
- https://www.spacex.com/media/falcon_users_guide_042020.pdf — April 2020 User's Guide
- http://www.spacex.com/falcon9.php#merlin_engine — 2013 SpaceX Falcon 9 page (Isp 282/311; via Wikipedia; defunct)
- https://www.spacex.com/vehicles/falcon-9/ — current page (JS-rendered)
- https://www.flickr.com/photos/spacex/24175842635 — official SpaceX Merlin close-up photo

**NASA / museum**
- https://www.nasa.gov/wp-content/uploads/2018/07/spacex_nasa_crs-6_presskit-2.pdf — NASA CRS-6 press kit (fetched, extracted)
- https://sma.nasa.gov/LaunchVehicle/assets/spacex-falcon-9-v1.2-data-sheet.pdf — NASA-hosted data sheet
- https://airandspace.si.edu/collection-objects/rocket-engine-liquid-fuel-merlin-1d/nasm_A20220606000 — Smithsonian NASM Merlin 1D record
- https://airandspace.si.edu/multimedia-gallery/image/nasm2023-05836tif — NASM display photo
- https://www.space.com/spacex-artifacts-smithsonian-air-space-museum — donation coverage
- https://cosmo.org/news/cosmospheres-rocket-gallery-to-feature-flight-proven-engine-from-spacexs-falcon-9/ — Cosmosphere Merlin
- https://spacecenter.org/exhibits-and-experiences/spacex/ · https://www.kennedyspacecenter.com/ — booster displays

**Reputable explainers / trade press**
- https://everydayastronaut.com/raptor-engine/ — EA (Merlin: 97 bar, 282–311 s, 198:1, GG cycle)
- https://www.nasaspaceflight.com/2013/03/falcon-9-boost-merlin-1d-engine-achieves-milestone/ — NSF qualification
- https://www.nasaspaceflight.com/2012/06/spacex-merlin-1d-orbital-fire-aj-26-engine/ — NSF 2012 testing
- https://spacenews.com/spacexs-merlin-1d-engine-achieves-flight-qualification/ — SpaceNews (fetched)
- https://spaceflightnow.com/2015/02/22/100th-merlin-1d-engine-flies-on-falcon-9-rocket/ — Spaceflight Now (fetched)
- https://barber-nichols.com/products/rocket-engine-turbopumps/ ; https://barber-nichols.com/wp-content/uploads/2019/11/rocket_engine_turbopumps.pdf — turbopump heritage
- https://www.elonx.net/spacex-stories-how-spacex-used-tin-snips-to-fix-a-rocket/ — MVac niobium nozzle story

**Wikipedia (index)**
- https://en.wikipedia.org/wiki/SpaceX_Merlin · https://en.wikipedia.org/wiki/Falcon_9 · https://en.wikipedia.org/wiki/Falcon_9_Full_Thrust · https://en.wikipedia.org/wiki/Falcon_9_Block_5

**Primary refs surfaced via Wikipedia**
- https://www.quora.com/Is-SpaceXs-Merlin-1Ds-thrust-to-weight-ratio-of-150+-believable/answer/Thomas-Mueller-11 — Tom Mueller (dry mass/T-W)
- https://twitter.com/SciGuySpace/status/994649495861432321 — Eric Berger, Block 5 thrust
- http://forum.nasaspaceflight.com/index.php?topic=33335.msg1125118#msg1125118 — SES-8 teleconference notes

**Community / aggregators (low confidence)**
- http://www.astronautix.com/m/merlin1d.html · http://www.astronautix.com/m/merlin1dvac.html — Astronautix
- https://www.wevolver.com/specs/merlin-engine-merlin-1d-falcon-9-falcon-heavy — wevolver aggregate
- https://www.uc.edu/content/dam/refresh/cont-ed-62/olli/fall-23-class-handouts/SpaceX%204%20Falcon%20rockets%20and%20Engines.pdf — UC OLLI handout (fetched)
- https://forum.nasaspaceflight.com/index.php?topic=26388.160 — NSF forum photo-scaling thread
- https://www.quora.com/What-is-the-fuel-to-oxidiser-ratio-of-the-merlin-1d-vacuum-rocket-motor — mixture ratio discussion
- https://ishan-roy.medium.com/how-do-spacexs-merlin-rocket-engines-work-638d3e7bd5b — GG exhaust explainer
- https://spacelaunchlive.com/articles/rocket-nozzle-types/ · https://spacelaunchlive.com/articles/rp-1-rocket-fuel/ — background explainers
- https://chimniii.com/news/Technology/Technology-SpaceX-No-Bell-to-Toll--How-Falcon-9-s-MVac-Nozzle-Silently-Whispers-Efficiency-in-the-Void.html — MVac nozzle dims (low)

**Photo archives**
- https://commons.wikimedia.org/wiki/Category:Merlin_(rocket_engine) — Commons category (25 files)
- https://commons.wikimedia.org/wiki/File:SpaceX_Testing_Merlin_1D_Engine_In_Texas.jpg — CC0 test-fire photo
- https://commons.wikimedia.org/wiki/File:Merlin_1D_engines_and_octaweb_harness.jpg — octaweb cluster
- https://www.flickr.com/photos/jurvetson/8975298066 — octaweb harness photo

**Key cross-checks:** 845 kN/190,000 lbf in ≥3 independent sources; 654→716 kN v1.1 confirmed by NASA + SpaceNews + Spaceflight Now; 165:1 MVac by SX-UG + Wikipedia; TEA-TEB, pintle, single-shaft turbopump, kerosene-hydraulic TVC, and milled-copper regen liner all confirmed in official SpaceX text plus NASA press kit. Disagreements reported as ranges: SL thrust 845 vs 854 kN, chamber pressure 9.7 vs 10.8 MPa, engine length (no official 1D value), exit diameter 0.92–1.10 m, MVac exit 2.4–3.3 m.
