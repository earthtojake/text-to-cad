# Hand continuation status — 2026-09-06

The hand is unfinished. Mechanical export repairs and full native checks precede
blind aesthetic acceptance, choreography, explode and final Viewer handoff.
Do not mark the whole hand accepted from any local or retained-body gate.

## Current checkpoint: R13

**Viewer crash reported by the user, 2026-09-07 UTC.** Do not reopen the full
hand in the user's browser. The server on port 3253 behind the supplied link
was stopped; the subsequent instance registry was empty. Read-only accounting
of all 866 default mesh caches proves 19,341,464 triangles and 2,495,048,856
bytes of CPU render arrays before topology, temporary allocations or GPU
buffers. See `native_r13_viewer_memory_accounting.json` and BUG036. The initial
load has no aggregate memory budget and adaptive detail starts afterward.
The earlier 4.0 GB tab observation is consistent with memory exhaustion, but
the exact crash mechanism is not confirmed by a crash dump. Fix and validate
bounded loading outside the user's browser before another handoff. Historical
Viewer links below are withdrawn, not verified deliverables.

The latest native STEP has 3259 occurrences, 3041 rigid bodies and 218 variable
bodies. Its SHA-256 is
`00d1fd2fa41afc7d50893ce492a25345caa267832a42c1ab01c044fe6b3552a9`.
The corrected prerequisite rebuild produced byte-identical STEP bytes; see
`native_r13_gate_reference_refresh.json`. The chronological notes below retain
earlier failures and pending states and are superseded by this checkpoint.

- `native_finger_finish_r5_v2_gate.json` passes all 225 poses for 35 uniquely
  identified changed bodies, all native rigid neighbours, all 48 payout routes,
  and separation from rotating actuators. The first empty-name audit remains
  invalid and supplies no acceptance.
- `native_r13_hand_rigid_gate.json` and `native_r13_tendon_gate.json` pass the
  combined 3041-body hand-frame checks at all 225 static poses. Physical
  actuator motion and final export validation are separate prerequisites.
- R6 thumb strict/subset/cap-pair/attachment/bore gates pass. The bank and five
  fingertip bridge replacements pass their local native gates.
- All six R13 whole-hand/detail renders and two proximal macros were inspected.
  The palm macro's small facets also appear in independent OCCT triangulation:
  they are actual modeled reliefs. There is no independent aesthetic verdict.
- Exact placed native BREP comparison finds 3230 R13 occurrences identical to
  R11. All 29 remaining occurrences pass a bound fresh strict native check.
  The complete R11 strict baseline now passes all 3257 occurrences/864 prototypes.
  `certify_native_export_validity.py` completed successfully:
  `native_r13_strict_gate.json` passes all 3259 R13 occurrences, every placement.
- Full export material equivalence was stopped after preserving 1229 of 1230
  completed proof classes, with 72 reported failures. The remaining ring-middle
  Boolean did not finish. It is not passing. Session 94269 is no longer active.
  `native_r13_export_material_stopped_partial.json` and
  `native_r13_export_material_stop_record.json` preserve the exact checkpoint
  and task-owned process identities. Log:
  `tmp/anthropomorphic_hand/native_r13_export_material_gate.log`.
  Focused source/export facts show identical placements and bounds. Both are
  native solids. The same Boolean helper also returns the whole terminal
  ferrule when subtracting two deep copies of that same valid native part;
  raw subtraction of the identical TShape returns empty. Single-solid
  normalization, common-root cancellation and non-destructive mode do not
  resolve this diagnostic. Do not infer changed geometry or equality from
  these contradictory results. Interactive session 32018 was closed after its
  diagnostic evidence was saved. No model geometry or collision threshold changed.
- `native_r13_export_records.json` is complete and hash-bound. Of 3259
  occurrences, 3166 have completed zero-face directed native differences;
  92 have agreeing complete native boundary records at 1e-10 scalar precision;
  only `wrist_fixed_bearing_fork` has differing records. Clone, moved-part
  (including 1e-8 mm) and reversed-orientation controls behave as required.
  Numeric field precision is not a global Hausdorff bound or a Boolean pass.
- The fork's 69 supports and 190 spatial edges agree. STEP export removes a
  degenerate edge and rewrites seven pcurves. `native_r13_export_fork_gate.json`
  now passes a fresh direct check of the actual final-export fork against all
  3041 exported rigid bodies and 48 routes at all 225 poses, including physical
  actuator payout. Session 70810 completed; no source/export equality is assumed.
- `native_r13_export_rigid_delta_gate.json` now passes all 225 poses for the
  remaining 46 rigid bodies without completed equality proofs. Every actual
  exported neighbour, every route and physical actuator payout are included.
  Session 23971 completed. The four partitions retain exact-pose checkpoints.
  Log: `tmp/anthropomorphic_hand/native_r13_export_rigid_delta.log`.
  `certify_r13_export_fidelity.py` completed successfully. It preserves the
  failed Boolean diagnostic, distinguishes direct
  rigid checks from the 46 variable tendons' native record comparison, and
  does not claim an exact global material-equality or spatial-error proof.
- Full physical actuator rigid audit completed all 225 poses successfully in
  session 35951 after its six-worker resume. Log:
  `tmp/anthropomorphic_hand/native_payout_rigid_grouped_resumed_6.log`.
  The five explicitly identified processes of the previous four-worker run
  were stopped; `native_payout_worker_resume_6.json` records checkpoint hashes.
  Neither the validator nor geometry changed. Earlier resume records remain.
- R11 strict session 12306 finished successfully. Do not stop unrelated Viewer
  or CAD processes.
- Fresh `blind_phalanx_r5` and `blind_pulley_r3` image packets and randomized
  assignments are prepared in `tmp/anthropomorphic_hand`. No critic has run.
  Explicit permission to launch specialists and fresh blind reviewers remains
  pending; do not infer it or fabricate verdicts.
- Five additional R13 component macros (carriers, fingertips, palm, wrist,
  actuators) completed in session 49733. The wrist view was obstructed; two
  reframed opposed macros completed in session 59278. All seven were inspected;
  `native_r13_component_visual_review.json` records their image hashes and the
  superseded obstructed view. Four further anonymous packets are prepared in
  `blind_universal_carriers_r13`, `blind_palm_frame_r13`, `blind_fingernails_r13`
  and `blind_capstans_r13`, with assignments outside the packet folders and no
  critic verdict. See `native_r13_additional_blind_packets.json`.
- `native_r13_neutral_moment_arm_gate.json` passes all 1152 tendon/axis entries
  using fresh finite differences and frozen source hashes. Its scope is neutral
  hand-side virtual work; wrist transport compensation remains separate.
  `R13_ROUTING_TABLES.md` and `native_r13_routing_tables.json` publish the 48
  tendon extrema, 24-axis moment matrix and 225 static results from verified
  current inputs. These tables explicitly retain pending acceptance gates.
- `certify_native_payout_repairs.py` completed successfully:
  `native_r13_payout_rigid_gate.json` passes all 225 physical actuator poses.
- `certify_r13_static_mechanics.py` completed successfully:
  `native_r13_static_mechanical_gate.json` passes current R13 static mechanics,
  3259 occurrences / 3041 rigid bodies / 218 variable bodies / 225 poses.
  It explicitly keeps `whole_model_accepted=false` and does not claim exact
  global source/export material equality. The regenerated routing tables now
  include all five static checks and the precise export-QA scope.
- A new task-owned static Viewer serves `models/` at
  `http://127.0.0.1:3252/` in session 98878. Its R13 file URL is
  `http://127.0.0.1:3252/?file=assemblies/STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step`.
  Browser loading was slow because default live-view meshes were not cached.
  `tmp/anthropomorphic_hand/warm_native_viewer_r13.py` completed in session 70525:
  all 866 components are cached at the unchanged default 0.0015 / 0.35 settings.
  The live page still has not displayed the model. The first renderer became
  blank and unresponsive; Chrome reported memory usage as high as 4.0 GB.
  Its main page context was absent while eight surf workers remained. A normal
  reload did not restore the scene. Only the task's renderer (Chrome Task
  Manager PID 41784, filtered by the R13 title) was stopped. A fresh renderer
  restored a responsive Viewer shell but remained at the indeterminate
  `Loading CAD...` state. No Viewer exception or definitive memory-failure
  diagnosis was obtained. The loading bar is indeterminate, not a percent.
  Do not return this URL as verified or infer milestone 6 acceptance. The
  server and completed cache remain available for focused debugging; no
  runtime source, geometry or tolerances were changed during this inspection.

Choreography and staged explode remain unauthored until prior acceptance gates
close. The old Viewer on port 3251 is not a final handoff.

## Accepted in this continuation

- `native_retained_final_gate.json`: all2594 retained rigid bodies, all225 final
  static poses, every retained/retained pair, pass. The manifest explicitly
  reserves all replacements and the pending middle-proximal support family for
  a complementary delta. Exact named proofs from the superseded native baseline
  seed this gate only after checking native STEP, frame and engine hashes.
- `final_fist_route_gate.json`: all48 complete routes, continuity, minimum bend
  radius, pair/self spacing and payout, pass. Maximum travel1.243445rad.
  The candidate uses MCP90/PIP90/DIP60 on four fingers, thumb CMC abduction-15,
  thumb CMC flexion45/MCP abduction-10/MCP flexion55/IP60. Independent limits
  are unchanged. The80/95/60 trial failed bend radius and was rejected.
- `final_fist_tendon_solids.json`: all48 fist routes versus all3039 actual
  exported rigid solids with corrected pads/nails, pass. This precedes the two
  arm reroutes and support machining; changed geometry must be checked again.
- `final_fist_rigid_delta.json`: complete,13 known thumb-support contacts,
  no changed inputs. Every hit is on the explicit support-repair list. Corrected
  pads/nails and the revised index/thumb pose introduce no other rigid contact.
- `fingertip_pad_export_roundtrip.json`:30 native valid closed bodies, analytic
  cap envelopes, bond planes and precision pinch pass. Original STEP pads were
  opposite caps (BUG030); these replacements preserve design dimensions/datums.
- `fingernail_export_roundtrip.json`:30 native bodies, source/export agreement,
  five nail envelopes and75 local pairs pass. Native strict validation also
  passes all30 placements. Two meridian sectors preserve the tiny screw cuts.
- Negative CMC jaw reroute: strict native pass, all three bores preserved, both
  yaw drums clear. Its small flexion-mouth lip is still handled by machining.
- Radial shared bank rib reroute: strict native pass, all six guide bores clear,
  both directed source/native differences empty, negative yaw drum clear.
  Existing positive-mouth lip and bushing-seat contacts remain in the relief list.

The historical `final_static_tendon_solids_resolved_gate.json` passes the frozen
3039-body computational integration across225 poses. BUG029 resolves a false
inside classification through an outside vertex and boundary-face proof,
1.810953546mm clearance. That certificate does not certify later replacements
or silently resolve the subsequently discovered native STEP export defects.

## Current mechanical work

`lib/static_clearance_relief.py` machines23 explicit support/obstacle pairs,
retaining shafts, bearing seats, pulley profiles and every guide datum. It now
preloads both validated arm reroutes rather than cutting their old ribs into
unsupported pieces. Two individually inspected palm offcuts are removable:
0.696665 and1.580853mm³; both are clear of every protected bearing/mount/comb-seat
zone and parent-frame guide mouth. Any unrelated detached fragment fails.

R8 built all14 connected supports and passed native strict validation. Its
225-pose targeted native sweep found one0.000195313mm³ palm/negative-CMC-jaw
contact at thumb abduction-5 degrees. R9's repeated rounded cleanup pockets
left exactly the same residual and correctly rejected the build. A focused
native experiment proves that a planar pocket using the same0.025mm clearance
removes the contact and retains one valid palm solid. R10 completed with
that explicit post-cut cleanup and zero-contact assertion. Log:
`tmp/anthropomorphic_hand/static_clearance_relief_build_r10.log`.
`static_clearance_relief_review.step` is now R10. Its build report passes,
`static_clearance_relief_strict.json` passes all14 native occurrences, and
`relieved_native_pair_gate.json` passes all23 pairs at all225 final poses
(177 distinct exact relative pairs). R8 reports are archived with `_r8` suffix;
the native R8 revision and focused cut comparison are recorded in
`palm_residual_cleanup_diagnostic.json`. Never use a failed build as acceptance.

After the build completes:

```sh
./.venv/bin/cadgen step inspect validate models/assemblies/STEP/anthropomorphic_hand/static_clearance_relief_review.step --every-placement --out models/assemblies/validation/anthropomorphic_hand/static_clearance_relief_strict.json
./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_relieved_native_pairs.py
./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_native_replacement_rigid.py --workers 4
./.venv/bin/python models/assemblies/validation/anthropomorphic_hand/check_all_native_tendon_solids.py --workers 4
```

The replacement rigid runner is running in `native_replacement_final.log`.
The all-native tendon runner now uses physical actuator payout, described below.
The replacement rigid runner complements the2594-body retained gate; coverage must be composed by
matching final body revisions and all225 poses. The tendon runner checks every
actual native solid, normalizing one-solid compounds to prevent the OCCT
containment miss (BUG031). Final whole-export validation remains required.
`native_hand_registry.py` includes pads/nails by default and support reliefs
with `include_reliefs=True`.

The old attachment audit was stopped after its R8 inputs became obsolete.
The revised R10 attachment audit passes every repaired support in all four
frames: `repaired_attachment_gate.json`. The runner finds
native contact paths from each repaired support to its host, using actual
vertex pairs as distance upper bounds and single-solid OCCT distance for
remaining edges. Bounding boxes only propose candidates. Acceptance requires
verified paths to the host; unrelated frame pairs need not be evaluated.

The old static route packets and hand-frame rigid sweeps retain neutral forearm
actuator hardware. The new `payout_static_route_packet_manifest.json` freezes
all225 poses with solved spool positions and updated stored rope/free leads.
`final_static_actuator_payout.json` passes total-length residuals for all48
tendons at each pose. Maximum travel5.975815839rad is at wrist_flexion_60.
`payout_static_curves_gate.json` passes all225 corrected poses: continuity,
minimum bend radius, mutual spacing and self-spacing. No choreography is added.

`lib/actuator_kinematics.py` moves spools, terminals, retainer screws and the
4:1 planetary hardware. The240-case axis/rolling/rope-endpoint check passes.
Both native probes at `wrist_flexion_60` now pass: all48 tendons versus all3039
native bodies, and every rigid pair with a physically rotating actuator endpoint.
The full225-pose physical payout tendon sweep is running. The full rigid
supplement is `check_native_payout_rigid_grouped.py --workers 2`; components
share a cache frame only after their authored transform matrices compare exactly.
The tendon checker uses exact angle-dependent cache aliases for moving bodies;
the rigid checker forbids shared forearm-frame identities for rotating parts.
`native_capstan_envelope_gate.json` passes the containing six-turn tube against
all144 native co-rotating terminations. The prefix verifier passes240 positives
and4 adversarial rejections; the full tendon runner verifies each actual prefix
before transferring the containing-envelope clearance proof.

`hand_mechanical_candidate.step` has rebuilt from the actual R10 native parts:
3257 occurrences,3039 rigid plus218 variable. It carries only the existing
static braided presentation. Full export strict validation and six QA renders
(`mechanical_candidate_render_job.json`) are running. Neither this mechanical
candidate nor its images confer a blind aesthetic pass.

### Subsequent native findings and isolated repairs

The whole candidate's strict run found five self-intersecting fingertip bridges.
`fingertip_bridge_repair_review.step` R2 rebuilds the ellipsoid first and cuts its
bond plane afterward. All5 native placements pass strict validation; both
directed native surface differences are empty, all60 mount pairs are clear and
all5 pad bonds touch. Opposed native fingertip context PNGs were inspected.
`fingertip_bridge_local_acceptance.json` binds those local results. These5 parts
are not yet integrated; the old whole candidate and running audit inputs stay
immutable. Diagnostic context colors do not constitute final finish approval.

The completed `native_reroute_supports_r10_gate.json` finds five previously
uncovered pairs: the radial bank against its splice screw, and the negative
CMC arm against a neighboring structural guide, inlet clamp, cap and screw.
The old arm also contacts a flexion tendon. R10's23-pair local pass therefore
does not confer whole-assembly clearance.

`radial_bank_screw_clearance_candidate.step` now passes native strict inspection,
preserves all6 bores and adds no material to R10. Its actual screw gap is
0.019999965mm. `radial_bank_screw_clearance_gate.json` transfers the225-pose
all-neighbour rigid proof using native material containment and a fresh exact
check of the sole failing pair (both bodies share the wrist frame).

The first new CMC arm (bowX4/Y-14) was rejected. The isolated R2 arm (bowX8/Y-6)
passes strict validation and its focused10-pose gate clears the known guide
hardware and flexion tendon; small palm contacts remain. Its completed all48
tendon/225-pose check rejects R2: it contacts the thumb IP-positive reaction,
MCP-abduction-positive reaction and CMC-abduction-negative wrist route. The
all-neighbour R2 diagnostic remains running. A new centerline proposal search
now includes every tendon pose and all protected palm seating regions. The separate
`palm_thumb_arm_clearance_r11.py` is building local pockets, rejecting disconnected
results and verifying all protected seating zones and guide-mouth regions.
R2 is rejected; its R11 palm-pocket experiment must not be integrated as a fix
for those tendon contacts. Neither has whole-hand acceptance.

The new native whole-hand render timed out at900s, including plain180s probes.
A CPU profile locates time in exact-surface tessellation. The native mesh cache
contains roughly2GB of unique meshes; browser uploads deliberately skip entries
over32MiB. `tmp/anthropomorphic_hand/warm_native_mesh.py` uses the same tessellator
at the same .003/.18 tolerances with filesystem storage, avoiding those upload
limits. All78 missing native meshes are now cached. The warmed retry exposed two additional limits: a socket write over2GB and an
unused aggregate component mesh allocation. Both are fixed and committed as
b010e1c25. All806 shared-JS,347 Viewer and5 snapshot transport tests pass, as do
production bundling, freshness and shipping checks. The six native whole-hand
views now render and all were visually inspected. Evidence:
`component_buffer_render_evidence.json`; no mechanical or aesthetic pass inferred.

The old cached baseline ended with an assertion and is not a complete gate.
The superseded full native baseline was deliberately stopped after preserving
its exact pair checkpoints; the final retained-body gate replaces that work.
Do not relaunch either obsolete audit.

## Visual and runtime work

Middle-proximal round5 and its32 supports retain local strict/neutral passes,
but no new blind verdict or final-range acceptance. The hub-collar aesthetic
candidate likewise remains separate. No choreography or explode is authored.
The session still has an unanswered request to authorize independent specialist
and fresh blind-review agents. Do not spawn agents or invent critic verdicts.

`hand_export_repair_context.step` contains all3257 occurrences with corrected
pads/nails and the first CMC arm reroute, before final support machining.
Full-context pad and CMC macros were rendered and visually inspected:
`export_repair_pad_macro.png`, `export_repair_cmc_macro.png` under
`tmp/anthropomorphic_hand/`. Local palmar/dorsal fingertip views also render.
These are QA views, not blind aesthetic acceptance.

Full-hand snapshot allocation failures were fixed by sharing immutable normal,
barycentric and edge-class buffers in `cadScene.js`; deformation still obtains
private writable attributes.803 shared-JS tests and347 viewer tests pass.
Production bundling (including Viewer build) and bundle freshness pass.
`render_buffer_reuse_evidence.json` records the successful3257-occurrence retry.
BUG032 documents reproduction and the regression test. Runtime/source/docs and
the regenerated browser bundle are committed as7b69cd927, "Add continuous tube
deformation for routed CAD assemblies". Model work and BUGS.md remain uncommitted.

Viewer remains at http://127.0.0.1:3251/ and is owned by this task. The last live
Chrome tab is the old `phalanx_continuous_context_r5.step` candidate, not a final
handoff. Do not stop unrelated Viewer instances. No PR or release has been made.

### R3 reaction-arm continuation

The piecewise arm search found an outside-drum route that clears the all225
route proposal screen and protected seating regions. R3 built as one solid,
but strict native inspection rejects self-intersections between its two tight
curved transitions and vertical section. `thumb_arm_r3_self_intersection_diagnostic.json`
locates those surface pairs. R3 opposed snapshots were inspected and its focused
CMC/palm/known-hardware gate passes. The all48 route and all-neighbour diagnostics
remain separate; R3 is not accepted. A smoother R4 proposal search is running.

The repaired radial bank's native attachment chain to the wrist cradle passes
all four actual-solid distances, with zero gap to the palm. Opposed snapshots
rendered and were inspected; a thin separated-looking sliver near the upper
arm/guide mouth still needs geometry-versus-tessellation diagnosis before visual
acceptance. Its strict/subset/225-pose rigid passes remain unchanged.

### Current R4 / R11 candidate

R4's smoother piecewise arm passes native strict validation, all48 physical
tendons at225 poses, all three bores and the10-pose known-neighbour/palm gate.
It has zero native attachment gap to its CMC carrier. Both isolated views were
inspected. The complete all-neighbour225-pose rigid audit is still running.
R3's obsolete rigid diagnostic was stopped after its strict failure; partial
results do not confer acceptance. R11's unused palm-cut experiment stays rejected.

`hand_mechanical_candidate_r11.py` combines R4, the repaired radial bank and
five bridge replacements in a separate full candidate. It built successfully
and is being force-regenerated after the surface export repair below. Its
strict native and full-context render gates remain required. The original R10
STEP and running audit inputs are unchanged. The old R10 strict client stalled
at863/864 prototypes after its daemon disappeared; it was stopped with the
incomplete report preserved. Five known bridge failures remain in that report.

The bank's separated-looking sliver is absent from independent native OCCT
triangulation. Exact UV comparisons locate a surface-export bug: converting a
periodic spline to nonperiodic retains extension knots beyond its active domain,
and the extractor used the first extension knot to shift the surface by an
unwanted whole period. Native and independent spline calculations differ by
up to1.2303mm. The exporter now uses the active Bounds() domain;14 targeted
tests pass including a small periodic swept-surface regression and guard test.
The wider surface suite, corrected cache/render refresh and product commit are
pending. Existing immutable native geometry and collision tolerances are unchanged.

### Latest arm and exporter result

R4's complete225-pose all-neighbour audit rejects it with exactly two pairs:
its return touches the separate right hub jaw (0.0083201mm³) and the dorsal
keyed stub shaft (0.2833312mm³). R11 therefore remains a diagnostic candidate,
not a mechanically accepted integration. Its updated native strict run is
active under `CADGEN_DAEMON=0`; its source STEP stays immutable during that run.

R5 adds a lower-return control point at local(4,1,-16), preserving endpoint
tangents. It passes strict native validation and all48 tendons at225 poses.
Attachment, focused bores/neighbours, full all-neighbour audit and snapshots
are running. R5 is not yet integrated.

The periodic surface exporter correction is committed as24aac21ce. All25
surface tests pass;1926 exact-native bank samples match rendered evaluation
within9.15e-7mm. The corrected isolated bank snapshot was inspected: the
floating sliver is gone. `periodic_surface_repair_evidence.json` binds that
result. R11's864 surface payloads were force-regenerated successfully, and
stale mesh entries were removed only for the426 affected task component IDs.
The corrected full native mesh warmup is running (`native_mesh_warm_r11.log`).
The complete corrected whole-hand views still need rendering and inspection.

### R6 and complete payout tendon result

R5's focused ten-pose bore/interface gate and opposed snapshots pass local QA.
Its complete225-pose all-neighbour audit FAILED exactly one cap pair at thumb
CMC abduction45degrees,0.000010248732mm³. R6 removes only a bounded pocket with
0.025mm margin around that actual native intersection. R6 built successfully;
strict, native subset/all225 cap-pair/attachment, focused bores and opposed
snapshots are running. R12 source is prepared using R6, but is not built yet.
R11 remains unchanged and under its full strict audit.

All physical-payout tendon partitions completed. The base report has exactly
three contacts on the old R10 arm. `certify_native_tendon_repairs.py` verifies
all hashes and packet identities and composes the R5 all-route, bank subset and
five bridge equivalence proofs. `all_native_repaired_tendon_solids_gate.json`
PASSES all225 poses,48 tendons and3039 rigid bodies for those replacements.
R6 requires its further subset transfer; rigid acceptance is separate.

`check_native_finger_finish.py` now audits the33-body continuous phalanx/support
family plus two PIP collars together against3041 rigid bodies and48 payout
routes across225poses. It also proves native AABB separation from every
physically rotating actuator at each pose. Inputs include R5 thumb, repaired
bank and five bridges. `check_native_finger_attachments.py` verifies all32
support-to-phalanx paths under the existing0.025mm seating/thread-fit contract.
The fresh specialist/blind-agent authorization question was presented again;
do not spawn without the user's answer.

### R13 integration and audit identity correction

R6 passes native strict validation, all225 cap-pair poses (10 distinct exact
relative placements), native material-subset proof, zero-gap carrier attachment,
all protected bores and focused interfaces. Its opposed snapshots were inspected.
R12 built with R6; R13 additionally contains the continuous phalanx/supports and
two collars,3259 occurrences/3041 rigid bodies. Both STEP files exist. R13's
866 surface payloads were force-regenerated; its28 new component meshes are
warmed. R12 palm and R13 six-view native renders are running.

IMPORTANT: the first `native_finger_finish_r5_gate.json` was invalidated after
the final evidence binder caught35 empty part names. Extracting a single solid
replaced the shape before saving its label, invalidating name-keyed bounds and
pair caches. The original report is preserved as
`native_finger_finish_r5_rejected_missing_names.json`; the primary report now
has pass=false and an explicit invalidation reason. No clearance acceptance
may be inferred from it. `check_native_finger_finish.py` preserves labels and
asserts all3041 names are unique and nonempty after extraction. A fresh audit
under `native_finger_finish_r5_v2` is running, with no old cache reuse. R13 remains
a diagnostic candidate until this audit passes. Its source still references
the invalidated old gate; update that reference and rebuild after the fresh pass.

`native_finger_attachments_r5_gate.json` independently PASSES all32 supports
and uses explicitly restored native names. `repair_payout_separation_gate.json`
PASSES all seven R6/bank/bridge replacements against every moving actuator at
all225 poses. New native certificate binders are prepared but not yet passing:
`certify_final_native_tendons.py` and `certify_native_rigid_repairs.py` require
the corrected finger audit (and the latter the final replacement rigid gate).
`plan_native_validity_reuse.py` is comparing R11/R13 exact placed BREP bytes;
it produces no pass verdict and requires completed baseline strict checks.
