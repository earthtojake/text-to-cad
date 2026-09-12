## Superseding 225-pose repair handoff — 2026-09-06

The locally accepted final frame inputs are the two files below. Each contains one connected native solid, already placed in assembled neutral coordinates. Do not overwrite either immutable construction baseline (`imported/palm_frame_integration.step` or `palm_little_review.step`); the new model scripts intentionally read those older inputs.

| File under STEP/anthropomorphic_hand | Body / motion frame | SHA256 |
|---|---|---|
| `palm_main_final_rom_review.step` | `palm_metacarpal_truss` / `wrist_flexion` | `6c2e669df4f176c530c5b1c8623c861b942ca60d1e75cb346bd2548f6a32adf4` |
| `palm_little_comb_rom_review.step` | `fifth_metacarpal_cupping_truss` / `palm_cup` | `0cbb95eaad8463d34ce50a9eae879d01cb4c02adb56ae2531b01c2278477f015` |

Both final STEP files passed strict every-placement inspection with zero failures. Both passed all 48 full tendon routes at all 225 authored static packets: main used 298 exact native distances, little used 47, after conservative primitive screening and exact local-path caching. The limiting main clearance was 0.079994 mm. The new native MCP outlet combs also passed all 225 poses against their corresponding hosts: 660 unique main comb/body poses and 240 little poses, with zero solid overlap. Little's actual positive and negative bushings both have zero overlap; their flange seating faces retain intended zero-distance contact.

The four positive MCP seats retain complete annuli from radius 1.83 to 2.30 mm at Z12.5, thickness2 mm. Original rear rib landings remain outside those annuli, locally pocketed for tendon and comb motion. The CMC positive seat is now centered at (-35,36,9.3), thickness1.4, bore radius1.58, outer radius1.85. Its original upper loop and Z14 seat were removed. A 28 mm continuous circular rib, radius0.7 and minimum spine bend radius2.437, joins the earlier original branch at (-31.4101934,20.6770006,6.6334146). The complete new annuli are explicitly checked to remain on the largest connected frame. Main's tiny detached outer-rim machining chips were removed; none contained a bearing band. All negative seats, pad mounts, wrist-foot bores, cup bearings, and dorsal guide-clamp datums remain unchanged except the little negative-flange pocket below Z-17.5 within radius2.8.

Current certificates under `validation/anthropomorphic_hand/`:

- `palm_main_final_rom_strict.json`, `palm_little_comb_rom_strict.json`.
- `palm_main_accepted_routes_225_gate.json`, `palm_little_accepted_routes_225_gate.json`.
- `palm_main_final_comb_225_gate.json`, `palm_little_final_comb_225_gate.json`.
- `palm_little_final_bushings.json`.
- `palm_final_rom_placements.json` gives exact names, frames, hashes and bearing datums.

The focused additional native check completed before handoff: **PASS**, all225 packets,26 actual bodies,397 unique body poses,37 native intersections and zero overlaps. Its exec session was **99752**. Command `./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/validate_palm_cmc_added_rib_225.py`, log `/tmp/palm_cmc_added_rib_225_gate.log`, report `validation/anthropomorphic_hand/palm_cmc_added_rib_225_gate.json`. It compared the exact new CMC rib/sphere/seat addition, with its bore reopened, against the actual frozen CMC carrier and metacarpal plus all24 current CMC guide bodies across225 packets. This is an addition check; root's whole-frame/global rigid delta remains the final full-assembly proof. The voxel clouds used to optimize this rib are screening aids, not replacements for the native check.

Three final solid-mode renders were generated and visually reviewed: `tmp/anthropomorphic_hand/palm_final_rom_palmar.png`, `palm_final_rom_dorsal.png`, and `palm_final_rom_cmc_macro.png`. The open frame and continuous rib remain visible. The macro exposes a shoulder where the smaller replacement rib joins the original branch; no further cosmetic geometry changes were made after freezing these hashes.

The final native assembly should use the final filenames above directly. The older procedural factory and immutable baseline files are preserved as construction history; do not silently substitute them for the accepted overlays. Root owns the full assembly registry and its final overlay integration.

---

# Palm integration status

The rebuilt main palm is one connected native solid, replacing the earlier 21-body candidate. The fifth metacarpal is a separate accepted native solid. Construction uses 17 full-radius curved branches with open tendon corridors, original bearing seats, three dorsal branching nodes, local guide-jaw pockets and small route clearance reliefs. No tendon, pulley radius, phalanx length or joint datum changed.

`palm_frame_integration.py` publishes the reviewed geometry to `STEP/anthropomorphic_hand/imported/palm_frame_integration.step`. The implementation is `lib/palm_frame_candidate.py`; its fixed curved centerlines are in `lib/palm_frame_paths.py`. `lib/palm_frame.py` imports that declared native input for whole-hand builds. `palm_little_review.step` is the accepted fifth-ray input; use native imports to avoid repeating its expensive finish pass.

Validation under `validation/anthropomorphic_hand/`:

- `palm_accepted_strict.json`: main frame, one solid, zero strict every-placement/self-intersection failures after the final screw-head clearance pocket. `palm_final_pair_strict.json` independently validates the two re-exported main/fifth-ray occurrences with zero failures.
- `palm_rebuilt_route_audit.json`: all neutral groups and all 17 current wrist-pose packets screened; 31 near pairs checked against the actual native frame, zero contacts. Minimum native rope/liner surface gap is 0.099993 mm.
- `palm_rebuilt_local_motion_fits.json`: 455 component/pose fit checks, zero intersections. Includes little cup 0–25°, MCP carriers at their extrema, nine thumb metacarpal corner poses, 67 palm guide mounts, 24 CMC guide mounts, 336 driven-pulley/terminal occurrences and the wrist cradle. A final monotone clearance subtraction preserves preceding passes; the formerly contacting fixed CMC clamp screw was explicitly retested with 0.05 mm clearance.
- `palm_cmc_mount_motion.json`: all 18 moving CMC mounting bodies at nine yaw/flex corner poses, broad-phase pruning and 14 actual native near-pair checks, zero intersections.
- `palm_cmc_guide_envelope.json` and `palm_cmc_metacarpal_envelope.json`: all 17 full-radius ribs clear the guide and metacarpal surface sweeps over 5,751 thumb poses with conservative between-sample reserves. Minimum bounded gaps are 0.084498 mm and 0.082625 mm. These certificates cover the ribs; separate bearing bosses are covered by native fitted-body checks, not falsely included in the rib bound.
- `validate_palm_final_relief.py`: final fixed CMC clamp screw has 0.05 mm gap; both full wrist mounting annuli R1.65–1.85 through the complete 3.2 mm thickness have zero missing volume.
- `palm_little_smooth_strict.json`: fifth metacarpal, one solid, zero strict failures. `palm_little_smooth_yaw_proof.json`: 102 native yaw reaction-liner checks, minimum gap 0.249558 mm. `palm_little_all_routes.json`: all neutral/current wrist paths clear.
- `palm_cradle_final_strict.json`: wrist cradle strict pass after the negative shaft-head withdrawal relief and palm mounting-seat correction.

The main-frame attachment datums remain world-space:

| Interface | Datum and physical seat |
| --- | --- |
| Three MCP supports | XY (−36,101), (−12,105), (12,100); Z +12.5/−16.5; bore R2.53, seat thickness 2 mm, outer R3.75 |
| Thumb CMC supports | XY (−35,36); Z +14/−18; bore R2.53, seat thickness 2 mm, outer R4.15 |
| Fixed cup supports | X22,Z0,Y35/75; bore R2.53, axial thickness 2.4 mm |
| Fifth-ray moving cup eyes | X22,Z0,Y38.2/71.8; original D bores R1.03, world +X flat at X22.75 |
| Wrist feet | X±24,Y14,Z−10.2; thickness 3.2 mm; bore R1.65, complete R1.85 inner seat annulus retained |
| Wrist cradle shoes | Top Z−12.2, bottom Z−14.6; 0.4 mm spacer gap to palm foot underside Z−11.8 |
| Palm pad mounts | (−24,55,11.5), (15,53,11.5), (−4,66,11.5); R0.8 bores, 2.2 mm thickness, outer R2.5 |
| Parent CMC inlet comb | Exact original dorsal rib patch; local CMC (2.98,−8,−17.98), world XY approximately (−27.235965,32.450324), 4×1 mm clamp footprint |

The wrist cradle's lateral branch is relieved by a radius4.85 cylinder ending exactly at the outer eye plane X−21.2. It clears the radius4.8 headed shaft without changing the D eye or bearing datums. Its palm-shoe branches are trimmed only above the actual shoe top so the palm's closed bolt-seat annuli remain intact.

Two opposing rendered presentation views are `tmp/anthropomorphic_hand/palm_rendered_iso.png` and `palm_rendered_dorsal.png`; the separate fifth-ray view is `palm_little_threequarter.png`. A remaining radial pad-seat top display speckle is documented in root BUG016: strict native validation passes, and native face inspection finds one planar top face with two boundary wires, not overlapping faces. Its renderer cause remains unconfirmed. It has not been hidden by deleting contact geometry. Whole-assembly aesthetic acceptance belongs to the fresh independent critic.

## Accepted removable palm hardware

`palm_hardware_review.step` contains15 final native bodies, SHA256 `39d5cfa215f13f86478b86260190fe3190d1bccb108d59cc8aaf7e5baabeb67d`. `validation/anthropomorphic_hand/palm_hardware_placements.json` provides every exact occurrence name, frame, system and kind. `lib/palm_hardware.py:palm_hardware_bodies()` imports this declared input for whole-hand builds. All bodies are already in neutral assembled world coordinates and move with `wrist_flexion`.

The three Ø5.4mm silicone caps have continuous contact faces and blind underside screw-head pockets. Removing a replaceable cap exposes its M1.6 socket screw. The screw seats atZ13.4 on a Ø4.6mm carrier and engages the existing nominal Ø1.6 threaded palm bore; the smooth CAD thread envelope is documented in source. Carrier underside isZ12.6 and pad crownZ14.7. Each wrist attachment has an M3 screw with R2.2 low head at the originalZ−8.6 seat, a0.4mm annular steel spacer and a full R1.65 sleeve insert in the cradle shoe. The ulnar insert's R1.85 flange is0.2mm thick, ending atZ−14.8; the radial R2.2 flange is0.4mm thick. Both retain complete sleeve engagement. The insert flanges conform to the actual cradle underside.

`palm_hardware_strict.json` passes15 every-placement checks. `palm_hardware_fits.json` records57 actual own/host/guide near-pair Booleans with zero intersections and18,930 tendon/body pairs screened,167 exact native distances, zero contacts, minimum0.093983mm gap. The final flange-only subtraction preserves preceding passes and its four limiting wrist poses were explicitly retested in `palm_final_insert_clearance.json`, minimum0.140640mm. `palm_hardware_cmc_envelope.json` bounds all15 complete hardware bodies against the5,751-pose CMC sweeps, minimum1.974mm to moving guides and3.545mm to the metacarpal.

The shared palm-cup drive-mouth clamp was relocated by the guide specialist onto the existing pad_2 rib at (−2.644829653,67.040070426,7.000320874), side+X, with both guide mouths and all tendon controls unchanged. The hardware audit checked the resulting `wrist_guide_mounts_review.step` SHA256 `5d731a96ee067c34961533972b007b990bf1d94de3cc561477705f0f100ab703`. The guide specialist owns its strict, attachment and225-route certificates.

The accepted one-body cradle input is `palm_cradle_clearance_review.step`, SHA256 `8f5f9beb5456a6df38ad07609f71f596935806e2309a6b5befc56159f389e525`. Final source-driven context is `palm_hardware_context_review.py`; its authored solid presentation/macro job is `palm_hardware_render_job.json`. The four images are `tmp/anthropomorphic_hand/palm_hardware_palmar.png`, `palm_hardware_dorsal.png`, `palm_hardware_pad_macro.png`, and `palm_hardware_wrist_macro.png`.
