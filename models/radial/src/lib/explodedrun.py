"""The `exploded-running` clip: the engine RUNS while it hangs partly exploded.

Layout only. The clip (lib/clips.py) reads it as the engine builds,
lib/animcheck.py checks the clip against kin.py composed with these offsets, and
`python -m lib.gate --clip exploded-running` checks its interference.

Every visible leaf gets its running motion from kin.py EXACTLY as in `running`
(pose(theta) o pose(0)^-1, spring tube deformation), then ONE constant
translation: its group's offset below. The offsets never change, so the clip
is the same seamless 720 deg loop as `running`.

The design (read with the three-quarter front camera in mind):

* The crank train stays assembled at the centre and is never offset: crankshaft,
  counterweights, master rod, knuckle pins, eight articulating rods, nine
  pistons, and the crank's cam drive gear. It is the subject.
* Each cylinder (barrel + hold-down nuts + head + valves + springs + rockers +
  rocker shafts + plugs + PUSHRODS) moves OUT along its own bore by R_CYL, so
  its barrel skirt clears the piston crown at TDC: all nine pistons slide in
  free air under their floating cylinders, rings exposed, in firing order.
  Its two rocker covers lift a further COVER_LIFT so the rockers show.
* Valvetrain compromise: the pushrods ride with their cylinder, seated in the
  rocker sockets, and keep their full kin.py motion (lift + swing), so the
  pushrod -> rocker -> valve -> spring chain stays one working unit at every
  head. Their lower ends therefore float R_CYL (plus the cam section's axial
  offset) away from the tappets, which stay in their guides in the cam section
  and lift on the turning cam ring. The pushrod TUBES are hidden: they would
  sheathe the pushrods and connect nothing.
* The crankcase opens axially: the front half forward, the rear half back.
  Ahead of it the nose stack spreads forward in three steps: the cam section
  (rear nose casting + cam ring at 1/8 against the crank + idler + tappets),
  then the nose case with the planetary reduction (the crank's bell gear rides
  with it, still spinning at crank speed and meshing with the planets; the fixed
  sun; the carrier = propeller shaft at 2/3), then the propeller at 2/3.
  The idler is lifted off the crank's cam gear by the cam-section offset (the
  gear cannot slide forward: the nose shaft ahead of it is wider than its bore).
* Behind, the blower section moves back with its whole 10:1 train (the crank's
  blower gear rides with it, still at crank speed, meshing with the three
  intermediates and the impeller pinion); the accessory case moves further back.
* Hidden: the three propeller blades (2.6 m of blade sweeping in front of a
  three-quarter camera hides the crank train for part of every revolution; the
  hub, clamp rings and spinner still turn at 2/3), ignition harness and leads,
  exhaust, intake and carburettor, engine mount, pushrod tubes, the crankcase
  through-bolts (they tie both halves), and the fuel line (accessory case to
  carburettor).
"""

from __future__ import annotations

import math
import re

CLIP = "exploded-running"

R_CYL = 205.0          # mm, every cylinder group out along its bore: skirt (h 205) clears the TDC crown (h 400)
COVER_LIFT = 60.0      # mm, rocker covers further out along the bore
AXIAL = {              # mm along +Y (+Y = rear)
    "front_half": -190.0,
    "cam": -310.0,
    "nose": -430.0,
    "prop": -540.0,
    "rear_half": 170.0,
    "blower": 300.0,
    "accessory": 430.0,
}

HIDE = re.compile(r"(ignition|exhaust|intake|mount|pushrods):.*|prop:blade_\d"
                  r"|crankcase:through_(bolt|nut)_\d+"
                  r"|accessory:fuel_line.*")

# (regex, group). First match wins. "cyl" and "cover" rules capture the cylinder number k.
RULES = [
    # --- the crank train: never offset (the bell gear and the blower gear ride with their trains)
    (r"crank:bell_.*", "nose"),
    (r"crank:blower_gear.*", "blower"),
    (r"(crank|master|artrod\d|piston\d):.*", "core"),
    # --- cylinder k and its rocker covers
    (r"heads:(section_skin_)?cover_(?P<k>\d)[IE]", "cover"),
    (r"heads:cover_(bolt|wire)_(?P<k>\d)[IE]_\d+", "cover"),
    (r"barrels:(barrel_|section_skin_|hold_down_nut_|hold_down_washer_|safety_wire_)(?P<k>\d).*", "cyl"),
    (r"heads:(section_skin_)?(head|seat|guide|chamber_lining|plug|exhaust_stud|exhaust_nut)_(?P<k>\d).*", "cyl"),
    (r"(valve|spring|rocker|pushrod)(?P<k>\d)[IE]:.*", "cyl"),
    (r"valvetrain:(rocker_shaft|shaft_nut|shaft_washer|spring_seat)_(?P<k>\d)[IE].*", "cyl"),
    # --- crankcase halves (studs 07-12 are screwed into the front half, 01-06 the rear)
    (r"crankcase:(section_skin_)?front_half|crankcase:pad_face_front_\d|crankcase:stud_\d_(0[7-9]|1[0-2])"
     r"|crankcase:nose_stud_\d+|crankcase:drain_front_.*|crankshaft:front_main_outer", "front_half"),
    (r"crankcase:(rear_half|pad_face_rear_\d|stud_\d_0[1-6]|lifting_eye.*|drain_rear_.*|scavenge_.*|blower_stud_\d+)"
     r"|crankshaft:rear_main_outer", "rear_half"),
    # --- nose stack
    (r"nose:(section_skin_)?(case_rear|flange_face).*|nose:flange_nut_\d+|crankcase:nose_nut_\d+"
     r"|cam:.*|camring:.*|camidler:.*|tappet\d[IE]:.*", "cam"),
    (r"prop:.*|propshaft:hub_(nut|cotter)", "prop"),
    (r"nose:.*|reduction:.*|planet\d:.*|propshaft:.*", "nose"),
    # --- rear stack
    (r"accessory:.*|blower:accessory_nut_\d+", "accessory"),
    (r"blower:.*|impeller:.*|blowergear\d:.*|crankcase:blower_nut_\d+", "blower"),
]
_RULES = [(re.compile(rx), g) for rx, g in RULES]


def u_cyl(k):
    """Bore axis of cylinder k (spec.cyl_u): the unit vector at in-plane angle 40 (k - 1)."""
    a = math.radians(40.0 * (k - 1))
    return (-math.sin(a), 0.0, math.cos(a))


def group_of(label):
    """Group name of a leaf label, or None when the clip hides it. Raises on an unplanned label."""
    if HIDE.fullmatch(label):
        return None
    for rx, g in _RULES:
        m = rx.fullmatch(label)
        if m:
            if g in ("cyl", "cover"):
                return f"{g}{m.group('k')}"
            return g
    raise ValueError(f"exploded-running: no layout rule for label {label!r} (add one to lib/explodedrun.py)")


def offset(group):
    """Constant translation (mm) of a group."""
    if group == "core":
        return (0.0, 0.0, 0.0)
    if group.startswith(("cyl", "cover")):
        k = int(group[-1])
        d = R_CYL + (COVER_LIFT if group.startswith("cover") else 0.0)
        u = u_cyl(k)
        return (u[0] * d, 0.0, u[2] * d)
    return (0.0, AXIAL[group], 0.0)


def layout(labels):
    """({group: [labels]}, {group: offset}, [hidden labels]) for the built assembly's labels."""
    groups, hidden = {}, []
    for lab in sorted(set(labels)):
        g = group_of(lab)
        if g is None:
            hidden.append(lab)
        else:
            groups.setdefault(g, []).append(lab)
    return groups, {g: offset(g) for g in groups}, hidden


def label_offsets(labels):
    """{label: offset} for every visible label, and the hidden set."""
    groups, offs, hidden = layout(labels)
    return {lab: offs[g] for g, labs in groups.items() for lab in labs}, set(hidden)
