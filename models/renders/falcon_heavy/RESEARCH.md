# SpaceX Falcon Heavy — Public-Source Research Dossier

> Educational, non-functional public-source reconstruction. Not suitable for manufacture, propulsion, testing, or operational engineering.

Research date: 2026-07-02. Merged from three domain reports (overall dimensions & performance; structure, livery & internals; engine layout & upper stage). Every fact carries its source(s) and original confidence rating. Values marked **[DERIVED]** are geometric derivations from sourced numbers, not published values. Where sources conflict, ranges are reported with both sources. All facts were verified against fetched source content (not memory) at research time.

## Source key (frequently cited sources)

| ID | Source | URL | Type |
|---|---|---|---|
| UG25 | Falcon User's Guide, rev 2025-05-09 (128 pp PDF, fetched and text-extracted) | https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf | Official SpaceX |
| UG21 | Falcon User's Guide 2021-09 (MIT mirror, corroboration) | https://web.mit.edu/2.70/Reading%20Materials/SpaceX%20Falcon-users-guide-2021-09.pdf | Official SpaceX (mirror) |
| UG15 | Falcon 9 User's Guide 2015 rev 2 (corroboration) | https://spacex.com.pl/files/2017-10/falcon-9-users-guide-rev-2.0.pdf | Official SpaceX (mirror) |
| UG08 | Falcon 9 User's Guide 2008/2009 (corroboration) | https://www.spaceflightnow.com/falcon9/001/f9guide.pdf | Official SpaceX (mirror) |
| SX-FH | spacex.com Falcon Heavy page (live page is JS-rendered; returns no static content — verify via archives/mirrors) | https://www.spacex.com/vehicles/falcon-heavy/ | Official SpaceX |
| SX24 | spacex.com FH page, archive.org capture 2024-12-26 | https://web.archive.org/web/20241226160703/https://www.spacex.com/vehicles/falcon-heavy/ | Official SpaceX (archive) |
| SX17 | spacex.com FH page, archive.org capture 2017-05-31 (has the Pluto line) | https://web.archive.org/web/20170531202158/http://www.spacex.com/falcon-heavy | Official SpaceX (archive) |
| FAA-EA | FAA "Final EA and FONSI for SpaceX Falcon Launches at KSC and CCAFS," July 2020, §2.1.1.2 (fetched, text-extracted) | https://www.faa.gov/sites/faa.gov/files/space/environmental/nepa_docs/SpaceX_Falcon_Program_Final_EA_and_FONSI.pdf | Federal (FAA) |
| WP-FH | Wikipedia "Falcon Heavy" (index; its dimension refs are SpaceX and *Espace et Exploration* No. 51) | https://en.wikipedia.org/wiki/Falcon_Heavy | Wikipedia-index |
| WP-FT | Wikipedia "Falcon 9 Full Thrust" | https://en.wikipedia.org/wiki/Falcon_9_Full_Thrust | Wikipedia-index |
| WP-B5 | Wikipedia "Falcon 9 Block 5" | https://en.wikipedia.org/wiki/Falcon_9_Block_5 | Wikipedia-index |
| WP-M | Wikipedia "SpaceX Merlin" | https://en.wikipedia.org/wiki/SpaceX_Merlin | Wikipedia-index |
| SF101 | Spaceflight101 FH datasheet (site now 404; archive capture 2022-12-01 fetched; values marked * are its own estimates) | https://web.archive.org/web/20221201210405/https://spaceflight101.com/spacerockets/falcon-heavy/ | Reputable explainer |
| WEV-M | Wevolver Merlin 1D spec page | https://www.wevolver.com/specs/merlin-engine-merlin-1d-falcon-9-falcon-heavy | Community aggregator |

Also checked, no usable dimension content: NASA JPL Europa Clipper press kit quick facts, https://www.jpl.nasa.gov/press-kits/europa-clipper/quick-facts/ (names "SpaceX Falcon Heavy rocket" as launcher, no vehicle dimensions); FAA FONSI for Falcon Heavy RTLS at LZ-1, https://www.faa.gov/sites/faa.gov/files/space/environmental/nepa_docs/FAA_FONSI_for_Falcon_Heavy_RTLS_at_LZ-1.pdf (covers only residual landing propellants).

---

## 1. Vehicle dimensions & performance

### 1.1 Overall stack dimensions

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Height, standard fairing | **70 m (229.6 ft)** "including both stages, interstage, and standard fairing" | UG25 Table 2-1 (verbatim); SX24 "HEIGHT 70 m / 229.6 ft"; FAA-EA "overall length of 229 feet"; WP-FH 70.0 m | **High** (3 independent official/federal) |
| Height, extended fairing | **75.2 m (246.7 ft)** | UG25 Table 2-1 (verbatim) | **High** |
| Width across three cores | **12.2 m (39.9 ft)** ("Total Width" on 2017 page; "WIDTH" on 2024 page; SF101 "Span") | SX24; SX17; SF101; WP-FH infobox | **High**. Conflict note: SpaceX's ft conversion is 39.9 ft; Wikipedia rounds to 40 ft |
| Core diameter | **3.66 m (12 ft)**, both stages | UG25 Table 2-1 (verbatim "Diameter 3.66 m (12 ft)"); SF101 3.66 m; https://en.wikipedia.org/wiki/Falcon_9 | **High**. Conflict note: Wikipedia/SpaceX F9 web page round to 3.7 m — use 3.66 m for CAD |
| Liftoff mass | **1,420,788 kg (3,125,735 lb)** | SX24 (verbatim); SX17 identical; FAA-EA "approximately 3.1 million pounds" | **High** for the published nominal; the 7-digit precision is a marketing nominal (fully-fueled, expendable config), not a measured constant |

### 1.2 Component lengths (CAD-critical; official sources do NOT publish a stage-by-stage breakdown)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| First stage (single core/booster) length | **~42.6 m** without interstage (SF101; same article elsewhere says the core "stands about 41.2 meters tall" — internally inconsistent, report range **41.2–42.6 m**); WP-FH lists 42.6 m citing *Espace et Exploration* No. 51 | SF101; WP-FH | **Medium-Low** (community/press estimate; SpaceX has never published it) |
| Interstage length | **~4.5 m**; "longer and stronger than the Falcon 9 v1.1 interstage" | WP-FH (Espace et Exploration No. 51); WP-FT | **Medium-Low to Medium** (rated Medium-Low in the dimensions report, Medium in the structure report; no official figure) |
| Second stage length | **~12.6 m** "without payload adapter and 1st Stage Interstage" (SF101, value flagged * = estimate); WP-FH 12.6 m | SF101; WP-FH | **Medium-Low** (estimate) |
| Reconstruction warning | 42.6 + 4.5 + 12.6 + 13.1/13.2 ≈ 72.8–72.9 m > 70 m stated total. The component estimates overlap: the MVac nozzle/second-stage aft section is recessed inside the interstage, and the fairing base wraps the S2 forward end. For CAD, anchor to the official 70.0 m overall / 3.66 m diameter / 5.2 m fairing diameter and treat unofficial stage lengths as adjustable to close the stack | derived (dossier analysis) | — |

### 1.3 Payload fairing

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Standard fairing outer diameter | **5.2 m (17.2 ft)** (UG25); SpaceX web page says 5.2 m / 17.1 ft | UG25 §4 (verbatim); SX24 | **High** |
| Standard fairing overall height | **13.2 m (43.5 ft)** per UG25; **13.1 m (43 ft)** per SpaceX web page; WP-FH lists both (13.2 via Espace et Exploration). Treat as range **13.1–13.2 m** | UG25; SX24; SF101 (13.1 m) | **High**, with small official-source spread |
| "13.9 m" fairing figure | **Not found in any official source.** SpaceX sources give 13.1/13.2 m standard and 18.7 m extended. Treat 13.9 m as an unsupported third-party figure | searched; no reliable hit | — |
| Extended fairing | Same 5.2 m (17.2 ft) diameter, **overall height 18.7 m (61.25 ft)**; vehicle height 75.2 m with it; halves joined by bolted frangible seam (vs mechanical latches + pneumatic pushers on standard) | UG25 §4 and §2 (verbatim) | **High** |
| Fairing construction | **Composite sandwich: aluminum honeycomb core between carbon-fiber face sheet plies**; two half-shells; inner surface emissivity ~0.9 | UG25 thermal section and §5 (verbatim); SX24 "carbon composite" | **High** |
| Fairing access door | 1 standard (up to 8 optional), circular, **610 mm (24 in) diameter** | UG25 §4 | High |
| Fairing mass | ~1,750 kg | SF101 (estimate) | **Low** (community estimate only) |

### 1.4 Propulsion / performance

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Liftoff (SL) thrust | **22,819 kN (5,130,000 lbf)**, 27 Merlin 1D engines | UG25 §2 text (verbatim); SX24 "THRUST AT SEA LEVEL 22,819 kN / 5,130,000 lbf"; FAA-EA "5.13 million pounds" | **High** |
| Vacuum thrust, stage 1 (all 27 engines) | **24,681 kN (5,548,500 lbf)** (⇒ ≈914 kN vacuum per first-stage M1D) | SX24 (verbatim); SF101 same; UC OLLI handout https://www.uc.edu/content/dam/refresh/cont-ed-62/olli/fall-23-class-handouts/SpaceX%204%20Falcon%20rockets%20and%20Engines.pdf (mirrors old spacex.com stats) | **High** (official archive); UC handout corroboration Medium |
| Per-engine SL thrust | **845 kN (190,000 lbf)** (Merlin 1D, full thrust). 27 × 190,000 lbf = 5,130,000 lbf exactly. Conflict: UG25's own F9 table gives stage total 7,686 kN SL → 854 kN/engine, while its prose says 845 kN × 9 = 7,605 kN; Wevolver and the UC handout also quote 854 kN. Treat as range **845–854 kN** | UG25 §2 pp.7-8 + Table 2-1; SX24 Merlin panel; WEV-M; UC handout | **High** that the value is 845 kN as published and **High** that the internal discrepancy exists |
| M1D first-stage vacuum thrust (per engine) | ≈ **914 kN** (community-tracked; RealismOverhaul config lists 914.22 kN). Do not confuse with the 981 kN MVac figure | WP-M; https://github.com/KSP-RO/RealismOverhaul/blob/master/GameData/RealismOverhaul/Engine_Configs/Merlin1_Config.cfg | Medium |
| Second stage (MVac) thrust | **981 kN (220,500 lbf) vacuum**; throttle to 140,679 lbf. Conflict: older figure **934 kN** appears on WP-FH and SF101 — superseded; use 981 kN for current Block 5 | UG25 Table 2-1; SX24 second-stage panel; WP-M | **High** |
| Second stage burn time | **397 s** | SX24; https://www.defenceaviation.com/spacex-falcon-9-second-stage-merlin-vacuum-engine-dragon-spaceship-specifications/ ; UC handout | High (as published); explainer corroboration Medium |
| MVac expansion ratio | **165:1 fixed nozzle** | UG25 §2 (verbatim); WP-M | High |

### 1.5 Payload capacities (SpaceX published, fully expendable)

| Destination | Value | Source(s) | Confidence |
|---|---|---|---|
| LEO (28.5°) | **63,800 kg (140,660 lb)** | SX24 & SX17 (verbatim); FAA-EA "64 tons (141,000 pounds)"; WP-FH | **High** |
| GTO (27°) | **26,700 kg (58,860 lb)** | SX24 & SX17 | **High** |
| Mars | **16,800 kg (37,040 lb)** | SX24 & SX17 | **High** |
| Pluto | **3,500 kg (7,720 lb)** | SX17 only (verbatim; dropped from post-2018 site redesigns) | **High** that it was published; Medium as a current figure |
| Caveats | These are max-expendable marketing figures; UG25 states mass-to-orbit data "available upon request" (none published in the guide). SF101's older 54,400 kg LEO / 22,200 kg GTO / 13,600 kg Mars reflect the pre-2017 (pre-uprated, partially reusable) baseline — historical range only | UG25 §3; SF101 | — |

### 1.6 Propellant loads and masses (public federal source)

FAA-EA §2.1.1.2 (verbatim: "The Falcon Heavy contains 1,898,000 pounds of LOX and 807,000 pounds of RP-1 in the first stage, and 168,000 pounds of LOX and 64,950 pounds of RP-1 in the second stage."):

| Item | Published (lb) | Converted (kg) | Source | Confidence |
|---|---|---|---|---|
| Stage 1 LOX, all 3 cores | 1,898,000 | ~860,900 | FAA-EA | **High** |
| Stage 1 RP-1, all 3 cores | 807,000 | ~366,000 | FAA-EA | **High** |
| Per core (÷3) | LOX ~632,700 / RP-1 ~269,000 | LOX ~287,000 / RP-1 ~122,000 | derived from FAA-EA | High (arithmetic) |
| Stage 2 LOX | 168,000 | ~76,200 | FAA-EA | **High** |
| Stage 2 RP-1 | 64,950 | ~29,460 | FAA-EA | **High** |
| Cross-check, per core | — | LOX 287,430 / RP-1 123,570 | SF101; WP-FH (Espace et Exploration) | Medium — agrees with FAA within ~1% |
| Cross-check, stage 2 | — | LOX 75,200 / RP-1 32,300; stage launch mass ~111,500; inert ~4,000 | SF101 (starred estimates); WP-FH | Medium — agrees with FAA within ~2% |
| F9 Block 5 single-core total propellant (context) | 1,135,925 lbm | ~515,250 | FAA-EA Table 2-1 | High |
| Dry masses | Core inert ~25,600 kg (SF101 est.; "24–27 t" range in its text); S2 inert ~4,000 kg | SF101; WP-FH (Espace et Exploration) | **Low-Medium** — never officially published |

---

## 2. Core/booster structure & livery

### 2.1 Three-core layout

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| First stage = 3 Falcon 9 cores | "The first stage comprises three Falcon 9 first stages: a center core and two side boosters; each booster and the core has nine Merlin 1D (M1D) engines" (27 total) | UG25 §2 | High |
| Cores strengthened vs stock F9 | "Falcon Heavy's first stage comprises three Falcon 9 first stages with enhancements provided to strengthen the cores" | UG25 §2 | High |
| Center core differs structurally | "The center core consists of thicker tank walls and carries the booster separation system." Side boosters (+Y / −Y) "are structurally identical" to each other | UG25 §2 | High |
| Same second stage + fairing as Falcon 9 | "Falcon Heavy utilizes the same second stage and same payload fairing as flown on Falcon 9" | UG25 §2 | High |
| Side boosters are nosecone-topped F9 stages | "two additional Falcon 9 first stages with aerodynamic nose-cones mounted outboard serving as strap-on boosters"; the center core carries the interstage (second stage stacks only on the center core) | WP-FH; visually confirmed in SpaceX pad photos (§2.6) | High |
| Attachment points (marketing text) | Side cores "connected on the nosecone, the interstage, and on the octaweb" | SX-FH / SX24 (JS page; text widely mirrored, e.g. https://www.wevolver.com/specs/falcon-heavy-block-5) | High |
| Attachment points (precise, official) | "The two side boosters are connected to the center core at the base engine mount and at the forward end of the LOX tank on the center core." Two pneumatic pusher separation mechanisms connect the forward ends of each side booster to the center core (fastening the top of the center-core LOX tank to the side boosters); two identical pusher mechanisms connect the aft ends and "laterally force the base of the side booster from the center core following shutdown" | UG25 §2 | High |
| CAD note | Forward attach plane = top of center-core first-stage LOX tank (just below interstage); aft attach plane = octaweb/base engine mount. 2 pushers forward + 2 aft per side booster | derived from UG25 | — |
| Coordinates/naming | Cores designated center, +Y, −Y; "The z-axis points to zenith when the vehicle is horizontal" | UG25 §2 | High |
| Hold-down | "After engine start, Falcon vehicles are held down until all vehicle systems are verified" | UG25 | High |

### 2.2 Interstage (the black band)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Construction | "a composite structure consisting of an aluminum honeycomb core surrounded by carbon fiber face sheet plies. The interstage is fixed to the forward end of the first stage tank. The stage separation system is located at the forward end of the interstage." (Same wording since the 2008 guide) | UG25 §2; UG08 | High |
| Length | ~4.5 m (see §1.2 — unofficial) | WP-FT; WP-FH | Medium-Low to Medium |
| Black appearance | Block 5 leaves the interstage unpainted with a permanent black hydrophobic thermal-protection coating — "the largest visual difference… the black band around the middle of the rocket" | WP-B5; https://spacenews.com/musk-details-block-5-improvements-to-falcon-9/ (quoting Musk); https://insights.globalspec.com/article/9968/block-5-how-spacex-re-engineered-its-falcon-9-rocket-to-endure-a-100-launch-lifespan | High (WP-B5, SpaceNews); Medium-High (GlobalSpec) |
| Stage-separation hardware at that joint | "mated by mechanical latches at three points between the top of the interstage and the base of the second stage fuel tank… helium circuit… releases the latches… four pneumatic pushers", including "a redundant center pusher" | UG25 §2 | High |

### 2.3 Grid fins

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Count/placement | "Four grid fins near the top of the first stage" (per core); FH: "four retractable grid fins at the top of each of the three Falcon 9 boosters, which extend after separation" (12 total per SX24). Photos show them stowed flat just below the nosecone (side boosters) / interstage (center core) | UG25 §2; WP-FH; SX24 | High |
| Material/history | Aluminum with ablative coating originally; replaced by larger single-piece cast-and-cut unpainted titanium fins, first flown 25 June 2017 (Iridium NEXT 11–20), standard on Block 5 | https://en.wikipedia.org/wiki/Grid_fin ; WP-B5; WP-FT; https://www.teslarati.com/spacex-starship-super-heavy-grid-fins-titanium-to-steel/ | High (Wikipedia set); Medium (Teslarati) |
| Size — conflicting, report as range | Museum artifact (flown titanium fin): **5 ft 2 in × 4 ft 0.5 in × 1 ft 3.5 in (~1.57 × 1.23 × 0.39 m)** — Smithsonian NASM collection object. Community estimates: "5ft x 4ft" (~1.5 × 1.2 m) and "perhaps 2 m by 1.2 m (approximately 6.5 ft x 4 ft)" | https://airandspace.si.edu/collection-objects/grid-fin-rocket-launch-vehicle-falcon-9/nasm_A20220607000 (page blocks robotic fetch; dimensions surfaced via search index); https://teamarcis.medium.com/grid-fins-8fc5175113d3 ; https://www.teslarati.com/spacex-starship-super-heavy-grid-fins-titanium-to-steel/ | High (museum); Low-Medium (community) |
| CAD guidance | ~1.5–1.6 m span × ~1.2 m chord × ~0.4 m deep (museum artifact = best-grounded; ~2 m figure is an upper-bound community estimate) | as above | — |

### 2.4 Landing legs

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Count/placement | "Four deployable legs at the base" of each first stage; FH "each core includes four extensible landing legs" that "stow along the sides of each core during liftoff and extend outward and down just before landing" (12 total per SX24) | UG25 §2; WP-FH; SX24 | High |
| Material | "Made of carbon fiber with aluminum honeycomb" — original SpaceX "Landing Legs" page (July 2013, since removed; cited in https://en.wikipedia.org/wiki/Falcon_9_v1.1 and WP-FH); contemporaneous report at https://spaceflightnow.com/falcon9/009/140223legs/ . Telescoping legs use an aluminum-honeycomb "crush core" per https://www.teslarati.com/spacex-rocket-durability-leg-retraction/ | High (official-via-press); Medium (crush core) |
| Deployed span — conflicting, report as range | **~18 m / 60 ft** (originates from SpaceX's 2013 "Landing Legs" page, removed; survives via Wikipedia citation trail — official-claim-via-archive) vs **~10 m / 33 ft** side-to-side at https://www.eclipseaviation.com/how-spacex-landing-legs-work/ (community). CAD guidance: model deployed span in the 15–18 m class; 60 ft is the standard public claim | as stated | Medium (18 m); Low (10 m) |
| Block 5 finish | Legs unpainted black with permanent TPS; retractable (latch back for transport) | WP-B5 | High |

### 2.5 Raceways (external cable conduits)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Second stage (official) | Payload harnesses "are routed along the exterior of the second stage propellant tanks, underneath raceway covers that provide protection during ground and flight operations" | UG25 §4 | High |
| First stage | Each core carries a full-length external raceway cover (avionics/plumbing conduit), visible as a raised black strip; on Block 5 raceways are among the unpainted black TPS-covered elements. Exact cross-section dimensions are not public | WP-B5; https://insights.globalspec.com/article/9968/block-5-how-spacex-re-engineered-its-falcon-9-rocket-to-endure-a-100-launch-lifespan ; SpaceX Flickr pad close-ups (§2.6) | High (existence/black color); Low (dimensions — community estimate only) |

### 2.6 Livery / markings (photo-cited)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Overall scheme | White-painted cores and second stage; black unpainted interstage (center core), black raceways and landing legs (Block 5) | Block 5 references above + photos below | High |
| Markings | Large dark-gray/black "SpaceX" logotype lengthwise on the first-stage tank and on the fairing; US flag on the fairing and booster/interstage region; "FALCON HEAVY" wordmark on the center-core interstage (FH Demo) | SpaceX Flickr photos (CC BY-NC 2.0, license verified on photo pages): FH Demo Feb 2018 on LC-39A https://www.flickr.com/photos/spacex/40126461411/ , https://www.flickr.com/photos/spacex/25254688767 , https://www.flickr.com/photos/spacex/38583830575/ ; Arabsat-6A Apr 2019 (all-Block-5) https://www.flickr.com/photos/spacex/40628438523 | High (official photos) |
| Additional galleries | Triple-landing gallery https://www.space.com/spacex-falcon-heavy-arabsat-6a-launch-landings-photos.html (Medium-High); official photostream index https://www.flickr.com/photos/spacex/ (cite individual photo URLs, not album URLs — album pages did not render); Wikimedia Commons https://commons.wikimedia.org/wiki/Category:Falcon_Heavy with subcategories by flight/boosters/launches-landings (High), example file https://commons.wikimedia.org/wiki/File:Falcon_Heavy_Demo_Mission_(39337245145).jpg | as noted | as noted |
| Era caveat for CAD | FH Demo (2018) side boosters were pre-Block-5 (white-painted legs/raceway; black interstage on center core only); Arabsat-6A/STP-2 onward are Block 5 (black legs, raceways, interstage) | Block 5 refs + mission photos above | Medium-High |

---

## 3. Tank & internal architecture (public facts only)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Propellants, both stages | LOX + RP-1 | UG25 | High |
| Wall material / manufacturing | "The first stage propellant tank walls of the Falcon vehicles are made from an aluminum lithium alloy. Tanks are manufactured using friction stir welding" (identical claim since 2008: "walls and domes… aluminum lithium alloy… all friction stir welded tank") | UG25 §2; UG08 | High |
| Structure types | LOX tank = monocoque; fuel tank = skin-and-stringer (UG Table 2-1, both stages); "Aluminum lithium skin; aluminum domes"; tank pressurization = heated helium. Conflict note: SF101 describes the stage-2 RP-1 tank as monocoque while UG25 Table 2-1 says S2 "fuel tanks – skin and stringer" — prefer the official UG25 value | UG25 Table 2-1; SF101 | High (UG25); conflict flagged |
| Tank order, stage 1 | LOX forward/upper, RP-1 aft/lower: "A common dome separates the LOX and RP-1 tanks, and a double-wall transfer tube carries LOX through the center of the RP-1 tank to the engine section." 2015 guide adds the dome/tube are insulated | UG25 §2; UG15 | High |
| Tank order, stage 2 | Same arrangement (LOX forward, RP-1 aft): S2 tank "is a shorter version of the first stage tank and uses most of the same materials, construction, tooling, and manufacturing techniques"; separation latches meet "the base of the second stage fuel tank" (fuel aft); AMOS-6 anomaly "originated around the upper stage oxygen tank" with the flash "near the top of the upper stage" | UG25; https://www.universetoday.com/articles/spectacular-video-captures-catastrophic-spacex-falcon-9-rocket-explosion-during-prelaunch-test ; https://www.nasaspaceflight.com/2016/09/falcon-9-explodes-amos-6-static-fire/ | High (S1); Medium-High (S2, inferred from converging official statements) |
| Center core | Thicker tank walls than side boosters/stock F9 (actual thickness values not public — see §6) | UG25 §2 | High (statement); values not public |
| Specific alloys (industry/community; not in official SpaceX text) | Constellium Airware **2195-T8** plate "used in the tank barrels and domes of the booster"; **2198** sheet also associated with the Falcon family. Report as: 2195 plate + 2198 sheet, Al-Li family per official text | https://www.lightmetalage.com/news/industry-news/aerospace/how-light-metals-help-spacex-land-falcon-9-rockets-with-astonishing-accuracy/ (Medium-High); https://www.researchgate.net/publication/294702811_Airware_2198_backbone_of_the_Falcon_family_of_SpaceX_launchers (supplier technical paper, Medium); WP-FT "The aluminium-lithium alloy used is 2195-T8" (Medium-High) | Medium to Medium-High |
| COPV helium bottles (public post-AMOS-6) | Official SpaceX anomaly updates (28 Oct 2016 / 2 Jan 2017): "a breach in the cryogenic helium system of the second stage liquid oxygen tank"; investigation focused on "one of the three composite overwrapped pressure vessels (COPVs) inside the LOX tank"; buckled liners could trap LOX/SOX between liner and overwrap. Original spacex.com "Anomaly Updates" page is offline; official text mirrored at https://spaceref.com/status-report/spacex-amos-6-anomaly-update-28-october-2016/ and reported at https://www.americaspace.com/2017/01/02/spacex-closes-amos-6-investigation-aims-to-launch-10-satellites-next-sunday/ and https://en.wikipedia.org/wiki/AMOS-6_(satellite) . CRS-7 precedent: strut-mounted helium COPV inside the S2 LOX tank (Wikipedia-indexed coverage) | official-via-mirror + Wikipedia-index | High (3 COPVs in the S2 LOX tank is public). **First-stage COPV count/placement is NOT publicly specified — model generically if needed (Low)** |
| LOX subcooling (context only, no geometry impact) | LOX subcooled to ~66.5 K on Full Thrust | WP-FT | Medium-High |
| Propellant loads | See §1.6 (FAA-EA figures) | FAA-EA | High |

---

## 4. Engine layout & octaweb

### 4.1 Arrangement (first stage, per core)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Arrangement | 9 Merlin 1D per core: "The first stage M1D engines are configured in a circular pattern, with eight engines surrounding a center engine" | UG25 p.8 | High |
| Name "Octaweb" | Publicly named "Octaweb"; replaced the v1.0 3×3 grid ("tic-tac-toe") layout starting with Falcon 9 v1.1 (2013). NASA: "an arrangement of eight engines in a circle around the center engine… reduces the length and weight of the Falcon 9 thrust structure and streamlines manufacturing." Note: the 2025 User's Guide itself does not use the word "octaweb" — it is the NASA/SpaceX-media/public name | https://www.nasa.gov/blogs/commercialresupply/2014/04/18/meet-the-octaweb/ ; https://en.wikipedia.org/wiki/Falcon_9_v1.1 | High |
| Per-engine bays | "each engine is housed within its own metal bay to isolate it from neighboring engines" | UG25 pp.4-5 (reliability section) | High |
| Engines offset within bays | "All the Falcon 9 engines apart from the center, are placed in offset with respect to the compartment" (space for gas-generator exhaust) | https://www.thespacetechie.com/octaweb-structure/ | Low-Medium |
| Octaweb construction (Block 5) | Bolted (not welded) assembly | WP-B5 | Medium |
| Falcon Heavy attachment | Side boosters connect to center core "at the base engine mount [octaweb] and at the forward end of the LOX tank" | UG25 p.7 | High |

### 4.2 Outer engine circle placement & bell spacing (no official figure exists)

No published SpaceX dimension for the outer-engine mounting circle was found. Community photogrammetric threads exist but were Cloudflare-blocked to automated fetch; verified anchors plus a transparent derivation are given instead.

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Stage diameter (anchor) | 3.66 m (12 ft) | UG25 Table 2-1; https://en.wikipedia.org/wiki/Falcon_9 | High |
| Merlin 1D (sea-level) nozzle exit — conflicting | WEV-M lists exit area 0.90 m² (→ exit dia ≈ 1.07 m); Everyday Astronaut's Starship guide lists Merlin nozzle area 0.65 m² (→ ≈ 0.91 m). Report bell exit diameter as range **0.9–1.1 m** | WEV-M; https://everydayastronaut.com/definitive-guide-to-starship/ | Low-Medium (sources conflict) |
| Outer engine circle diameter **[DERIVED]** | ≈ **2.4–2.7 m** (center-of-engine circle). Derivation: bells of 0.9–1.1 m exit dia must fit 8-around-1 inside the 3.66 m base with near-touching packing visible in underside photos; R ≈ 1.83 m − (bell radius 0.45–0.55 m) − small margin → R ≈ 1.2–1.35 m | Anchors above + SpaceX official 27-engine underside photo https://x.com/spacex/status/1114932679688900608 (also reported at https://interestingengineering.com/innovation/spacex-image-falcon-heavy-27-merlin-engines) | Low (derived) |
| Adjacent outer bell center-to-center spacing **[DERIVED]** | ≈ **0.92–1.03 m** (= 2R·sin 22.5° for R = 1.2–1.35 m); implies bell-edge gaps of only ~0–0.1 m — bells visually near-touching in underside photos | Same anchors/photos | Low (derived) |
| Community photogrammetry threads (content unverified — Cloudflare 403; cite for further manual reading only, do not quote numbers) | NSF "Falcon 9 dimensions: measuring photos" https://forum.nasaspaceflight.com/index.php?topic=41947.0 ; NSF "Falcon 9 clustered Engine Thrust Frame configuration" https://forum.nasaspaceflight.com/index.php?topic=44735.0 ; KSP forum "Falcon 9 octaweb?" https://forum.kerbalspaceprogram.com/topic/95630-falcon-9-octaweb/ | community | Low |
| Academic simplified octaweb geometry exists | DLR modeled a "simplified geometry of Falcon 9 first stage with octaweb engine configuration" for retropropulsion CFD (figure public; dimension table paywalled) | https://www.researchgate.net/publication/318295483_A_Numerical_Study_on_the_Thermal_Loads_During_a_Supersonic_Rocket_Retro-Propulsion_Maneuver ; journal version https://arc.aiaa.org/doi/10.2514/1.A34486 | Medium (existence); numbers not extracted |

### 4.3 Engine cant (outer engines)

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Official statement on fixed cant | **None found.** No SpaceX statement that outer Merlins are permanently canted was located | absence of evidence across User's Guide + SpaceX pages | Medium (that no statement exists) |
| All 9 engines gimbal | User's Guide attitude-control table lists "Gimbaled engines" for first-stage pitch/yaw/roll; TVC actuators are fuel-hydraulic ("thrust vector control system pulls from the high-pressure rocket-grade kerosene system") | UG25 pp.4, Table 2-1 | High |
| Community consensus | All nine engines gimbaled; underside photos show nozzles essentially parallel (axis-aligned) at rest — model cant ≈ 0° for CAD | https://www.quora.com/On-the-SpaceX-Falcon-9-how-many-engines-gimbal-for-directional-control-just-the-center-one-On-the-Heavy-will-it-be-all-three-center-engines ; https://x.com/spacex/status/1114932679688900608 | Low-Medium |

### 4.4 Engine-section base heat shielding

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Reusable base heat shield | Block 5 has "a reusable heat shield protecting the engines and plumbing at the base of the rocket" | WP-B5 | Medium-High |
| Titanium replacing composite | Block 5 replaced the earlier composite base heat shield around the octaweb with bolted-on titanium (higher melting point, less refurbishment) | https://insights.globalspec.com/article/9968/block-5-how-spacex-re-engineered-its-falcon-9-rocket-to-endure-a-100-launch-lifespan ; https://www.space.com/40582-elon-musk-explains-spacex-falcon-9-block-5.html (Musk 2018 Block 5 press call) | Medium |
| Local water cooling | Musk (2018): parts of the base shield have active water cooling for hot spots (shock impingement during reentry) | same two URLs | Medium |
| Block 5 TPS general | "Thermal protection shielding was modified to support rapid recovery and refurbishment" | UG25 p.6 | High |

### 4.5 27-engine totals & consistency

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| FH engine count/total | "Each of the 27 first stage engines produces 845 kN (190,000 lbf) of thrust at sea level, for a total of 22,819 kN (5,130,000 lbf) of thrust at liftoff" | UG25 p.7 | High |
| Official marketing statement | "Falcon Heavy's 27 Merlin engines generate more than 5 million pounds of thrust at liftoff" | https://x.com/spacex/status/1114932679688900608 ; SX-FH (JS-rendered; stat confirmed via search index) | High |
| Consistency check (lbf) | 27 × 190,000 lbf = 5,130,000 lbf exactly — internally consistent; the kN pair (27 × 845 = 22,815 vs 22,819) differs only by lbf→kN rounding | UG25 arithmetic | High |
| 845 vs 854 kN discrepancy flag | UG25 prose uses 845 kN/engine, but its own F9 table gives first-stage total "7,686 kN (sea level) (1,710,000 lbf)" — 7,686/9 = 854 kN, while prose says "845 kN… for a total thrust of 7,605 kN". WEV-M and the UC handout also quote 854 kN. Treat per-engine SL thrust as **845–854 kN** (see §1.4) | UG25 pp.7-8 + Table 2-1; WEV-M; UC handout | High that the discrepancy exists |

---

## 5. Second stage & Merlin Vacuum

| Fact | Value | Source(s) | Confidence |
|---|---|---|---|
| Commonality | FH uses the same second stage (and fairing) as Falcon 9 | UG25 §2 | High |
| Single MVac per second stage | "A single Merlin Vacuum (MVac) engine powers the second stage, using a fixed 165:1 expansion nozzle" (fixed, non-deploying); Table 2-1 "Number of engines: 1" | UG25 pp.5, 8; Table 2-1; WP-M | High |
| Vacuum thrust | 981 kN (220,500 lbf); throttle to 140,679 lbf. Older 934 kN figure (WP-FH, SF101) superseded | UG25 Table 2-1; WP-M | High |
| Burn time | 397 s | SX24; https://www.defenceaviation.com/spacex-falcon-9-second-stage-merlin-vacuum-engine-dragon-spaceship-specifications/ ; UC handout | High (as published) / Medium (mirrors) |
| Nozzle skirt material/cooling | Niobium alloy, radiatively cooled; extension "2.7-meter-long (9 ft)" (figure traces to SpaceX's 2009 Merlin Vacuum press release; 2009 test reported at https://www.satellitetoday.com/finance/2009/03/16/spacex-tests-merlin-vacuum-engine/ ; corroborated (Merlin-1C-Vac era) at https://en-academic.com/dic.nsf/enwiki/420986 ) | WP-M + trade press | High (material); Medium (2.7 m length — 1C-era figure; a later shortened extension variant −1.2 m also exists per Wikipedia) |
| Exit diameter — conflicting public estimates, no official figure | Range **≈ 2.5 m to ≈ 3.0 m**: (a) WEV-M lists MVac nozzle exit area 4.90 m² → dia ≈ 2.50 m; (b) the same page's throat area 0.042 m² × 165 → 6.93 m² → dia ≈ 2.97 m (the two are mutually inconsistent — noted verbatim); (c) hard upper bound: must fit inside the 3.66 m interstage (UG25). Claims up to 3.3 m circulate in forums (e.g. NSF Merlin thread https://forum.nasaspaceflight.com/index.php?topic=41014.380 ) but no accessible source stating 3.3 m was verified — **treat 3.3 m as unconfirmed**. CAD recommendation: ~2.5–3.0 m, default ≈ 2.9–3.0 m (consistent with 165:1 over the 16:1 sea-level bell) | WEV-M; UG25 | Low-Medium |
| MVac overall length | **No official figure.** Sourced anchors: niobium extension 2.7 m; Merlin 1C (sea level) overall 2.92 m. Community estimates ≈ 4–4.6 m circulate on forums (unverified, Cloudflare-blocked). **[DERIVED]** powerhead+chamber (~1.5–2 m) + 2.7 m radiative skirt → ≈ **4.2–4.7 m** plausible for CAD | WP-M + derived | Low |
| Ignition | "dual redundant triethylaluminum-triethylborane (TEA-TEB) pyrophoric igniters" (restart reliability) | UG25 p.8; WP-M | High |
| Attitude control | GN2 cold-gas ACS | UG25 | High |
| Propellants / cycle | LOX / RP-1 ("Liquid oxygen/kerosene (RP-1)"), gas-generator cycle, turbopump-fed, heated-helium tank pressurization | UG25 Table 2-1 | High |
| Stage length | ~12.6 m (unofficial estimate — see §1.2) | SF101 (* estimate); WP-FH | Medium-Low |
| Tank architecture | Shorter version of the first-stage tank, same materials/construction/tooling; LOX forward, RP-1 aft; 3 COPVs in the LOX tank (see §3) | UG25; §3 sources | High / Medium-High |
| Forward interface | Mated to interstage by mechanical latches at three points at the base of the S2 fuel tank; released by helium circuit; four pneumatic pushers incl. redundant center pusher (see §2.2) | UG25 §2 | High |
| Aft geometry note | The MVac nozzle/S2 aft section is recessed inside the interstage — accounts for the stage-length overlap in §1.2 | derived (dossier analysis) | — |

---

## 6. Known unknowns (explicitly NOT public — do not treat as fact; model generically and mark as estimated)

The following could not be sourced from any official or reliable public document in any of the three research passes:

- **Tank wall thickness** — not published for any core; the center core's walls are officially "thicker" (UG25) but by an unspecified amount.
- **Weld schedules / friction-stir welding parameters** — only the existence of FSW is public (UG25).
- **Separation system internals** — pusher mechanism dimensions, latch hardware geometry, frangible-seam internals, and attach-point hardware dimensions are not public; only counts, locations, and operating principle (pneumatic, helium-released) are (UG25).
- **Avionics** — box locations, counts, harness routing, and internal layout are not public.
- **COPV counts/placement details** — 3 COPVs in the second-stage LOX tank is public (AMOS-6 statements); first-stage COPV count, size, and placement are NOT publicly specified (community estimate only, Low).
- **Exact propellant feed routing** — only the double-wall LOX transfer tube through the RP-1 tank center is public (UG25); manifold, valve, and line routing are not.
- **Stage-by-stage length breakdown** — 42.6 m (booster) / 4.5 m (interstage) / 12.6 m (S2) are entirely unofficial and over-close the 70 m stack by ~2.8 m; anchor to official overall dimensions.
- **Outer-engine mounting circle diameter and bell spacing** — no official figure; §4.2 values are derived (Low).
- **Engine cant angle** — no official statement exists; model ≈ 0° from photo evidence (Low-Medium).
- **Octaweb internal structural geometry** — bay dimensions, member sizes; only "own metal bay" per engine and bolted Block 5 construction are public.
- **Grid-fin airfoil/lattice geometry** — model from photos; only overall museum-artifact envelope is grounded.
- **Raceway cross-section dimensions** — existence and black color are public; dimensions are not.
- **Interstage internal structure** — only the composite sandwich construction is public.
- **MVac exit diameter and overall length** — conflicting estimates only (§5); no official figure.
- **Base heat shield geometry** — titanium, bolt-on, locally water-cooled per Musk statements; panel layout/dimensions not public.
- **Dry/inert masses** — core ~25,600 kg (range 24–27 t) and S2 ~4,000 kg are community estimates (Low-Medium); never officially published.
- **Fairing mass** — ~1,750 kg is an SF101 estimate only (Low).
- **Landing-leg deployed span** — the 60 ft/18 m figure is an official claim surviving only via archive/citation trail (Medium); no live official URL.
- **Current payload-to-orbit detail** — UG25 says mass-to-orbit data "available upon request"; only marketing max-expendable figures are public.
- **"13.9 m" fairing** — not found in any official source; unsupported third-party figure.

Source-access caveats carried from the underlying reports: `forum.nasaspaceflight.com`, `forum.kerbalspaceprogram.com`, `forum.cosmoquest.org`, the ResearchGate figure page, GlobalSpec full text, and the Smithsonian NASM page were Cloudflare/robot-blocked to automated fetch (cited as pointers or via search-index snippets only); `spacelaunchreport.com` and `astronautix.com` were offline and not cited for values; the live spacex.com Falcon Heavy page is JS-rendered and was verified via archive captures and mirrors. Local extracted text of the official User's Guide (research artifact): `/private/tmp/claude-501/-Users-jakefitzgerald-robots-text-to-cad--claude-worktrees-reverent-hodgkin-5d1bb8/c1c63e8b-fd13-4694-bd14-77a418fe5d0d/scratchpad/users-guide.txt`.

---

## Sources

Deduplicated list of every URL cited in this dossier.

### Official SpaceX (including archives and mirrors of official material)

- https://www.spacex.com/assets/media/falcon-users-guide-2025-05-09.pdf
- https://www.spacex.com/vehicles/falcon-heavy/
- https://web.archive.org/web/20241226160703/https://www.spacex.com/vehicles/falcon-heavy/
- https://web.archive.org/web/20170531202158/http://www.spacex.com/falcon-heavy
- https://web.mit.edu/2.70/Reading%20Materials/SpaceX%20Falcon-users-guide-2021-09.pdf
- https://spacex.com.pl/files/2017-10/falcon-9-users-guide-rev-2.0.pdf
- https://www.spaceflightnow.com/falcon9/001/f9guide.pdf
- https://x.com/spacex/status/1114932679688900608
- https://spaceref.com/status-report/spacex-amos-6-anomaly-update-28-october-2016/
- https://www.flickr.com/photos/spacex/
- https://www.flickr.com/photos/spacex/40126461411/
- https://www.flickr.com/photos/spacex/25254688767
- https://www.flickr.com/photos/spacex/38583830575/
- https://www.flickr.com/photos/spacex/40628438523

### Federal, NASA, museum, academic

- https://www.faa.gov/sites/faa.gov/files/space/environmental/nepa_docs/SpaceX_Falcon_Program_Final_EA_and_FONSI.pdf
- https://www.faa.gov/sites/faa.gov/files/space/environmental/nepa_docs/FAA_FONSI_for_Falcon_Heavy_RTLS_at_LZ-1.pdf
- https://www.nasa.gov/blogs/commercialresupply/2014/04/18/meet-the-octaweb/
- https://www.jpl.nasa.gov/press-kits/europa-clipper/quick-facts/
- https://airandspace.si.edu/collection-objects/grid-fin-rocket-launch-vehicle-falcon-9/nasm_A20220607000
- https://www.researchgate.net/publication/318295483_A_Numerical_Study_on_the_Thermal_Loads_During_a_Supersonic_Rocket_Retro-Propulsion_Maneuver
- https://arc.aiaa.org/doi/10.2514/1.A34486
- https://www.researchgate.net/publication/294702811_Airware_2198_backbone_of_the_Falcon_family_of_SpaceX_launchers
- https://www.uc.edu/content/dam/refresh/cont-ed-62/olli/fall-23-class-handouts/SpaceX%204%20Falcon%20rockets%20and%20Engines.pdf

### Wikipedia / Wikimedia Commons

- https://en.wikipedia.org/wiki/Falcon_Heavy
- https://en.wikipedia.org/wiki/Falcon_9
- https://en.wikipedia.org/wiki/Falcon_9_Full_Thrust
- https://en.wikipedia.org/wiki/Falcon_9_Block_5
- https://en.wikipedia.org/wiki/Falcon_9_v1.1
- https://en.wikipedia.org/wiki/Grid_fin
- https://en.wikipedia.org/wiki/SpaceX_Merlin
- https://en.wikipedia.org/wiki/AMOS-6_(satellite)
- https://commons.wikimedia.org/wiki/Category:Falcon_Heavy
- https://commons.wikimedia.org/wiki/File:Falcon_Heavy_Demo_Mission_(39337245145).jpg

### Reputable explainers / trade press

- https://web.archive.org/web/20221201210405/https://spaceflight101.com/spacerockets/falcon-heavy/
- https://spacenews.com/musk-details-block-5-improvements-to-falcon-9/
- https://insights.globalspec.com/article/9968/block-5-how-spacex-re-engineered-its-falcon-9-rocket-to-endure-a-100-launch-lifespan
- https://www.space.com/40582-elon-musk-explains-spacex-falcon-9-block-5.html
- https://www.space.com/spacex-falcon-heavy-arabsat-6a-launch-landings-photos.html
- https://spaceflightnow.com/falcon9/009/140223legs/
- https://www.teslarati.com/spacex-starship-super-heavy-grid-fins-titanium-to-steel/
- https://www.teslarati.com/spacex-rocket-durability-leg-retraction/
- https://www.lightmetalage.com/news/industry-news/aerospace/how-light-metals-help-spacex-land-falcon-9-rockets-with-astonishing-accuracy/
- https://www.universetoday.com/articles/spectacular-video-captures-catastrophic-spacex-falcon-9-rocket-explosion-during-prelaunch-test
- https://www.nasaspaceflight.com/2016/09/falcon-9-explodes-amos-6-static-fire/
- https://www.americaspace.com/2017/01/02/spacex-closes-amos-6-investigation-aims-to-launch-10-satellites-next-sunday/
- https://www.satellitetoday.com/finance/2009/03/16/spacex-tests-merlin-vacuum-engine/
- https://interestingengineering.com/innovation/spacex-image-falcon-heavy-27-merlin-engines
- https://everydayastronaut.com/definitive-guide-to-starship/
- https://www.defenceaviation.com/spacex-falcon-9-second-stage-merlin-vacuum-engine-dragon-spaceship-specifications/
- https://en-academic.com/dic.nsf/enwiki/420986

### Community / aggregator / forum (pointer-only where fetch was blocked)

- https://www.wevolver.com/specs/merlin-engine-merlin-1d-falcon-9-falcon-heavy
- https://www.wevolver.com/specs/falcon-heavy-block-5
- https://www.thespacetechie.com/octaweb-structure/
- https://teamarcis.medium.com/grid-fins-8fc5175113d3
- https://www.eclipseaviation.com/how-spacex-landing-legs-work/
- https://www.quora.com/On-the-SpaceX-Falcon-9-how-many-engines-gimbal-for-directional-control-just-the-center-one-On-the-Heavy-will-it-be-all-three-center-engines
- https://github.com/KSP-RO/RealismOverhaul/blob/master/GameData/RealismOverhaul/Engine_Configs/Merlin1_Config.cfg
- https://forum.nasaspaceflight.com/index.php?topic=41947.0 (Cloudflare-blocked; pointer only)
- https://forum.nasaspaceflight.com/index.php?topic=44735.0 (Cloudflare-blocked; pointer only)
- https://forum.nasaspaceflight.com/index.php?topic=41014.380 (Cloudflare-blocked; pointer only)
- https://forum.kerbalspaceprogram.com/topic/95630-falcon-9-octaweb/ (Cloudflare-blocked; pointer only)