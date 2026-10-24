# tendon_hand models

`models/tendon_hand` on cadgen 0.8: the tendon-driven right-hand research
project (24 joint degrees of freedom, 48 antagonistic tendon actuators; millimetres,
fingers along +Y, palm side +Z, thumb on -X). The old project was 112 one-model
scripts. The 56 that build from the project's code are models here, folded into five
scripts by subsystem, each model keeping its name, a `@model` that writes nothing. The
other 56 were reviews and clearance studies on frozen STEP snapshots and generated
validation output, not the hand itself, and are not kept.

Build from this folder; each script builds the models its `__main__` calls:

```
python components.py
python phalanges.py
python routing.py
python guide_mounts.py
python forearm.py
cadgen snapshot "$ID" fist.png --pose fist          # ID: anatomy_layout's id: line
```

| Script | Models |
| --- | --- |
| `components.py` (20) | `axle_review`, `driven_axle_review`, `bushing_review`, `retaining_ring_review`, `pulley_review`, `pulley_hub_review`, `universal_carrier_review`, `wrist_review`, `palm_cradle_clearance_review`, `thumb_metacarpal_review`, `motor_review`, `gearbox_review`, `capstan_review`, `capstan_index_overlay`, `tension_cartridge_review`, `tension_cartridge_bank_review`, `drive_terminal_review`, `drive_terminal_macro`, `drive_terminal_placements`, `runtime_fixture` |
| `phalanges.py` (11) | `anatomy_layout` (joints and curl couplings, below), `phalanx_review`, `phalanx_variants_review`, `phalanx_continuous_r5`, `phalanx_continuous_supports_r5`, `phalanx_continuous_representative_r5`, `fingertip_pad_review`, `fingertip_pad_export_repair`, `fingertip_bridge_repair_review`, `fingernail_export_repair_review`, `fingernail_review` |
| `routing.py` (5) | `bowden_review`, `transport_review`, `middle_routing_review`, `thumb_cmc_transport_review`, `thumb_cmc_candidate_review` |
| `guide_mounts.py` (14) | `index_guide_mounts`, `middle_guide_mounts`, `ring_guide_mounts`, `little_guide_mounts`, `phalanx_guide_mounts_review`, `guide_comb_review`, `fixed_outlet_review`, `fixed_outlet_mounts_review`, `yaw_reaction_mounts_review`, `yaw_outlet_mount_review`, `yaw_guide_macro_review`, `thumb_cmc_negative_jaw_repair_review`, `thumb_downstream_mounts_review`, `thumb_reaction_arm_context_candidate` |
| `forearm.py` (6) | `forearm_frame_review`, `forearm_guide_banks_review`, `forearm_mount_system_review`, `forearm_housing_review`, `actuator_fasteners_review`, `forearm_housing_context` |

Measured on 2026-10-23 (one machine, its load 15-35 from other work; the five scripts
built one after another, each in a fresh worker): cold `components` 106 s, `routing` 20 s,
`phalanges` 257 s, `guide_mounts` 210 s, `forearm` 97 s. A no-op takes 1.0-2.5 s per
script: every model replays.

## The port

- `@step(out="../STEP/x.step")` became `@model`; `build123d` is imported directly, `cadgen.srgb("#…")` is the hex itself, which
  a shape takes as it is, `cadgen.report` is gone (the engine names each body it runs) and
  `read_step` is the engine's. `lib/` holds the 56 factory
  modules these models reach, unchanged but for those imports, and the JSON data they
  read. `lib/assembly.integration_bodies` and `lib/palm_frame.make_palm_frame_bodies`
  still read frozen STEP snapshots outside Git; no ported model calls them.
- No model calls another. `phalanx_guide_mounts_review` called the four finger models,
  `forearm_mount_system_review` the frame and guide-bank models, and
  `forearm_housing_context` read the mount system's and the fasteners' STEP. The
  pieces several models place are `@memo` stages: `finger_guide_mounts(finger)` (18-35 s
  and about 1,240 kernel calls each, placed by its finger's model and the four-finger
  review), `forearm_frame()` and `forearm_guide_banks()` (about 40 s, 3,100 and 5,300
  calls, placed by three models each) and `continuous_supports()` (about 25 s, 1,160
  calls, placed by both R5 support models). Nothing else is: the housing and the
  fasteners (2.4 s and 0.9 s) are plain functions, and each model makes its own.
- The R5 supports clip against `phalanx_continuous_r5` as STEP gives it back ("native
  STEP reconstruction is required for reliable clipping"): the original read that
  model's STEP output with build123d's `import_step`. `lib/phalanx_r5_host.py` writes
  the same phalanx to STEP and reads it back in memory now, in `warm_host()`, a `@memo`
  function returning the shape as OCCT's reader made it, so the call keys it (the
  phalanx as built clips the +X rail to nothing; its STEP reconstruction clips it whole).
  The clipping booleans of `lib/phalanx_r5_boolean.py` are build123d's, never cleaned, as
  the raw `BRepAlgoAPI` ones they replace were (the same parts: volumes, faces and
  bounds). Both R5 models replay on a no-op (0.2 s for the two, against 17 s each when
  they ran whole, measured 2026-10-23/24).
- Materials: `capstan_index_overlay` declared `materials=` (the palette's aluminium
  bucket); each of its parts carries `lib/palette.py`'s `MATERIALS` entry for its bucket
  now (`lib.assembly.compound`), a catalogue material in the old finish's look with
  `color=None`, so a part keeps its palette colour. The other models declared no
  materials and carry colours alone, as before.
- Dropped: the side files four models wrote from their bodies
  (`validation/*_frames.json`, for the validation programs; a model writes nothing), `capstan_index_overlay`'s `capstan_records()` (r13's overlay
  table, read from a validation output), `runtime_fixture`'s `bend` clip (a tube
  deformation, which no joint makes) and the render-job JSON (the old snapshot's).

## Kinematics

`anatomy_layout` is the hand's skeleton at the neutral pose: every phalanx and every
joint's two drive pulleys. Its finger joints are build123d joints at `lib/layout.py`'s
datums: a `RevoluteJoint` on the parent about the joint's axis, its travel the joint's
limits, and a `RigidJoint` of the same label on the child where it stands, so every
joint is 0 as built. Per finger: MCP flexion, PIP and DIP; the thumb: CMC flexion, MCP
abduction, MCP flexion and IP. A joint's two drive pulleys ride its child. The study
has no palm, so the MCP and thumb-CMC abduction carriers (each joint's abduction
pulleys) stand as the ground and those abductions are not modelled.

Each finger's curl is one control, `gear_pair(hand, "<finger>_curl", ...)`: 0 straight, 1
each flexion at its limit (MCP 90, PIP 110, DIP 80 degrees); `thumb_curl` drives the
thumb's MCP flexion (70) and IP (85). Two configurations: `fist` (every curl 1) and
`point` (all but the index).
