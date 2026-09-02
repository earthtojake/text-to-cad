# Burr inspection and repair loop

Load this reference when a model needs assembly-interference evidence or a
source repair based on Burr.

## Choose the right input

- Use STEP for assembly structure and the interference check.
- Use STL or GLB for visual inspection only.
- Start Burr on the narrowest folder that contains the intended models.
- Generated cache directories are not source artifacts and should not be
  selected as models.

For a meaningful STEP assembly check, give distinct external components clear
occurrence names. The checker cannot infer which accidental names represent a
board, enclosure, motor, bracket, or fastener.

## Preserve subsystem boundaries

Internal contacts inside a validated purchased or electronics subsystem are
often intentional. When the question is board-versus-enclosure clearance,
represent the populated board as one external occurrence and the enclosure as a
second occurrence. Preserve the detailed geometry inside the board occurrence;
do not remove the connector or fuse unrelated external components merely to
silence a finding.

The same rule applies to other subsystems: group only the internal geometry that
has already been validated together, and keep every external interface that the
current check is meant to compare as a distinct occurrence.

## Evaluate a finding

When Burr reports a failure:

1. Record the exact model path, component names, and finding message.
2. Select the finding so Burr highlights the involved occurrences.
3. Use X-ray for hidden collisions and Solid for exterior occlusion.
4. Choose a canonical camera view that makes the defect understandable.
5. Locate the source system that owns the geometry or placement.
6. Repair the smallest responsible source parameter or feature.
7. Regenerate the same output path and wait for Burr to refresh it.
8. Rerun the check and the same visual view.

Keep the negative artifact when it is a useful regression fixture. Name fail
and pass models by the condition they prove, not by arbitrary revision numbers.

## Interpret incomplete results

An incomplete result is a stop condition for the clean interference claim.
Common causes include an unsupported file shape, too few distinct components,
or an open/inconclusive component mesh after STEP tessellation.

An exact vendor STEP can be visually detailed yet unsuitable as a collision
mesh. In that case, retain it for visual review if useful and introduce a
closed, documented collision envelope for the dimensions relevant to the
check. Never silently substitute a box and call it the exact component.

## KiCad handoff

KiCad owns schematic and PCB validation, component placement, footprint 3D
models, and populated STEP export. The combined mechanical source owns board
placement relative to the enclosure or chassis. Burr owns only visualization
and the external assembly-interference result.

A strong board/enclosure fixture contains:

- a KiCad source project;
- a populated board STEP exported from that project;
- source for a deliberately blocked enclosure and its fail assembly;
- source for a repaired cutout and its pass assembly;
- Burr result text and paired screenshots from the same view.

## Reporting

For `pass`, report the number of components and checked pairs. For `fail`, also
report every relevant component pair and finding type. For `incomplete`, report
the exact reason and do not collapse it into pass/fail.

Always distinguish visual observations from computed interference. Burr does
not currently prove minimum clearance, tolerance stacks, motion envelopes,
flexible-body behavior, fit class, strength, or manufacturability.
