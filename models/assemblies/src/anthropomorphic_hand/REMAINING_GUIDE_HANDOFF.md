# Remaining guide-mouth mounts

All public factories return already assembled `(shape, frame, system, kind)` tuples. Source coordinates, guide datums, and all tendon paths are unchanged. Each disconnected solid remains its own named body with modeled fastener attachment.

## Accepted and frozen

| Factory | Mouths | Bodies | Frozen STEP |
|---|---:|---:|---|
| `lib.yaw_guide_mounts.yaw_reaction_mounts()` | 8 | 64 | `yaw_reaction_mounts_review.step` |
| `lib.thumb_remaining_mounts.thumb_downstream_mounts()` | 8 | 42 | `thumb_downstream_mounts_review.step` |
| `lib.wrist_guide_mounts.wrist_guide_mounts()` | 6 | 29 | `wrist_guide_mounts_review.step` |
| `lib.cup_guide_mounts.cup_guide_mounts()` | 18 | 33 | `cup_guide_mounts_review.step` |
| `lib.thumb_remaining_mounts.thumb_base_mounts()` | 16 | 52 | `thumb_base_mounts_review.step` |

STEP directory: `models/assemblies/STEP/anthropomorphic_hand`.

SHA256:

- yaw: `4d438e71c57ad6246232f4c27d2b0d0e87555a2b5bc3e648f611ec000577f2cc`
- thumb downstream: `7a9650b896d02e981494f99dc75d225a855e4be5dab3f2ec3bb7780ba70066b8`
- thumb base: `851b66ea1dbcce1eb5d7a664a8a3e6130168d3fe606f35f8b4d1ea510dee18dd`
- cup: `815e69d771c985320c4814d18db5bcbf33db645e3a362aef652fb86f877dd99d`
- wrist: `66d67434bc744fdf80eddec71a6776a9dceeacb721915dbe9d448dd548a93c65`

Each subgroup passes strict every-placement validation, same-group native mutual interference, complete native attachment graph, exact same-frame host interference, and all225 recorded route poses. Nominal screw radial fit is0.020mm, contact-graph tolerance0.025mm. The full-assembly gate remains root-owned.

Reports are in `models/assemblies/validation/anthropomorphic_hand`: prefixes `yaw_reaction`, `thumb_downstream`, `wrist_guide`, `cup_guide`, and `thumb_base`, with suffixes `_validate.json`, `_mutual.json`, `_attachment_report.json`, and `_route_report.json`. Final route packet source fingerprint is `2512eea4ea7ec67076c60c5ebe4d297a6102fa51f1f0b191dda9fb6d23a9aaff`.

Label-to-frame mapping is implemented in `check_remaining_guide_routes.frame`. Finger yaw mounts belong to each finger's MCP abduction frame. Thumb metacarpal mounts belong to `thumb_cmc_flexion`; thumb MCP IP outlet and IP drive mounts belong to `thumb_mcp_flexion`; other thumb MCP mounts belong to `thumb_mcp_abduction`. Wrist abduction guide mounts belong to `forearm`; wrist flexion guide mounts belong to `wrist_abduction`; palm cup drive mounts belong to `wrist_flexion`.

The final29 wrist bodies pass strict, mutual38, attachment29 against the final main palm, and all225 routes (`wrist_upper_validate.json`, `wrist_upper_mutual.json`, `wrist_upper_attachment_report.json`, `wrist_upper_route_report.json`). Exact placement manifest: `wrist_guide_frames.json`. The final65-pose hardware grid passes in `wrist_final_hardware_rom.json`: three revised bodies are checked directly, and26 byte-identical native bodies inherit the complete65-pose baseline. Actual native hardware is bounded by proved containing solids, with exact native fallback wherever an envelope intersects a guide.

All 56 requested mouths are now accepted locally in 220 real bodies. The final thumb bank uses the radial rib center (-1.512673403, -9.118275723, -15.000175788), positive-X clamp side and 4.0 mm width. Its four arms join one connected support; both host jaws are single connected bodies, with zero bolt/host overlap. The final wrist and cup placement manifests are `wrist_guide_frames.json` and `cup_guide_frames.json`; thumb base is `thumb_base_frames.json`.

The root-owned full-assembly gates may require additional material relief where other moving hardware meets these local families. The subsequent CMC parent repair is accepted below. Final wrist hardware and palm-bank replacement gates are accepted below.

The exact accepted fifth-ray host is `palm_little_review.step`, SHA256 `22a73cf25b02ac7b5d2a43d9a53983bfd7e6c302b726b6df377510690998ac0c`.

## CMC parent follow-up accepted

`thumb_cmc_mounts_review.step` has24 bodies, SHA256 `7e07b6a808078bf7c6f3343da565b7164a75a9e64a2106d9a4e9f1146cd42b72`; exact mapping is `thumb_cmc_frames.json`. A new smooth parent support arm and local swept passages clear the unchanged225 tendon poses. Strict every-placement, mutual39, host attachment24 and all225 route gates pass. The combined118-body native mutual gate with thumb-base52 and downstream42 passes328 tested pairs (`thumb_all_guides_mutual.json`). All mouth and clamp datums remain unchanged.

## Fixed palm-bank replacement accepted

`palm_guide_mounts_review.step` has66 bodies, SHA256 `5197d6f9ee6017416b44f41a7bcb26b612cb5e36dc7aa23b05be0c19f6916b01`; mapping `palm_bank_frames.json` is authoritative. Remove all67 old `palm_bank` occurrences before integrating these66. The42 mouth datums stay fixed. Six smooth support arms now terminate on the unchanged dorsal MCP bosses atZ−16.5; a0.020 mm clearance pocket removes the ring/fifth-ray corner contact.

Final strict66, mutual104, attachment66 and225 route checks pass (`palm_bank_final_*`). The attachment report names the exact new main-host SHA `6c2e669df4f176c530c5b1c8623c861b942ca60d1e75cb346bd2548f6a32adf4`. The225-pose native moving-hardware gate passes against120 comb bodies, final fifth-ray host and15 palm hardware bodies (`palm_bank_moving_hardware.json`), with every input STEP hash recorded.

## Final wrist hardware repair accepted

The frozen final wrist SHA is `66d67434bc744fdf80eddec71a6776a9dceeacb721915dbe9d448dd548a93c65`,29 bodies. Both flexion-mouth jaws have native bushing clearance. Both abduction-mouth screws are inward-shifted M0.4 socket screws, with heads facing away from the moving flexion pulleys. The positive mouth now attaches through its upper jaw to one smooth connected support arm; every mouth and tendon path stays fixed.

Replace old labels `wrist_abduction_drive_mouth_-1_liner_+1_M0p6_screw` and `wrist_abduction_drive_mouth_1_liner_-1_M0p6_screw` with their corresponding `_M0p4_screw` labels. Replace the full wrist family using the29-body manifest so obsolete fasteners cannot remain. The full-assembly225-pose gate remains root-owned; these certificates cover the named guide families and explicitly recorded host/hardware inputs.
