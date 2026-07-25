# ST3215 Rear Motor Bay

## Purpose

This folder owns a standalone, reusable holder for the rear body of the exact
Feetech/Waveshare ST3215 catalog servo. It is intentionally separate from the
SO-101 upper arm so it can later be attached to upper arms, lower arms, feet,
or other robot parts without copying fit-critical geometry.

## Source and generated artifacts

- `ST3215_rear_motor_bay.py` is the source of truth.
- `ST3215_rear_motor_bay.step` is generated; never edit it directly.
- `ST3215_rear_motor_bay_fit_preview.py` builds a non-printable fit assembly.
- `ST3215_rear_motor_bay_fit_preview.step` is the generated preview.
- `reviews/` contains verification snapshots.
- The exact purchased-part source is
  `models/robots/lekiwi_quadruped/components/waveshare_feetech_st3215_servo.step`.

## Reuse contract

- Units are millimeters.
- The flat attachment datum is the outer YZ face at `X = 0`.
- The bay extends from `X = -16` to `X = 0`.
- The servo inserts from negative X and seats against the rim at `X = -1.5`.
- The central opening through the attachment rim is reserved for cabling.
- Import `gen_step()` into a future part and fuse or glue the `X = 0` perimeter
  face to that part. Keep the component in these local coordinates until the
  consuming part supplies its placement.
- Do not silently add this component to an existing limb. Make that attachment
  as a separate, explicit change after its pose and mating face are confirmed.

## Current fit assumptions

- Exact rear-case geometry, including keyed case steps, defines the cavity.
- Clearance is 0.25 mm per global-Y side and 0.125 mm per global-Z side.
- Wall thickness is 3.0 mm.
- Stop-rim thickness is 1.5 mm.
- Cable window is 16 x 14 mm.
- Four vertical servo-mount access holes use the verified 20.5 mm Y spacing:
  the top pair is at `X = -6.8117`, the bottom pair at `X = -3.0617`, and
  both pairs are at `Y = +/-10.25`.
- Each access path has a 2.0 mm inner pilot with a 4.0 mm outside access
  relief. The 4.0 mm opening passes through the complete 3.0 mm wall and ends
  flush with its inner face; the 2.0 mm pilot then continues 2.8 mm toward the
  servo, ending at `Z = +/-16.225`. Four local 6 x 6 mm cleanup pockets remove
  the complete reverse-imprinted protrusions around those holes. Only these
  four pockets reach the access-channel limits at `Z = 14/-13`; they must not
  become a cavity-wide slab because all exact servo-profile fitting grooves
  outside the four local pockets must remain intact. These dimensions and step
  direction reproduce the matching 20.5 mm-spaced pattern inspected in the
  original SO-101 upper arm; the unrelated 5.4/3.0 mm pattern elsewhere on that
  arm is not used here.

These are preliminary FDM test-fit values. Confirm the physical servo variant,
printer, material, shrinkage, and preferred retention method before treating
them as production dimensions. Also verify screw-head diameter and screw length
against the physical servo before assembly; the STEP geometry establishes the
axes, but does not encode the supplied fastener specification.

## Validation

Regenerate the part and preview, inspect both, and confirm that per-solid
servo/bay intersections have zero positive volume. After visible changes,
create snapshots and hand both STEP files to CAD Viewer.
