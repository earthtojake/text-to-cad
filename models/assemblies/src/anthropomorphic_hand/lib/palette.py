"""The shipped palette: one total rule from occurrence name to surface finish.

This is the only place the assembled hand's colour is decided. Read it to know
what colour any of the 3,259 bodies in ``hand_mechanical_candidate_r13.step``
is, and why it is that colour.

Two ideas carry the whole model.

1. A CORD IS COLOURED BY THE JOINT IT DRIVES.

   Each of the 48 cords runs from its own forearm spool, through the guides,
   to exactly one of the 24 joints. Its colour therefore names the motion it
   makes, so a reader can follow one cord from the motor pack to the finger it
   moves without a legend:

       red     flexion / curl        MCP flexion, thumb CMC + MCP flexion,
                                     wrist flexion, and the palm cup
       green   abduction / spread    MCP abduction, thumb CMC + MCP abduction,
                                     wrist abduction
       blue    PIP, the middle joint
       yellow  DIP / IP, the tip joint

   That partitions the cords 16 red / 14 green / 8 blue / 10 yellow, and
   :func:`cord_finish` raises rather than defaulting if a joint ever appears
   that names none of those four motions.

   ANTAGONIST PAIRS SHARE A HUE. The two cords on a joint are one system, so
   they take one colour: the ``_positive`` cord gets the saturated hue and the
   ``_negative`` cord the same hue mixed 45 % toward white, which reads at a
   glance as which half of the pair is pulling and which is paying out.

   Cords are dyed braided fibre, not metal: both sides keep the cord material
   (roughness .57, metalness .03) whatever their hue.

2. EVERYTHING STRUCTURAL IS ONE ALUMINIUM GREY.

   Frames, phalanges, carriers, pulleys, capstans, shafts, bushings, ferrules,
   gearbox internals and all 1,061 fasteners are the single aluminium grey
   ``#a9b7c1`` with the aluminium finish. One grey means the eye stops sorting
   hardware by shade and reads the cords instead.

   Four families are deliberately not folded into it, because each one is a
   different physical material and reads as one:

       dark #17242d   the anodised actuator pack -- motor cases, gearbox
                      housings, the forearm chassis and its jaws, the bonded
                      strain gauges and the resin bond lines, and the
                      compliant backings under the pads and nails
       pad  #ede8da   the silicone fingertip and palm pads
       black #242a2b  the silicone cable grommets at the forearm exits
       liner #d5e7e5  the translucent bowden liner (alpha .28)

The rule is total on purpose. :func:`finish_for` raises ``ValueError`` on an
occurrence kind it has never been told about, so a new part family shows up as
a failed build rather than as a body that quietly ships the default grey.

``FINISHES`` and :func:`lib.finish.finish` remain the authoring-time surface
languages used by the procedural factories; ``steel`` still exists there for
the sub-assembly studies, but the assembled hand no longer uses it -- the
palette below folds steel into aluminium.
"""

# --- physical surfaces ------------------------------------------------------
# Roughness/metalness/clearcoat as the CAD Viewer's per-part PBR override.

ALUMINUM = {"roughness": .34, "metalness": .86, "clearcoat": .12}
ANODIZED = {"roughness": .32, "metalness": .68, "clearcoat": .16}
STEEL = {"roughness": .12, "metalness": .98, "clearcoat": .25}
SILICONE = {"roughness": .67, "metalness": .01, "clearcoat": .04}
CORD = {"roughness": .57, "metalness": .03}
# `opacity` HERE, not only on the colour. A shape's colour carries alpha, but
# the GLB exporter converts colour to a hex string on the way into the file and
# hex has no alpha channel, so a liner declared translucent only through its
# colour arrives opaque -- 170 near-white tubes running the length of the hand,
# which is exactly what they looked like. `cad_material` survives that trip.
LINER = {"roughness": .30, "metalness": .05, "opacity": .28}

# The structural frame is the SAME anodised black as the actuator pack: one
# machine, one finish. It keeps the aluminium material (metalness .86) rather
# than the anodised one, so it still reads as machined metal and not as paint.
FRAME_COLOR = "#17242d"
DARK_COLOR = "#17242d"
PAD_COLOR = "#ede8da"
GROMMET_COLOR = "#242a2b"
LINER_COLOR = "#d5e7e5"
LINER_ALPHA = .28

# --- the four cord hues -----------------------------------------------------
# Keyed by the motion the driven joint makes, not by the finger.

CORD_HUES = {
    "flexion": "#d2372c",    # red    -- curl
    "abduction": "#3f9e58",  # green  -- spread
    "pip": "#2f6fd0",        # blue   -- the middle joint
    "tip": "#e0b325",        # yellow -- DIP / IP, the fingertip joint
}

CORD_TINT = .45  # how far the paying-out (negative) cord is mixed toward white

# A joint names its motion in its own name. Ordered longest-first so that
# ``_pip`` is never mistaken for the ``_ip`` of the thumb.
JOINT_MOTION_SUFFIXES = (
    ("_pip", "pip"),
    ("_dip", "tip"),
    ("_ip", "tip"),
    ("_flexion", "flexion"),
    ("_abduction", "abduction"),
)
# The palm cup curls the hand around what it holds; it is a flexion.
JOINT_MOTION_EXACT = {"palm_cup": "flexion"}

CORD_SIDES = ("positive", "negative")


def tint(color, fraction=CORD_TINT):
    """``color`` mixed ``fraction`` of the way toward white, in sRGB."""
    text = color.lstrip("#")
    channels = (int(text[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(
        round(c + fraction * (255 - c)) for c in channels)


def joint_motion(joint):
    """Which of the four motions ``joint`` makes. Raises on an unknown joint."""
    if joint in JOINT_MOTION_EXACT:
        return JOINT_MOTION_EXACT[joint]
    for suffix, motion in JOINT_MOTION_SUFFIXES:
        if joint.endswith(suffix):
            return motion
    raise ValueError(
        f"{joint!r} names none of the four cord motions "
        f"{sorted(CORD_HUES)}; give it a hue before shipping its cords")


def cord_finish(name):
    """``(motion, color)`` for a cord named ``<joint>_<positive|negative>``."""
    for side in CORD_SIDES:
        if name.endswith("_" + side):
            joint = name[:-len(side) - 1]
            break
    else:
        raise ValueError(
            f"{name!r} is not a cord: expected a name ending in "
            f"{' or '.join('_' + s for s in CORD_SIDES)}")
    motion = joint_motion(joint)
    color = CORD_HUES[motion]
    return motion, (color if side == "positive" else tint(color))


def cord_language(name):
    """The :data:`FINISHES` key for a cord named ``<joint>_<positive|negative>``."""
    motion, _ = cord_finish(name)
    return f"cord_{motion}_{name.rsplit('_', 1)[1]}"


# The cord languages, spelled so :func:`lib.finish.finish` can name one
# directly. These replace the retired ``tendon_flex`` / ``tendon_extend`` pair;
# there is no generic cord colour any more, only a motion and a side.
CORD_FINISHES = {
    f"cord_{motion}_{side}": (
        (color if side == "positive" else tint(color)), CORD)
    for motion, color in CORD_HUES.items() for side in CORD_SIDES
}

# The hardware surface languages. Kept separate from the cord hues because
# native_integration.overlay() infers a material for an imported body by
# nearest colour, and an imported grey must never land on a cord's fibre
# material just because a cord hue happens to sit nearer in RGB.
HARDWARE_FINISHES = {
    "aluminum": (FRAME_COLOR, ALUMINUM),
    "dark": (DARK_COLOR, ANODIZED),
    "steel": ("#d3dbe1", STEEL),
    "pad": (PAD_COLOR, SILICONE),
}

# The authoring-time surface languages, re-exported by :mod:`lib.finish`.
FINISHES = {**HARDWARE_FINISHES, **CORD_FINISHES}

# --- which bodies are not aluminium -----------------------------------------

# Kinds whose bodies are the anodised actuator pack.
DARK_KINDS = frozenset({
    "motor_case",             # 48 -- the visible motor can
    "gearbox_housing",        # 48 -- the planetary can bolted to it
    "drive_terminal_bond_line",    # 48 -- resin, at the driven pulley
    "capstan_terminal_bond_line",  # 48 -- resin, at the forearm spool
    "pad_mount",              # 8  -- compliant backing under a silicone pad
    "nail_mount",             # 5  -- compliant saddle under a fingernail
})
DARK_NAME_MARKS = ("_bonded_strain_gauge_",)  # 144, inside the cartridges

TRANSLUCENT_KINDS = frozenset({"guide"})           # 170 bowden liners
PAD_KINDS = frozenset({"fingertip_pad", "palm_pad"})  # 8 silicone pads
GROMMET_SUFFIX = "_silicone_grommet"               # 4 cable-exit grommets

# The forearm's own shell -- chassis, flange, side frames, portal and exit-
# bridge jaws, tie anchors, rail-clamp caps -- is the motor pack's housing and
# stays anodised with it. Its screws are hardware and go grey with the rest.
CHASSIS_KINDS = frozenset({"frame", "guide_mount"})
CHASSIS_MARK = "forearm"

# Everything else. Listed rather than defaulted so that a part family this
# palette has never seen fails the build instead of shipping the default grey.
FRAME_KINDS = frozenset({
    # hand and wrist structure
    "frame", "phalanx", "carrier", "fingernail", "hub_spacer",
    # routing hardware
    "guide_mount", "fastener",
    # joints
    "shaft", "bushing", "retaining_ring",
    # the driven terminal at each joint
    "drive_pulley", "drive_pulley_grub_screw", "drive_terminal_cover",
    "drive_terminal_cover_screw", "drive_terminal_ferrule",
    # the forearm spool
    "capstan", "terminal_ferrule", "tension_cartridge",
    # motor internals that are not the anodised can
    "motor_endcap", "motor_shaft",
    # gearbox internals
    "gearbox_ring", "gearbox_sun", "gearbox_carrier", "gearbox_bearing",
    "gearbox_spindle",
    "gearbox_planet_1", "gearbox_planet_2", "gearbox_planet_3",
    "gearbox_planet_pin_1", "gearbox_planet_pin_2", "gearbox_planet_pin_3",
})

# The buckets, in the order a body is tested against them. The name is the one
# a report prints; the counts a full hand must land in are asserted by
# :func:`census`.
BUCKETS = ("cord_flexion", "cord_abduction", "cord_pip", "cord_tip",
           "bowden_liner", "silicone_pad", "silicone_grommet",
           "anodized_dark", "aluminum_frame")

EXPECTED_CORDS = {"cord_flexion": 16, "cord_abduction": 14,
                  "cord_pip": 8, "cord_tip": 10}


def finish_for(name, kind):
    """``(bucket, color, material, alpha)`` for one occurrence.

    Total by construction: an occurrence whose ``kind`` this palette has never
    been told about raises, rather than silently taking the frame grey.
    """
    if kind == "tendon":
        motion, color = cord_finish(name)
        return f"cord_{motion}", color, CORD, 1.
    if kind in TRANSLUCENT_KINDS:
        return "bowden_liner", LINER_COLOR, LINER, LINER_ALPHA
    if kind in PAD_KINDS:
        return "silicone_pad", PAD_COLOR, SILICONE, 1.
    if name.endswith(GROMMET_SUFFIX):
        return "silicone_grommet", GROMMET_COLOR, SILICONE, 1.
    if kind in DARK_KINDS or any(mark in name for mark in DARK_NAME_MARKS):
        return "anodized_dark", DARK_COLOR, ANODIZED, 1.
    if kind in CHASSIS_KINDS and CHASSIS_MARK in name and "screw" not in name:
        return "anodized_dark", DARK_COLOR, ANODIZED, 1.
    if kind in FRAME_KINDS:
        return "aluminum_frame", FRAME_COLOR, ALUMINUM, 1.
    raise ValueError(
        f"{name!r}: the palette has no rule for kind {kind!r}; add it to "
        f"FRAME_KINDS or to one of the named exceptions")


def census(rows):
    """Bucket every ``{'name','kind'}`` row; assert the cord split is intact.

    ``rows`` is the ``mechanical_candidate_r13_frames.json`` shape, so this
    runs against the recorded body list without touching CAD.
    """
    counts = {bucket: 0 for bucket in BUCKETS}
    for row in rows:
        counts[finish_for(row["name"], row["kind"])[0]] += 1
    cords = {bucket: counts[bucket] for bucket in EXPECTED_CORDS}
    if cords != EXPECTED_CORDS:
        raise ValueError(f"cord split is {cords}, expected {EXPECTED_CORDS}")
    return counts


def apply_palette(bodies):
    """Recolour every :class:`lib.assembly.Body` in place; return the census.

    Runs last, on the shapes the exporter will read ``color`` and
    ``cad_material`` off, so this is what the written STEP and the store
    package carry.
    """
    from cadgen import srgb
    for body in bodies:
        _, color, material, alpha = finish_for(body.name, body.kind)
        body.shape.color = srgb(color, alpha)
        body.shape.cad_material = dict(material)
    return census([dict(name=b.name, kind=b.kind) for b in bodies])
