---
name: organic-cad
description: Integrate organic GLB, OBJ or STL models with parametric CAD joints, connectors and mounts. Use for fitting mechanical connections into AI-generated or sculpted meshes, Boolean integration, assembly and motion-clearance checks.
---

# Organic models with CAD connections

Use an imported organic mesh for appearance and authored CAD for functional
connections. Choose fixed connectors or movable mechanisms from intended use
and actual installation space; size them from local geometry. Keep both sources.
Fuse their tessellated geometry with a solid mesh kernel; keep independently
printed parts as separate nodes.

Apply this workflow to sculpted assemblies, decorative housings and organic
forms that need mechanical connections.

## Setup

Install this skill's pinned `requirements.txt` in the project environment.
Final STL/GLB export needs Node.js (>=20); rendering also requires
`python -m playwright install chromium`.
Exercise the helpers this task will use with a small solid, since the heavy
geometry backends load on call rather than import. For example, run
`prepare_mesh(trimesh.creation.box())` before mesh Boolean work; also exercise
`from_cad` or `check_motion` when the task needs CAD conversion or motion.
Report a missing backend before processing the full model.

Read [references/workflow.md](references/workflow.md) for mesh/CAD integration.
Read [references/joint-design.md](references/joint-design.md) when selecting or
sizing a movable mechanism; for a known fixed connector, use only its relevant
sizing guidance. Read [references/joint-layout.md](references/joint-layout.md)
when deciding part boundaries or connector ownership. Read
[references/runtime.md](references/runtime.md) while implementing the recipe,
and [references/validation.md](references/validation.md) for the checks that
apply to the chosen connection. Use
[references/motion-surfaces.md](references/motion-surfaces.md) only for curved
seams or smoothed motion cutters.

## Workflow

1. **Inspect and establish physical scale.** Preserve the input asset; inspect
   scene instances, transforms, bounds, connected pieces and topology. GLB is
   preferred, OBJ/STL supported. Texture/normal-map detail does not become printed
   relief. Record units, up axis and the target physical dimensions; never infer
   millimetres silently from a normalized AI asset. An unspecified size may be
   chosen explicitly for a prototype; fit-critical dimensions need measured input
   or an identified calibration experiment.
2. **Describe the intended connection and movement before choosing hardware.** For each connection,
   record which surfaces move relative to which, the neutral pose, required and
   unwanted rotations/translations, axes, travel and any coupled movement. Include
   whether it must hold a pose, detach or support a load. Anatomy suggests candidate
   motions; the user's intended function determines the requirement. Keep
   operating travel distinct from assembly/insertion. Do not assume every shoulder,
   elbow or wrist needs a ball joint.
3. **Prepare and measure a working copy.** Use `prepare_mesh` and retain its audit.
   Triangle/quad caps are opt-in and need visual review; fail unresolved defects.
   Reconstruction/remeshing needs an error budget and a before/after comparison.
   Simplify, if needed, before adding precision CAD. Measure local cross-sections,
   depth, skin clearance and attachment stock at candidate locations in mm.
4. **Choose and size the mechanism and layout together.** Use the joint-design
   reference to select a fixed connector, hinge, swivel, ball socket, gimbal,
   slider or other suitable structure. Consider meaningful alternatives when the choice is ambiguous.
   Place the axes and assign each mechanical feature to a printed part or separate
   insert. Account for local space, retained walls, roots, motion and assembly access;
   derive joint dimensions from those measurements. Set process-dependent fit gaps
   separately from geometric scale. Use natural seams, overlaps, hollow hoods or
   internal carriers where useful; a plane plus an exposed connector is a prototype
   option. Record the selected structure, dimensions and reasons before authoring.
5. **Generate the mechanical CAD with `$cad`.** When available, load that skill
   with a concrete brief: selected mechanism, measured space, derived dimensions,
   local frames, travel, part ownership, protected exterior and assembly route.
   Author editable parametric solids, exact STEP, labeled additive stock and
   subtractive tools; validate their dimensions, alignment and geometry and inspect
   a snapshot before integration. Follow the handoff contract in the workflow
   reference. The ball-socket helper is optional after selection; it is not the
   generator for every mechanism. If `$cad` is unavailable, state that and author
   equivalent CAD through the installed cadgen runtime, retaining the same checks.
6. **Segment and integrate one representative connection.** Author closed regional masks
   or capped cuts, explicit seam gaps and named datums. Tessellate the validated CAD
   at an explicit tolerance, place it once in the common frame, then union attachment
   stock into its assigned sculpt part and subtract that part's complete functional
   voids. Keep separate pins, inserts and covers independent. A pocket must not be
   refilled by surrounding sculpt material or reinforcement. Check connected
   attachments and cavity access; the workflow reference covers Boolean ownership.
7. **Design motion clearance when parts move.** Save the initial collision
   result. Sweep the relevant organic and mechanical obstacles through the specified
   motion, with geometric and discretization allowances; use a checker/envelope that
   actually supports that motion. Bound permitted cuts and protect functional walls,
   roots, bearing surfaces and retention features. For appearance-sensitive sculpts,
   prefer local spatially partitioned covers over a global hull. Recheck after
   clipping/protecting cutters. Curved seams and optional cutter smoothing are
   separate decisions; smoothing must preserve coverage and meet a material-removal
   budget. Keep stage-by-stage added/removed volumes and same-pose shape comparisons.
   Broad trims or external stock need their own geometric justification.
8. **Validate the final assembly.** Check closed positive-volume parts, expected
   components, actual connector dimensions, walls and attachment stock. Check assembly
   access and any intended retention separately. For movable connections, validate
   neutral, endpoints and intermediate configurations, including combinations of
   independent freedoms and coupled coordinates. Use the actual final geometry,
   including pins, covers, ribs and carriers; record overlap in mm3 and separation
   in mm. Kernel errors are inconclusive. Inspect concealed layouts in section and
   relevant normal/extreme views. Run `stl_roundtrip` before final geometry checks
   and use its returned meshes. Report unsupported motion checks as unverified.
9. **Produce reviewable artifacts suited to the connection.** Write one STL per
   printable part, a named assembly GLB, mechanical STEP, executable source and
   the relevant checks. Add an exploded GLB for multi-part assembly review and
   visible clearance cutters and motion reports when motion cuts were made. For
   interactive movable-assembly review, author canonical URDF with the selected
   joint types, compare its FK to the checked transforms and hand it to
   `$cad-viewer` when available. Snapshot primary outputs and inspect the images.
   Return verified paths/links, the selection and dimension rationale, checks
   run and remaining limits. Use `$dfam-check` for printability and `$gcode` when
   slicing is requested. Supply a representative coupon before claiming a working
   printed friction or snap fit.

## Capability boundaries

- `cadgen.organic` supplies mesh repair, solid booleans, plane splitting and CAD-to-mesh
  conversion. Its only built-in joint factory is `ball_socket`; other mechanisms
  are authored with CAD. There is no automatic semantic rigging or joint placement.
- `RotationGrid`, `clearance_envelope` and `check_motion` implement fixed-pivot
  rotations and sampled two-body checks. A hinge can use one active angular axis.
  They do not implement translational, helical or arbitrary linkage motion. Such
  mechanisms need explicit transforms and a compatible checker/envelope, or a clear
  unverified result; never encode millimetres as angles or substitute a ball sweep.
- There is no integrated constrained surface-fitting or least-removal optimizer.
  Optional smoothing does not provide one. Protecting/clipping a cutter or omitting
  obstacles can invalidate coverage; sampled passes are not continuous certification.
- Rigid checks do not establish elastic insertion, holding torque, strength or wear.
  Check assembly paths separately. Never exempt an entire adjacent part pair to hide
  collisions; local intentional contact/interference needs its own assessment.
- GLB nodes describe grouping, not Boolean union or interactive joints. URDF types,
  frames and limits must match the selected mechanism. A spherical joint can use
  three co-located virtual revolute axes matching the checked order; a hinge uses
  its own single axis. Viewer sliders are a visual aid, not a collision checker or
  proof of mechanical stops. Keep untested coupled motion and print behavior explicit.
