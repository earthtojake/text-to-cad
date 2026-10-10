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
