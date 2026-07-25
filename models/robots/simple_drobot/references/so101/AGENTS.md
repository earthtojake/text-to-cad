# SO-101 Part Editing Notes

## Purpose

Use this folder to turn existing SO-101 parts into editable build123d starting
points for a small dog-like robot. Keep each robot part in its own named
subfolder so later work on other limbs and brackets stays separate. The first
part is `upper_arm/`, and the first actuator target is the
Feetech/Waveshare ST3215 servo.

The authoritative working checkout for this project is
`C:\Users\roman\Documents\dev\fork\text-to-cad`. Run generators, inspections,
snapshots, and CAD Viewer from that checkout. Do not write new project changes
to `C:\Users\roman\Documents\dev\cad\text-to-cad`.

## Folder layout

- Use one subfolder per part, such as `upper_arm/`, `lower_arm/`, or `foot/`.
- Keep a part's immutable reference STEP, editable Python generator, generated
  STEP, hidden viewer sidecars, and `reviews/` directory together inside that
  part subfolder.
- Keep this `AGENTS.md` at the `so101/` level so its guidance applies to every
  part subfolder.

## Files and provenance

- `upper_arm/Upper_arm_SO101.step` is the immutable Autodesk-exported reference.
- `upper_arm/Upper_arm_SO101_editable.py` is the source of truth for all new
  upper-arm edits.
- `upper_arm/Upper_arm_SO101_editable.step` is generated from the Python
  source; never edit the generated STEP directly.
- `upper_arm/reviews/` contains the upper-arm verification snapshots.
- Reuse the exact catalog servo already stored at
  `models/robots/lekiwi_quadruped/components/waveshare_feetech_st3215_servo.step`.
  It is step.parts record `waveshare_feetech_st3215_servo`, SHA-256
  `29954eb73bd22b3f9536de2c1d8f96843b5c5b32288a8f4cb09709b8b892e39b`.
- A limb-independent holder now lives at
  `models/robots/simple_drobot/components/st3215_motor_bay/`. Reuse that
  component for later parts. Its flat attachment datum is `X = 0`; creating it
  did not alter or regenerate the existing upper-arm model.

The requested `STS3215` is cataloged as `ST3215`. Confirm whether the actual
hardware is ST3215 or ST3215-HS before finalizing a fit-critical interface.

## Verified starting geometry

- The reference contains one non-empty upper-arm solid plus two empty
  `Wiring_holder` assembly occurrences.
- Non-empty body bounds are approximately:
  - X: -65.084989 to 77.054028 mm
  - Y: 0 to 24.5 mm
  - Z: -35.6 to 31.7 mm
- Body size is approximately 142.139017 x 24.5 x 67.3 mm.
- Keep the imported STEP coordinates until a functional servo datum is chosen.

## Applied upper-arm edits

- The perforated mounting panel on the negative-X end was removed from
  `upper_arm/Upper_arm_SO101_editable.py` from a Back-view markup request.
- `REMOVE_PERFORATED_MOUNT_PANEL` controls this edit.
- `MOUNT_PANEL_CUT_PLANE_X_MM = -29.0` creates the new end plane. The original
  panel junction is at approximately X = -29.084989 mm, so the configured plane
  provides 0.085 mm of boolean overtravel.
- The resulting part remains one solid with bounds approximately
  X -29.0 to 77.084989 mm, Y 0 to 24 mm, and Z -35.6 to 31.7 mm.
- A preliminary ST3215 rear-body socket now extends from that cut end toward
  negative X. The exact catalog servo is aligned lengthwise with the arm:
  servo local X follows global X, local Z follows global -Y, and local Y
  follows global +Z.
- The socket captures only the rear 14.5 mm of the case, leaving the horn and
  passive output outside on the global +/-Y sides. Its cavity is cut from the
  exact catalog rear-case solids, so the raised connector housing and case
  steps become matching negative grooves. Current test-fit assumptions are
  0.25 mm clearance per global-Y side, 0.125 mm clearance per global-Z side,
  3.0 mm walls, a 1.5 mm stop rim, and a rear cable window.
- `upper_arm/Upper_arm_SO101_ST3215_preview.py` generates a non-printable
  installed-fit assembly using the exact catalog servo.
- The printable socket version is one valid solid with bounds approximately
  X -44.4 to 77.084989 mm, Y -3.6117 to 27.6117 mm, and Z -35.6 to 31.7 mm.
- In the fit preview, the servo rear face and socket stop both lie at
  X -29.9 mm; the installed servo extends to X -75.1234 mm. Per-solid boolean
  checks found no positive-volume servo/arm collision.

## Modeling contract

- Units are millimeters.
- Treat the imported STEP as an immutable BREP base. STEP import does not
  recover the original sketches, constraints, or feature history.
- Put every meaningful edit in named parameters near the top of
  the part's editable Python generator.
- Apply subtractive edits in part-local coordinates before posing the link.
- Apply rotations about a named pivot and document whether they are a design
  change or only an assembly pose.
- Keep booleans oversized through the target body to avoid coincident faces.
- Preserve closed positive-volume solids. If a cut creates multiple bodies,
  decide explicitly whether they are separate manufactured parts or should be
  rejoined by new geometry.
- Do not guess a servo mount from the case envelope. A horn-driven joint and a
  case-tab mount are different interfaces.

## Next fit decisions

Before treating the preliminary socket as a final printable attachment,
confirm or record:

1. Exact servo variant: ST3215 or ST3215-HS.
2. Interface type: output horn/spline, servo case tabs, or a yoke using both.
3. Which upper-arm end and face should meet the servo.
4. Neutral joint angle and intended rotation axis.
5. Screw/horn hardware, desired clearance, and 3D-printing process.
6. Cable exit direction and required motion clearance.

## Communicating requested edits

Prefer CAD Viewer's `Orthographic markup` workspace for new change requests. It
shows switchable front, back, top, bottom, right, and left views, accepts a typed note for every
view plus overall instructions, and exports flat PNG images with one
machine-readable JSON file. `Copy for Codex` copies only projections that have
marks or typed notes, so a single sufficient view can be pasted into a task.
The older flat reference image remains at
`upper_arm/reviews/upper_arm_change_markup_sheet.png`.

- Red means remove or cut.
- Green means add material.
- Blue means move or rotate; mark the pivot, axis, and angle.
- Purple means servo or other purchased hardware.
- Amber means a general note.

Every marked-up change should identify the exact region, at least one real
dimension in millimeters, the intended mating face, and any required cable or
motion clearance. Do not infer dimensions by measuring the fitted markup
views.

## Regeneration and review

From the repository root:

```powershell
python skills/cad/scripts/step models/robots/simple_drobot/references/so101/upper_arm/Upper_arm_SO101_editable.py
python skills/cad/scripts/inspect refs models/robots/simple_drobot/references/so101/upper_arm/Upper_arm_SO101_editable.step --facts --planes --positioning
python skills/cad/scripts/inspect diff models/robots/simple_drobot/references/so101/upper_arm/Upper_arm_SO101.step models/robots/simple_drobot/references/so101/upper_arm/Upper_arm_SO101_editable.step --planes
```

After any visible change, generate and review a CAD snapshot and open the
result through the CAD Viewer with the repository `models` directory as its
root.
