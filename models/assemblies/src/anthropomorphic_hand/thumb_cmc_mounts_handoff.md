# CMC endpoint supports

`lib/thumb_cmc_mounts.py::thumb_cmc_mounts()` provides 24 real bodies for the 12 frozen CMC reaction-liner endpoints. Each row is `(shape, material_frame, 'thumb', kind)` in assembled neutral world placement, following the existing assembly convention. `cmc_mount_ownership()` maps the twelve endpoints explicitly.

The parent six-channel comb has 35-degree bores at the accepted anchors, R0.47 clamp waists, flared mouths, a 0.08-mm jaw split and two visible M0.6 screws. Three child clamps share a four-liner comb and two separate MCP-flexion outlets at child Y16. No tendon path, pulley, axis or dimension changed for the supports.

## Frozen parent attachment datum

- CMC parent coordinates: **(2.98, -8.00, -17.98) mm**.
- World coordinates: **(-27.235965, 32.450324, -17.98) mm**.
- Clamp closing axis: +Z; footprint 4 mm in local X by 1 mm in local Y.
- The current exact dorsal palm rib is subtracted from two jaws, retaining its native seating patch. The future palm rebuild should retain a rail at this datum or deliberately revise the attachment.
- Parent attachment lower cap `thumb_cmc_parent_inlet_comb_palm_rib_lower_cap` withdraws along **-Z**. The negative MCP-flexion attachment `..._rail_lower_cap` also withdraws -Z. Other caps withdraw +Z in their material frames.

The palm truss has a separately identified self-intersection and is being rebuilt. **The final parent-to-palm host certificate is explicitly pending that rebuild.** The moving-thumb-body, mount-pair and tendon-to-mount checks are separately reported; they do not imply the host gate passed.

## Final pinch packet

`thumb_cmc_atlas.py` and its review JSON now contain 66 entries. The first 65 are unchanged; the added exact final pinch has CMC flex37.474289981694746/yaw-21.046825109125002. Its candidate packet is `validation/anthropomorphic_hand/thumb_cmc_final_pinch_packet.json` and passed its numeric and complete ten-thumb hardware gates (180 exact body-distance checks, CMC minimum radius3.549527 mm). The downstream joint values are recorded in the packet's `whole_pose`.

## Validation artifacts

- `thumb_cmc_mounts_review.step`: complete 24-body support system.
- `thumb_cmc_mounts_validate.json`: strict per-placement geometry validation.
- `thumb_cmc_mounts_routes_report.json`: all48 tendon paths versus mounts at25 stated CMC static cases.
- `thumb_cmc_mounts_thumb_bodies_report.json`: mount/moving-thumb and mount/mount Boolean checks; palm host excluded explicitly and remains pending.
- `thumb_cmc_mounts_pinch_thumb_bodies_report.json`: final exact pinch routes and moving hardware versus mounts.

Read the final `pass` field and row count of each report; a partially written report is not a pass. These are static mount checks, not the requested animation sampling certificate.

## Release scope, 08:12 UTC

The final source and STEP pass strict geometry for all24 bodies, the25-case tendon-to-mount gate, and actual thumb-hardware/mount-pair gates at neutral and exact final pinch. The last revision changed only `thumb_cmc_child_four_liner_comb_structural_jaw`, moving its two support struts outside the rail caps and screws. The23 unchanged bodies retain their prior actual checks; the revised body has its own full recheck. `summarize_thumb_cmc_mounts.py` composes this scoped evidence without erasing the original failed reports. The authoritative summary is `thumb_cmc_mounts_release_status.json`, containing the final STEP SHA256.

Still required in the final assembly: the complete articulated mount-to-hardware sweep, rebuilt-palm host verification, animation sampling, and aesthetic criticism. This specialist release does **not** claim those passed. The factory is ready for integration and those final gates.
