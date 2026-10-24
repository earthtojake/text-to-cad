"""Nine-cylinder supercharged radial -- the full, sectioned assembly.

One model, `radial`: the engine's eighteen
systems in occurrence (and explode) order, each a compound of its labelled parts.
Every system is a `@memo` stage below -- `lib/<system>.py`'s `build()`, each part
given the finish its colour names (`lib/palette.py`) -- so an edit that does not
reach a system's code replays it from the worker's memory instead of running it.

The mechanism is `lib/mechanism.py`'s (`assemble`): build123d joints on the parts its
label contract picks, standing at 0 as built (crank angle 0, cylinder 1 at firing TDC),
the gear train one coupling, `drive` (degrees of crank), two configurations, and the
`running` motion, the 720-degree four-stroke cycle in 8 s from `lib/kin.py`. Two GLB
animations join it (`lib/explode.py`): `explode`, the original's 24 s teardown, and
`exploded-running`, the cycle with the engine held partly apart and some parts hidden.
A GLB exported from the model carries all three as clips.
"""

from __future__ import annotations

from cadgen import memo, xbf

from lib import (
    accessory as accessory_lib,
    barrels as barrels_lib,
    blower as blower_lib,
    cam as cam_lib,
    crankcase as crankcase_lib,
    crankshaft as crankshaft_lib,
    exhaust as exhaust_lib,
    heads as heads_lib,
    ignition as ignition_lib,
    intake as intake_lib,
    mount as mount_lib,
    nose as nose_lib,
    pistons as pistons_lib,
    propeller as propeller_lib,
    pushrods as pushrods_lib,
    reduction as reduction_lib,
    rods as rods_lib,
    valvetrain as valvetrain_lib,
)
from lib import mechanism
from lib.palette import material_compound


@memo
def crankcase():
    """split power-section crankcase, cylinder pads, studs, main-bearing housings."""
    parts = crankcase_lib.build()
    if not parts:
        raise RuntimeError("lib/crankcase.py build() produced no parts")
    system = material_compound(parts, "crankcase", crankcase_lib.MATERIALS)
    return system


@memo
def crankshaft():
    """two-piece single-throw crankshaft, counterweights, main bearings, drive gears."""
    parts = crankshaft_lib.build()
    if not parts:
        raise RuntimeError("lib/crankshaft.py build() produced no parts")
    system = material_compound(parts, "crankshaft", crankshaft_lib.MATERIALS)
    return system


@memo
def rods():
    """master rod + flange, 8 knuckle pins + retainers, crankpin bearing, 8 articulating rods."""
    parts = rods_lib.build()
    if not parts:
        raise RuntimeError("lib/rods.py build() produced no parts")
    system = material_compound(parts, "rods", rods_lib.MATERIALS)
    return system


@memo
def pistons():
    """9 pistons, 54 rings, 9 wrist pins + plugs."""
    parts = pistons_lib.build()
    if not parts:
        raise RuntimeError("lib/pistons.py build() produced no parts")
    system = material_compound(parts, "pistons", pistons_lib.MATERIALS)
    return system


@memo
def barrels():
    """9 finned steel cylinder barrels + hold-down nuts."""
    parts = barrels_lib.build()
    if not parts:
        raise RuntimeError("lib/barrels.py build() produced no parts")
    system = material_compound(parts, "barrels", barrels_lib.MATERIALS)
    return system


@memo
def heads():
    """9 aluminium heads: deep fins, rocker boxes, covers, guides, seats, 18 spark plugs."""
    parts = heads_lib.build()
    if not parts:
        raise RuntimeError("lib/heads.py build() produced no parts")
    system = material_compound(parts, "heads", heads_lib.MATERIALS)
    return system


@memo
def valvetrain():
    """18 valves, springs, retainers, keepers, 18 rockers + shafts."""
    parts = valvetrain_lib.build()
    if not parts:
        raise RuntimeError("lib/valvetrain.py build() produced no parts")
    system = material_compound(parts, "valvetrain", valvetrain_lib.MATERIALS)
    return system


@memo
def cam():
    """cam ring, cam idler, 18 tappets + rollers."""
    parts = cam_lib.build()
    if not parts:
        raise RuntimeError("lib/cam.py build() produced no parts")
    system = material_compound(parts, "cam", cam_lib.MATERIALS)
    return system


@memo
def pushrods():
    """18 pushrods, 18 pushrod tubes, packing nuts, connectors."""
    parts = pushrods_lib.build()
    if not parts:
        raise RuntimeError("lib/pushrods.py build() produced no parts")
    system = material_compound(parts, "pushrods", pushrods_lib.MATERIALS)
    return system


@memo
def nose():
    """nose case, tappet guides, thrust-bearing housing, governor pad."""
    parts = nose_lib.build()
    if not parts:
        raise RuntimeError("lib/nose.py build() produced no parts")
    system = material_compound(parts, "nose", nose_lib.MATERIALS)
    return system


@memo
def reduction():
    """planetary reduction: bell gear, fixed sun, 6 planets, carrier, propeller shaft, thrust bearing."""
    parts = reduction_lib.build()
    if not parts:
        raise RuntimeError("lib/reduction.py build() produced no parts")
    system = material_compound(parts, "reduction", reduction_lib.MATERIALS)
    return system


@memo
def propeller():
    """hub, three blades, spinner, retention hardware."""
    parts = propeller_lib.build()
    if not parts:
        raise RuntimeError("lib/propeller.py build() produced no parts")
    system = material_compound(parts, "propeller", propeller_lib.MATERIALS)
    return system


@memo
def blower():
    """blower section, diffuser, impeller, impeller drive gears."""
    parts = blower_lib.build()
    if not parts:
        raise RuntimeError("lib/blower.py build() produced no parts")
    system = material_compound(parts, "blower", blower_lib.MATERIALS)
    return system


@memo
def intake():
    """9 intake pipes, couplings, carburettor."""
    parts = intake_lib.build()
    if not parts:
        raise RuntimeError("lib/intake.py build() produced no parts")
    system = material_compound(parts, "intake", intake_lib.MATERIALS)
    return system


@memo
def accessory():
    """accessory case, 2 magnetos, starter, generator, fuel + oil pumps, oil sump."""
    parts = accessory_lib.build()
    if not parts:
        raise RuntimeError("lib/accessory.py build() produced no parts")
    system = material_compound(parts, "accessory", accessory_lib.MATERIALS)
    return system


@memo
def ignition():
    """harness ring, 18 leads, plug elbows, magneto feeds."""
    parts = ignition_lib.build()
    if not parts:
        raise RuntimeError("lib/ignition.py build() produced no parts")
    system = material_compound(parts, "ignition", ignition_lib.MATERIALS)
    return system


@memo
def exhaust():
    """9 stacks, collector ring, outlet, clamps."""
    parts = exhaust_lib.build()
    if not parts:
        raise RuntimeError("lib/exhaust.py build() produced no parts")
    system = material_compound(parts, "exhaust", exhaust_lib.MATERIALS)
    return system


@memo
def mount():
    """engine mount ring, bosses, bushings, bolts."""
    parts = mount_lib.build()
    if not parts:
        raise RuntimeError("lib/mount.py build() produced no parts")
    system = material_compound(parts, "mount", mount_lib.MATERIALS)
    return system


# Declares its xbf, the corpus's example of a slow model's result kept across runs and
# engine restarts: a cold build takes most of an hour. Every body replays; a no-op without
# the file still samples the running motion again (5 s), which a run that takes it skips.
@xbf(out="../XBF/radial.xbf")
def radial():
    systems = [
        crankcase(), crankshaft(), rods(), pistons(), barrels(), heads(), valvetrain(), cam(), pushrods(),
        nose(), reduction(), propeller(), blower(), intake(), accessory(), ignition(), exhaust(), mount(),
    ]
    return mechanism.assemble(systems)


if __name__ == "__main__":
    radial()
