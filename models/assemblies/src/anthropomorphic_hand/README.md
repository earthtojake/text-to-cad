# Anthropomorphic tendon hand

An original right-hand research sculpture with24 joint degrees of freedom and48
antagonistic tendon actuators. Millimeters; fingers point along+Y, palm side+Z,
thumb-X. The full design and acceptance sequence are in [BRIEF.md](BRIEF.md).

**Work in progress.** The latest complete review export is
`../../STEP/anthropomorphic_hand/hand_mechanical_candidate_r13.step`, with3259
occurrences. It combines the repaired thumb, bank and bridges with the revised
middle phalanx and pulley collars. Its corrected finger audit and combined
225-pose hand-frame rigid and tendon certificates pass. Strict native export
validation passes all 3259 occurrences. The full physical actuator audit,
fresh final-export deltas and combined static mechanical certificate now pass
all 225 poses. Export QA distinguishes native material-difference proofs,
direct final-export checks and numeric native tendon boundary-record agreement;
the failed exact Boolean identity diagnostic remains separate.
Independent visual reviews, final choreography, explode and Viewer acceptance
remain required.
It is not a finished or accepted model. [RESUME_STATUS.md](RESUME_STATUS.md) records current
results and [GAUNTLET.md](GAUNTLET.md) records design and blind-review outcomes.
The current [routing tables](../../validation/anthropomorphic_hand/R13_ROUTING_TABLES.md)
contain all 48 tendons, the measured 24-axis neutral moment matrix and all 225
static sample results, with the remaining acceptance limits stated explicitly.

| Milestone | Current status |
|---|---|
| 1. Routing and neutral clearance | Passing in the current static mechanical certificate |
| 2. Independent component design reviews | Open; six anonymous comparison packets are prepared, without new verdicts |
| 3. Native solids, routing tables and static sweeps | Passing for 3259 occurrences and all 225 specified poses |
| 4. Whole-hand visual acceptance | Open; inspected renders do not replace independent acceptance |
| 5. Pose choreography and staged explode | Not authored; must follow visual acceptance, then pass the specified .02/.05 sampling |
| 6. Live Viewer with both parameters | Open; static preview loading remains unresolved and neither parameter exists yet |

The local generated mechanical report is
`../../validation/anthropomorphic_hand/native_r13_static_mechanical_gate.json`.
Its `whole_model_accepted` value remains `false`. Authorization to launch fresh
specialists and blind reviewers is pending under this session's subagent rule.
Generated CAD and numeric audit outputs are gitignored; see
[PR_CONTENTS.md](PR_CONTENTS.md) for the source-only handoff and regeneration limits.

| Source | Purpose |
|---|---|
| `hand_mechanical_candidate_r12.py` | Complete3257-occurrence reconstruction with mechanical repairs |
| `hand_mechanical_candidate_r13.py` | Complete3259-occurrence review with the finger/collar candidates |
| `mechanical_candidate_r13_render_job.json` | Palm, dorsal, forearm and three detail views |
| `mechanical_r13_component_context_render_job.json` | Five current component macros for independent review |
| `mechanical_r13_wrist_context_render_job.json` | Opposed wrist macros after removing a camera obstruction |
| `fingertip_bridge_repair_review.py` | Five strictly validated native bridge replacements |
| `radial_bank_screw_clearance_candidate.py` | Native bank clearance repair with attachment proof |
| `thumb_reaction_arm_clearance_r6.py` | Strictly validated thumb arm with full-range cap clearance |
| `phalanx_continuous_context_r5.py` | Continuous-waist middle-proximal aesthetic candidate |
| `lib/` | Parametric factories, routing, assembly frames and physical actuator transforms |

Run an individual model with the repository Python, then inspect its declared
STEP. Durable reports and validation runners are in
`../../validation/anthropomorphic_hand/`; review images and transient diagnostics
are in the repository's `tmp/anthropomorphic_hand/`. Historical candidates are
kept for comparison. Their names do not imply acceptance.

The full native gates use immutable STEP revisions and225 frozen pose packets.
Do not replace their inputs during a running audit. New repairs stay isolated
until their geometry, routing, rigid clearance and attachment evidence passes.
Final choreography and explode remain unauthored pending the acceptance gates.
