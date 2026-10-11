# Materials

Isotropic, linear, room temperature. Name one in the study's `material`, or
give the numbers yourself. These are textbook values for a first pass; a
study that matters uses the supplier's datasheet through the object form
(`{"name": "...", "E_MPa": ..., "nu": ..., "yield_MPa": ...}`).

| name (and aliases) | E (MPa) | ν | yield (MPa) | density (t/mm³) | notes |
| --- | --- | --- | --- | --- | --- |
| `steel` (`mild-steel`) | 200 000 | 0.30 | 250 | 7.85e-9 | generic structural / low-carbon |
| `stainless-304` (`304`, `stainless`, `ss304`) | 193 000 | 0.29 | 215 | 8.00e-9 | annealed |
| `aluminum-6061-t6` (`6061`, `6061-t6`, `aluminum`, `aluminium`) | 68 900 | 0.33 | 276 | 2.70e-9 | the default aluminium |
| `aluminum-7075-t6` (`7075`, `7075-t6`) | 71 700 | 0.33 | 503 | 2.81e-9 | |
| `titanium-6al-4v` (`titanium`, `ti-6al-4v`) | 113 800 | 0.342 | 880 | 4.43e-9 | |
| `brass` | 97 000 | 0.31 | 310 | 8.50e-9 | C36000, half hard |
| `abs` | 2 200 | 0.35 | 40 | 1.04e-9 | injection moulded; printed parts are weaker and anisotropic |
| `pla` | 3 500 | 0.36 | 60 | 1.24e-9 | printed; treat yield as an upper bound |
| `petg` | 2 100 | 0.38 | 50 | 1.27e-9 | printed |
| `nylon-pa12` (`nylon`, `pa12`) | 1 700 | 0.40 | 48 | 1.01e-9 | SLS / MJF |

Names are case-insensitive; spaces and underscores read as hyphens.

For printed polymers the model's assumptions are loose: layer adhesion,
infill and orientation change stiffness and strength by a factor of two or
more. Say so, and use a larger safety factor than for a machined metal part.

## Strength, fatigue and heat

The properties other analyses read. Ultimate strength and fatigue (`fatigue`,
Goodman and the S-N line), conductivity (`thermal`, `thermal_transient`,
`thermal_stress`), expansion (`thermal_stress`) and specific heat
(`thermal_transient`). Override any of them in the material object:
`uts_MPa`, `endurance_MPa` with `endurance_cycles` (also accepted as
`fatigue_strength_MPa` and `fatigue_cycles`), `conductivity_W_mK`,
`expansion_per_K` (per kelvin, so `23.6e-6`), `specific_heat_J_kgK`, and for
`nonlinear` the plastic tangent `plasticity: {"tangent_MPa": ...}` or a
hyperelastic `hyperelastic: {"model": "neo_hookean", "mu_MPa": ..., "bulk_MPa": ...}`.
An analysis that needs a value the material lacks says which key to add.

| name | UTS (MPa) | endurance (MPa) | at cycles | k (W/(m·K)) | α (1e-6/K) | c (J/(kg·K)) | sources |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `steel` | 400 | 200 | 1e6 | 50 | 11 | 470 | [MatWeb A36], [MakeItFrom A36], [Shigley] |
| `stainless-304` | 505 | 240 | 1e7 | 16.2 | 17.3 | 500 | [ASM 304], [NiDI 304 fatigue] |
| `aluminum-6061-t6` | 310 | 96.5 | 5e8 | 167 | 23.6 | 896 | [ASM 6061-T6] |
| `aluminum-7075-t6` | 572 | 159 | 5e8 | 130 | 23.6 | 960 | [ASM 7075-T6] |
| `titanium-6al-4v` | 950 | 510 | 1e7 | 6.7 | 8.6 | 526 | [ASM Ti-6Al-4V] |
| `brass` | 393 | 138 | 1e8 | 116 | 20.5 | 377 | [CDA C36000] |
| `abs` | 43 | none | none | 0.17 | 90 | 1200 | [Novodur 433], [Röchling ABS] |
| `pla` | 60 (unverified) | none | none | 0.13 | 85 | 1800 | [Prusament PLA], [MakeItFrom PLA], [Omnexus CLTE] |
| `petg` | 50 | none | none | 0.20 | 68 | 1100 | [Prusament PETG], [HIPEX G PETG] |
| `nylon-pa12` | 48 | none | none | 0.144 | 109 | 2350 | [EOS PA 2200], [EOS PA 2200 2010] |

Notes, value by value:

- `steel` is generic structural steel, read as ASTM A36. UTS 400 MPa is A36's
  minimum (MatWeb: 400 to 550). The endurance limit is Shigley's rule
  Se' = 0.5·Sut (200 MPa, which MakeItFrom also gives), taken at the rule's
  usual 1e6 cycles; the page fetched did not state the cycle count. k, α and c
  are MakeItFrom's A36 values (MatWeb's A36 bar sheet has no thermal data).
- `stainless-304`, annealed: UTS, k (0 to 100 °C), α (0 to 100 °C) and c from
  ASM. ASM gives no fatigue value; 240 MPa at 1e7 reversed-bending cycles is
  from a secondary page citing INCO/NiDI publication 2978 (MakeItFrom gives
  210 MPa), so treat it as approximate.
- `aluminum-6061-t6` and `aluminum-7075-t6`: every value from ASM; the
  endurance is the R. R. Moore fully reversed strength at 5e8 cycles
  (aluminium has no true endurance limit). α over 20 to 100 °C.
- `titanium-6al-4v`, annealed grade 5: every value from ASM; 510 MPa at 1e7 is
  unnotched (ASM gives 240 MPa notched, Kt 3.3).
- `brass`, C36000 half hard: Copper Development Association, rod under 12 mm,
  the row that carries the fatigue strength (393 MPa UTS, 138 MPa at 1e8).
  Thicker rod is 380 to 400 MPa.
- `abs`: UTS 43 MPa is Novodur 433's tensile yield stress (ISO 527), the
  strength ABS datasheets quote; k, α and c are Röchling SustaABS's (NETZSCH
  gives c 1260 to 1680 J/(kg·K), α 80 to 100e-6/K).
- `pla`: Prusament's PLA datasheet gives tensile yield only (57 MPa filament,
  51 MPa printed flat, 59 MPa upright) and no thermal properties. UTS 60 MPa is
  the table's starting value and is unverified. k and c from MakeItFrom; α
  from Omnexus's CLTE table (85e-6/K).
- `petg`: UTS 50 MPa is Prusament PETG's tensile yield printed upright (47 flat).
  Prusament gives no thermal properties; k, α and c are from the HIPEX G PETG
  sheet (Eastman Eastar 6763 gives k 0.21, α 51e-6/K, c 1300 at 60 °C).
- `nylon-pa12`, EOS PA 2200 (SLS): UTS 48 MPa in X/Y (42 in Z) from EOS's
  current datasheet; k (0.144 across the layers, 0.127 along them), α and c
  from EOS's 2010 product information.

### Why some values are none

- Endurance, for `abs`, `pla`, `petg` and `nylon-pa12`: polymers have no endurance limit, and their fatigue strength depends on frequency, temperature, moisture and (printed) layer orientation; give the grade's S-N point from its datasheet

### Sources

- [MatWeb A36]: https://web.archive.org/web/20240902143212id_/https://matweb.com/search/DataSheet.aspx?MatGUID=d1844977c5c8440cb9a3a967f8909c3a
- [MakeItFrom A36]: https://makeitfrom.com/material-properties/ASTM-A36-SS400-S275-Structural-Carbon-Steel
- [Shigley]: Shigley's Mechanical Engineering Design, chapter 6 (Se' = 0.5·Sut for Sut up to 1400 MPa); solutions manual https://www.secs.oakland.edu/~latcha/ME4300/SM_PDF/CH6.pdf
- [ASM 304]: https://web.archive.org/web/20250327094625id_/https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=mq304a
- [NiDI 304 fatigue]: https://tubingchina.com/Fatigue-Properties-and-Endurance-Limits-of-Stainless-Steel.htm (citing INCO/NiDI publication 2978)
- [ASM 6061-T6]: ASM Aerospace Specification Metals, asm.matweb.com bassnum=ma6061t6, read in the printout https://quickparts.com/wp-content/uploads/2024/05/Aluminum-6061.pdf
- [ASM 7075-T6]: https://web.archive.org/web/20241216135852id_/https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=MA7075T6
- [ASM Ti-6Al-4V]: https://web.archive.org/web/20241204175911id_/https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=MTP641
- [CDA C36000]: https://alloys.copper.org/alloy/C36000
- [Novodur 433]: INEOS Styrolution Novodur 433 ABS datasheet, https://www.protolabs.com/media/0q3bj4w5/id-pending-novodur-433-abs.pdf
- [Röchling ABS]: https://www.roechling.com/pl/industrial/materialy/thermoplastics/engineering-plastics/abs/sustaabs-grey-591062
- [Prusament PLA]: Prusament PLA technical data sheet v1.1 (2022-07-27), linked from https://prusament.com/materials/pla/
- [MakeItFrom PLA]: https://makeitfrom.com/material-properties/Polylactic-Acid-PLA-Polylactide
- [Omnexus CLTE]: https://web.archive.org/web/20240406205455id_/https://omnexus.specialchem.com/polymer-property/coefficient-of-linear-thermal-expansion
- [Prusament PETG]: https://storage.googleapis.com/prusa3d-content-prod-14e8-wordpress-prusament-prod/2023/10/9f8d2165-tds_prusament-petg_n_en.pdf
- [HIPEX G PETG]: https://pim.igepa.nl/Plaatmateriaal/Kunststof/PET-G/Technische%20datasheet%20HIPEX%20G%20PETG.pdf
- [EOS PA 2200]: https://www.eos.info/polymer-solutions/polymer-materials/data-sheets/mds-pa-2200
- [EOS PA 2200 2010]: https://www.sculpteo.com/media/imagecontent/PA2200_Product_information_03-10_en.pdf

## Fracture

What `fracture` reads: the plane-strain fracture toughness K_IC (the crack grows
where its stress intensity K reaches it) and, for crack growth, Paris's law
da/dN = C (ΔK)^m. Override them in the material object:
`fracture_toughness_MPa_sqrt_m`, `paris_C` (m per cycle, with ΔK in MPa√m) and
`paris_m`. Room temperature, in air. A value no source gives for the grade is
none, and a study that needs it asks for it.

| name | K_IC (MPa√m) | Paris C (m/cycle) | Paris m | sources |
| --- | --- | --- | --- | --- |
| `steel` | none | 6.9e-12 | 3.0 | [Norton Paris] (ferritic-pearlitic steels) |
| `stainless-304` | none | 5.6e-12 | 3.25 | [Norton Paris] (austenitic stainless steels) |
| `aluminum-6061-t6` | 29 | none | none | [ASM 6061-T6 e] (T-L) |
| `aluminum-7075-t6` | 20 | none | none | [ASM 7075-T6] (S-L, the lowest of three) |
| `titanium-6al-4v` | 75 | none | none | [ASM Ti-6Al-4V] |
| `brass` | none | none | none | |
| `abs` | none | none | none | |
| `pla` | none | none | none | |
| `petg` | none | none | none | |
| `nylon-pa12` | none | none | none | |

Notes, value by value:

- `aluminum-7075-t6`: ASM gives K_IC 20 MPa√m in the S-L direction, 25 in T-L
  and 29 in L-T. The table takes the lowest, 20; a crack whose orientation in
  the plate or bar is known may use its own direction's value.
- `aluminum-6061-t6`: ASM gives 29 MPa√m, T-L orientation.
- `titanium-6al-4v`, annealed grade 5: ASM gives 75 MPa√m (no orientation stated).
- `steel` and `stainless-304`: Barsom's Paris fits for ferritic-pearlitic and
  austenitic stainless steels, from Norton's Machine Design table 6-2. The SI
  column there is labelled mm/cycle, but its U.S. column (3.60e-10 in/cycle,
  ksi√in, for ferritic-pearlitic) converts to 6.9e-12 m/cycle with ΔK in MPa√m,
  so C is per metre, as Barsom gives it. They are fits over many steels: a
  study that matters uses the grade's own da/dN data.
- K_IC is a plane-strain value: thinner sections are tougher (plane stress),
  so it is conservative for thin parts.

### Why some values are none (fracture)

- K_IC, for `steel`, `stainless-304` and `brass`: a tough, ductile metal like this tears plastically before a valid plane-strain K_IC can be measured, and no source cited here gives one for the grade; give fracture_toughness_MPa_sqrt_m from the supplier's test (or a J_IC converted to K), and treat LEFM as an approximation for it
- Paris C and m, for the aluminium alloys, titanium and `brass`: no source cited here gives Paris constants for this grade; give paris_C (m/cycle, ΔK in MPa√m) and paris_m from the alloy's crack-growth (da/dN) data at the load ratio it sees
- Every fracture value, for `abs`, `pla`, `petg` and `nylon-pa12`: a polymer's (and a printed part's) toughness and crack growth depend on grade, temperature, rate, moisture and layer orientation; give fracture_toughness_MPa_sqrt_m and paris_C, paris_m from the grade's own test data

### Sources (fracture)

- [Norton Paris]: Robert L. Norton, Machine Design: An Integrated Approach, 6th edition, table 6-2 (data from Barsom), https://designofmachinery.com/wp-content/uploads/2021/02/Chap-06-MD-6ed-p.360-361.pdf
- [ASM 6061-T6 e], [ASM 7075-T6] and [ASM Ti-6Al-4V]: as listed under the electrical and the strength sources (asm.matweb.com).

## Electrical and magnetic

What `electromagnetic` reads: resistivity (steady current; a material under
1 ohm·m is a conductor, an equipotential in electrostatics; over 1000 ohm·m
it carries no current), relative permittivity (electrostatics, dielectrics
only) and relative permeability (magnetostatics). Override them in the material
object: `resistivity_ohm_m`, `relative_permittivity`, `relative_permeability`.
Room temperature, DC (permittivity at the frequency given). The air around
the parts is eps_r 1.00059 [HyperPhysics dielectrics], mu_r 1.00000037
[EngToolbox permeability]; vacuum eps0 8.8541878188e-12 F/m [NIST eps0] and
mu0 1.25663706127e-6 N/A² [NIST mu0]. Dry air breaks down at about 3 kV/mm
[Physics Factbook air], less at sharp edges and over long gaps.

| name | resistivity (ohm·m) | eps_r | mu_r | sources |
| --- | --- | --- | --- | --- |
| `steel` | 1.4368e-7 | none | none | [MakeItFrom A36] (12 % IACS), [EngToolbox permeability] |
| `stainless-304` | 7.2e-7 | none | 1.008 | [ASM 304] |
| `aluminum-6061-t6` | 3.99e-8 | none | 1.000022 | [ASM 6061-T6 e], [EngToolbox permeability] |
| `aluminum-7075-t6` | 5.15e-8 | none | 1.000022 | [ASM 7075-T6], [EngToolbox permeability] |
| `titanium-6al-4v` | 1.78e-6 | none | 1.00005 | [ASM Ti-6Al-4V] |
| `brass` | 6.6312e-8 | none | 1.0 (unverified) | [CDA C36000 e] (26 % IACS) |
| `abs` | 1e13 | 3.1 | 1.0 (unverified) | [Röchling ABS], [Novodur P2H-AT] |
| `pla` | 1e14 (unverified) | 3.0 (unverified) | 1.0 (unverified) | [PLA printed permittivity] |
| `petg` | 1e13 | 2.6 | 1.0 (unverified) | [Eastar 6763] |
| `nylon-pa12` | 1e12 | 3.8 | 1.0 (unverified) | [EOS PA 2200 e], [Professional Plastics] |

Notes, value by value:

- Resistivity from % IACS is 1.7241e-8 ohm·m / (% IACS / 100): A36 12 % gives
  1.4368e-7, C36000 26 % gives 6.6312e-8. ASM's metals are given in ohm·cm
  (x 0.01).
- `aluminum-*`: the permeability is Engineering Toolbox's for aluminium, not
  for the alloy. `titanium-6al-4v`: ASM's 1.00005 at 1.6 kA/m.
- `brass`: no brass permeability was found; copper's is 0.999994
  ([EngToolbox permeability]), so 1.0 is used, unverified.
- `abs`: Röchling SustaABS gives 10^15 ohm·cm and eps_r 3.1 (IEC 60250, frequency
  not stated); INEOS Novodur P2H-AT gives eps_r 2.9 at 1 MHz and > 1e13 ohm·m.
- `pla`: no datasheet with PLA's resistivity or permittivity could be fetched;
  1e14 ohm·m and 3.0 are typical polyester values, unverified. A study of 3D
  printed PLA measured eps_r 1.78 to 2.81, falling with infill
  ([PLA printed permittivity]).
- `petg`: Eastman Eastar 6763, 10^15 ohm·cm (ASTM D257) and eps_r 2.6 at 1 kHz
  (2.4 at 1 MHz).
- `nylon-pa12`: EOS PA 2200 gives 10^13 to 10^15 ohm·cm and eps_r 3.8 at 1 kHz,
  both strongly dependent on temperature and humidity; 1e12 ohm·m is the
  middle of that range.
- Polymers' permeability: 1.0 for all four, the usual assumption for a
  non-magnetic plastic; no source states it for these grades (Engineering
  Toolbox gives 1 for PTFE), so it is unverified.

### Why some values are none (electrical)

- Permittivity, for every metal: a metal conducts, so it has no permittivity: in an electric study it is an equipotential (one voltage throughout), held or floating
- Permeability, for `steel`: structural steel is ferromagnetic: its permeability depends on the field and saturates (Engineering Toolbox lists about 100 for carbon steel); give relative_permeability from the grade's B-H curve at the field expected

### Sources (electrical)

- [NIST eps0]: https://physics.nist.gov/cgi-bin/cuu/Value?ep0
- [NIST mu0]: https://physics.nist.gov/cgi-bin/cuu/Value?mu0
- [HyperPhysics dielectrics]: http://hyperphysics.phy-astr.gsu.edu/hbase/Tables/diel.html ("Air(1 atm) 1.00059")
- [Physics Factbook air]: https://hypertextbook.com/facts/2000/AliceHong.shtml ("approximately 3 kV/mm")
- [EngToolbox permeability]: https://www.engineeringtoolbox.com/permeability-d_1923.html
- [ASM 6061-T6 e]: https://web.archive.org/web/20241217181844id_/https://asm.matweb.com/search/SpecificMaterial.asp?bassnum=MA6061T6
- [CDA C36000 e]: https://web.archive.org/web/20260504212850id_/https://alloys.copper.org/alloy/C36000
- [Novodur P2H-AT]: https://plasticker.de/docs/recybase/35956_1785994693.pdf
- [PLA printed permittivity]: https://pmc.ncbi.nlm.nih.gov/articles/PMC9942642/
- [Eastar 6763]: https://eastman.com/content/dam/eastman/corporate/en/literature/m/mbs80.pdf (table 3)
- [EOS PA 2200 e]: https://www.amf.uzh.ch/dam/jcr:59a8b14a-c212-4693-8443-d5e543aeabe2/Material-Data-PA2200-ENGLISH.pdf
- [Professional Plastics]: https://www.professionalplastics.com/professionalplastics/ElectricalPropertiesofPlastics.pdf
- [MakeItFrom A36], [ASM 304], [ASM 7075-T6], [ASM Ti-6Al-4V] and [Röchling ABS]: as listed under Sources below.

## Orthotropic materials

A material stiffer one way than another (unidirectional carbon or glass in a solid block, wood, a
part treated as directional) takes an `orthotropic` block in its material object: nine constants
and, optionally, its axes. The table has no orthotropic entries: take the numbers from the
material's datasheet or test data, never make them up.

```json
{"name": "UD carbon block", "density_t_per_mm3": 1.6e-9, "yield_MPa": 60,
 "orthotropic": {"E1_MPa": 135000, "E2_MPa": 10000, "E3_MPa": 10000,
                 "nu12": 0.3, "nu13": 0.3, "nu23": 0.45,
                 "G12_MPa": 5000, "G13_MPa": 5000, "G23_MPa": 3500,
                 "axes": [[1, 0, 0], [0, 1, 0]]}}
```

- `E1_MPa`, `E2_MPa`, `E3_MPa`: the moduli along material directions 1, 2 and 3.
- `nu12`, `nu13`, `nu23`: ν_ij is the contraction along j under a stress along i (so ν21 =
  ν12 E2 / E1). They must be physically possible: |ν_ij| < √(E_i / E_j), and the compliance
  positive definite; an impossible set is refused with a sentence saying so.
- `G12_MPa`, `G13_MPa`, `G23_MPa`: the shear moduli.
- `axes` (optional): directions 1 and 2 in the part's coordinates, perpendicular; 3 is 1 × 2.
  Default: the global X and Y axes.
- `E_MPa` and `nu` are not needed (E1 and ν12 fill them). `yield_MPa` is optional, and needed only for a `stress` check (judged, as for
  any material, by von Mises against it: a rough measure for a directional material; say so).

Where it is used: every analysis that assembles the solid stiffness takes the full 6 × 6 tensor
(rotated into the part's axes): `static`, `modal`, `buckling`, `harmonic`, `random_vibration`,
`shock`, `transient`, `thermal_stress` (with the isotropic expansion the material gives) and the
static solve under `fatigue` and `drop`. `nonlinear`, `impact`, `creep`, `contact` and `bolt` treat
every material as the same in every direction, so they refuse an orthotropic one with a sentence
naming the analyses that take it. The symmetry ladder rung cuts an
orthotropic part only across a plane normal to one of its material directions.

A laminate (plies at angles) is not one orthotropic material: use the `composite` analysis
([composite.md](composite.md)), whose ply materials (`laminae`) are given as E1, E2, ν12, G12
and strengths.

## Piezoelectric ceramics

What `piezo` reads ([piezo.md](piezo.md)): a `piezo` block in the material, the linear
constants in the stress-charge form, in the ceramic's own axes with 3 along the poling.
Three poled PZT ceramics are in a table of their own (they are not in the tables
above, which every other analysis reads): name one in `material` (or a part's).

| ceramic (name) | c11E | c12E | c13E | c33E | c44E | c66E | e31 | e33 | e15 | ε11S/ε0 | ε33S/ε0 | ρ (kg/m³) | sources |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PZT-4 (`pzt-4`) | 139 | 77.8 | 74.3 | 115 | 25.6 | 30.6 | −5.2 | 15.1 | 12.7 | 730 | 635 | 7500 | [TP-226] section III |
| PZT-5A (`pzt-5a`) | 121 | 75.4 | 75.2 | 111 | 21.1 | 22.6 | −5.4 | 15.8 | 12.3 | 916 | 830 | 7750 | [TP-226] section III |
| PZT-5H (`pzt-5h`) | 126 | 79.5 | 84.1 | 117 | 23.0 | 23.5 | −6.55 | 23.3 | 17.0 | 1700 | 1470 | 7500 | [TP-226] section III |

Stiffness in GPa (TP-226 lists them in 10¹⁰ N/m²), e in C/m², permittivity at constant
strain over ε0. Also accepted: `pzt4`, `pzt5a`, `pzt5h`, and the US Navy types `navy-i`
(PZT-4), `navy-ii` (PZT-5A) and `navy-vi` (PZT-5H).

Notes:

- Every number above was read from TP-226's own table (a copy is linked below),
  checked on 2026-10-10. TP-226 also lists derived values; the table's constants
  reproduce its d33, d31, k_t, k33 and ε33T within 2 % (a test holds them to it):
  PZT-5A d33 373 pC/N (TP-226: 374), ε33T/ε0 1704 (1700), k_t 0.484 (0.486).
- TP-226's c66 for PZT-5A (2.26) and PZT-5H (2.35) are not exactly (c11 − c12)/2
  (2.28 and 2.325): its own rounding. The table keeps TP-226's numbers, so the
  ceramic is very slightly anisotropic about its poling axis.
- No yield strength: a ceramic is brittle. A `stress` check needs `yield_MPa` in
  the material object; TP-226 section V gives a static tensile strength of
  11 000 psi (76 MPa) for all three, and a dynamic (peak) one of 3 500 psi (24 MPa)
  for PZT-4 and 4 000 psi (28 MPa) for PZT-5A and PZT-5H: use the dynamic one for a
  part that is driven.
- Room temperature, low field, freshly poled. Batches vary by several percent, and
  the constants age (TP-226 section IV: PZT-4's k_p falls 1.7 % per decade of time, PZT-5A's
  and PZT-5H's 0.2 % or less).
  A study that matters uses the supplier's datasheet, in the block below.

A ceramic of your own takes the full matrices (from the supplier's datasheet;
never invent them):

```json
{"name": "my PZT", "density_t_per_mm3": 7.8e-9, "yield_MPa": 24,
 "piezo": {"cE_GPa": [[121, 75.4, 75.2, 0, 0, 0], [75.4, 121, 75.2, 0, 0, 0], [75.2, 75.2, 111, 0, 0, 0],
                      [0, 0, 0, 21.1, 0, 0], [0, 0, 0, 0, 21.1, 0], [0, 0, 0, 0, 0, 22.6]],
           "e_C_m2": [[0, 0, 0, 0, 12.3, 0], [0, 0, 0, 12.3, 0, 0], [-5.4, -5.4, 15.8, 0, 0, 0]],
           "epsS_rel": [[916, 0, 0], [0, 916, 0], [0, 0, 830]],
           "poling": [0, 0, 1]}}
```

- `cE_GPa`: 6 × 6 stiffness at constant field, Voigt order 11, 22, 33, 23, 13, 12
  (engineering shears), symmetric and positive definite.
- `e_C_m2`: 3 × 6 piezoelectric stress constants (rows: field along 1, 2, 3).
- `epsS_rel`: 3 × 3 permittivity at constant strain, over ε0; symmetric, positive definite.
- `poling` (optional, default `[0, 0, 1]`): the poling direction in the part's
  axes. A table ceramic turned over is `{"name": "pzt-5a", "piezo": {"poling": [0, 0, -1]}}`:
  every key left out is the table's.
- `density_kg_m3` (optional): used when the material gives no `density_t_per_mm3`.
- `E_MPa`, `nu` and `yield_MPa` are not needed: E and ν are the compliance's own
  (1/s11 and −s12/s11).

A datasheet in the strain-charge form (s^E, d, ε^T) converts: c^E = (s^E)⁻¹,
e = d c^E, ε^S = ε^T − d eᵀ.

### Sources (piezoelectric)

- [TP-226]: D. Berlincourt, H. H. A. Krueger, revised by C. Near, "Properties of Morgan
  Electro Ceramic Ceramics", Morgan Electro Ceramics Technical Publication TP-226,
  section III (typical room temperature data, low signal) and section V (high signal:
  strengths); copy at https://www.ultrasonic-resonators.org/misc/references/articles/Berlincourt__'Properties_of_Morgan_Electro_Ceramic_Ceramics'_(Morgan_Technical_Publication_TP-226).pdf
