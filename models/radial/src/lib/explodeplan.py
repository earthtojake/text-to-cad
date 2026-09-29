"""The exploded view, planned from the built assembly.

    cd src && python -m lib.explodeplan [--recompute]     # plan -> tmp/kin/explode_plan.json

Everything moves by TRANSLATION from the theta = 0 rest pose. The plan is built
in four passes:

1. UNITS. Every leaf belongs to one rigid unit (RULES below, first match wins):
   a unit is what separates as one piece (a cylinder = barrel + head + valves +
   springs + plugs; a rocker = arm + bearing + adjuster + locknut; ...). Section
   skins ride with the part they skin. Fasteners and retaining hardware (labels
   ending bolt/nut/stud/screw/washer/pin/clip/clamp/wire/cotter/retainer) not
   named by a rule are units of their own; studs stay in the part they are
   screwed into.
2. DIRECTIONS. Each unit leaves along its own assembly axis (a cylinder radially
   along its bore, a pushrod along itself, an axial part along the crank
   axis, a fastener along its own axis, found by PCA of its vertices).
3. BLOCKING. For every unit and candidate direction: which other units does its
   straight exit path hit (surface-sample screen, confirmed by the exact OCC
   boolean: common volume > 0.5 mm^3)? Cached per document.
4. SEQUENCE. The brief's stage order is the priority; a unit is scheduled once
   every unit blocking its exit has gone, so a physically required prerequisite
   is pulled forward (and reported) instead of passing through. A fastener
   leaves along its axis immediately before the unit it holds (the touching
   unit that leaves first), then rides with it; a fastener whose own exit is
   blocked by its host (a nut under a fin) moves only as far as it is free,
   then rides along.

The timeline and travel distances (layout) are STAGES below. lib/animgen.py
turns the plan into the `explode` clip; lib/explodecheck.py verifies it.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import os
import re
import sys
import time
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parent.parent
ROOT = SRC.parent
STEP_FILE = ROOT / "STEP" / "radial.step"
OUT = ROOT / "tmp" / "kin" / "explode_plan.json"

FIRING = (1, 3, 5, 7, 9, 2, 4, 6, 8)
F, R = (0.0, -1.0, 0.0), (0.0, 1.0, 0.0)


def u_cyl(k):
    a = math.radians(40.0 * (k - 1))
    return (-math.sin(a), 0.0, math.cos(a))


# ---------------------------------------------------------------------------
# 1. Units: (regex, unit name template, direction spec, stage, order-in-stage)
#    direction specs: F, R, down, cyl (bore axis of cylinder k), rad (radial
#    from the unit's centre), tappet, pushrod, artrod, axis (PCA axis, either
#    sign), fixed (datum), or a list of those tried in order.
# ---------------------------------------------------------------------------
def rules(labels):
    """The unit rules for this build (first match wins). Parts that only exist after a
    builder's split (blower rear cover, nose front/rear castings, crank bell flange) switch
    their neighbours from 'captive' to 'movable' automatically."""
    L = set(labels)
    blower_split = "blower:rear_cover" in L
    nose_split = "nose:case_front" in L
    R_ = [
        # --- 1 propeller: blades slide off their shanks along their own axes, then straight
        #     forward; the hub (both halves + clamp rings, locked together) follows
        (r"prop:front_cone", "prop_cone", "F", 1, 0.2),
        (r"prop:blade_(?P<j>\d)", "prop_blade_{j}", "blade", 1, 0.5),
        (r"prop:(hub_front|hub_rear|clamp_ring_\d)", "prop_hub", "F", 1, 0.8),
        # --- 2 nose front pieces lift forward; the reduction comes out forward piece by piece
        #     (measured axial order: rear cone, front cover, liner, thrust-bearing pair, shaft,
        #     thrust housing with its captive sun, planets one by one, carrier, bell gear)
        (r"propshaft:rear_cone", "rear_cone", "F", 2, 0.1),
        (r"nose:(section_skin_)?front_cover", "nose_cover", "F", 2, 0.15),
        (r"nose:(section_skin_)?thrust_liner(_\d)?", "nose_liner", "F", 2, 0.2),
        (r"reduction:thrust_outer|propshaft:thrust_(inner|balls)", "thrust_bearing", "F", 2, 0.25),
        (r"propshaft:shaft", "propshaft", "F", 2, 0.3),
        (r"nose:(section_skin_)?thrust_housing(_\d)?|reduction:(sun|sun_support|sun_front_bushing|sun_rear_bushing)",
         "nose_thrust_housing", "F", 2, 0.35),
        (r"planet(?P<j>\d):(gear|bearing)", "planet_{j}", "F", 2, 0.5),
        (r"propshaft:carrier", "carrier", "F", 2, 0.6),
        # (DEVIATION: the bell gear leaves bolted to its flange; its nuts have no free exit between them)
        (r"crank:bell_.*", "bell_gear", "F", 2, 0.7),
        # --- 3 the 17 elbows unplug along their plug axes (their nuts first)
        (r"ignition:elbow_(?P<k>\d)(?P<p>[FR])", "elbow_{k}{p}", "plug", 3, 0.2),
        # (DEVIATION, measured: each magneto feed lies between the cylinder-3/8 pads of both case
        #  halves - 22 mm forward, 42 mm rearward - so it lifts out sideways once its cylinder is off)
        (r"ignition:feed_(terminal_)?L", "ign_feed_L", ["rad", "F", "R"], 6, 0.9),
        (r"ignition:feed_(terminal_)?R", "ign_feed_R", ["rad", "F", "R"], 6, 0.9),
        # --- 4 exhaust stacks slide rearward; the collector ring rearward as one piece, then fans
        # (measured: each stack-end band clamp holds stack and collector together; it slides up
        #  the stack first, then the collector ring leaves rearward off the stack ends)
        (r"exhaust:clamp_stack_(?P<k>\d)", "exh_band_{k}", ["F", "axis"], 4, 0.25),
        (r"exhaust:(section_skin_)?(collector_[a-z0-9]+|clamp_ring_\d|clamp_outlet)", "exh_collector_{name}", ["rad", "R"], 4, 0.3),
        (r"exhaust:(stack|stack_band|stack_blue|stack_flange|gasket)_(?P<k>\d)", "exh_stack_{k}", ["R", "axis", "rad"], 4, 0.4),
        (r"intake:(section_skin_)?(pipe|hose|elbow)_(?P<k>\d).*", "intake_{k}", "rad", 4, 0.6),
        (r"intake:carb_.*", "carburettor", "down", 4, 0.8),
        # --- 5 rocker covers, rocker shafts, rockers, pushrod tubes, pushrods, tappets, then the
        #     nose case (front casting) forward
        (r"heads:(section_skin_)?cover_(?P<k>\d)(?P<v>[IE])", "cover_{k}{v}", ["cyl", "axis"], 5, 0.1),
        (r"valvetrain:rocker_shaft_(?P<k>\d)(?P<v>[IE])", "rshaft_{k}{v}", ["F", "R"], 5, 0.2),
        (r"rocker(?P<k>\d)(?P<v>[IE]):.*", "rocker_{k}{v}", ["cyl", "axis"], 5, 0.3),
        (r"pushrods:(section_skin_)?(tube|packing_gland)_(?P<k>\d)(?P<v>[IE]).*", "tube_{k}{v}", "pushrod", 5, 0.4),
        (r"pushrod(?P<k>\d)(?P<v>[IE]):.*", "pushrod_{k}{v}", "pushrod", 5, 0.5),
        (r"(cam:tappet_(guide|liner)_|tappet)(?P<k>\d)(?P<v>[IE]).*", "tappet_{k}{v}", "tappet", 5, 0.7),
    ]
    if nose_split:
        R_ += [
            # the idler meshes inside the cam ring: ring + idler + its shaft leave as one, forward
            # off the rear casting's hub, once the front casting has gone
            # (DEVIATION, circular: the crankcase front half cannot pass the rear nose case and the cam
            #  ring in front of it, which cannot leave before it: the three leave forward together)
            (r"camidler:.*|cam:idler_(shaft|washer|nut)|camring:.*", "case_front", "F", 8, 0.1),
            (r"nose:(section_skin_)?case_rear.*|nose:flange_face.*", "case_front", "F", 8, 0.1),
            (r"nose:.*", "nose_case", "F", 5, 0.9),
        ]
    else:
        R_ += [
            (r"camidler:.*|cam:idler_(shaft|washer|nut)", "cam_idler", "F", 5, 0.8),
            (r"nose:.*", "nose_case", "F", 5, 0.9),
        ]
    R_ += [
        # --- 6 cylinders (barrel + head + valves + springs + seats + guides + plugs) bloom in
        #     firing order; then the ignition web (ring + 18 leads) lifts forward intact
        (r"barrels:(section_skin_)?barrel_(?P<k>\d)|barrels:section_skin_(?P<k2>\d)", "cyl_{k}", "cyl", 6, 0.5),
        (r"heads:(section_skin_)?(head|guide|seat|plug|chamber_lining)_(?P<k>\d).*", "cyl_{k}", "cyl", 6, 0.5),
        (r"(valve|spring)(?P<k>\d)[IE]:.*|valvetrain:spring_seat_(?P<k2>\d)[IE]", "cyl_{k}", "cyl", 6, 0.5),
        (r"ignition:.*", "ignition", "F", 6, 0.9),
        # --- 7 pistons slide off their rods (pin plugs + wrist pins out sideways first)
        (r"piston(?P<k>\d):(section_skin_)?(piston|ring_\d)", "piston_{k}", "cyl", 7, 0.5),

        # --- 8 crankcase front half forward (the rear half is backed by the blower: it leaves
        #     forward in step 9); knuckle pins out, the eight rods fan from the flange
        # (the main-bearing outer races sit in their case halves' bores and leave with them)
        (r"crankcase:(section_skin_)?front_half|crankcase:pad_face_front_\d|crankshaft:front_main_outer", "case_front", "F", 8, 0.1),
        # (DEVIATION, measured: a knuckle pin can only be drawn 13 mm before the crank cheek stops it,
        #  so the eight rods leave with the master rod as one rod assembly, knuckle hardware in place)
        (r"artrod\d:.*|master:.*", "master", ["F", "R"], 9, 0.45),
        # --- 9 accessory section rearward; blower rear cover + internals rearward; cam ring
        #     forward off its hub; crank halves, master, crankcase rear half along the axis
        (r"accessory:.*", "accessory", "R", 9, 0.1),
        (r"camring:.*", "cam_ring", "F", 9, 0.2),
        (r"master:(rod|crankpin_bearing|small_end_bushing)", "master", ["cyl1", "F", "R"], 9, 0.3),
        (r"crank:(front_crank|front_counterweight|front_cw_bushing_\d|front_main_inner|crankpin_front_plug|cam_gear|cam_gear_key)",
         "crank_front", "F", 9, 0.4),

        (r"crank:(rear_crank|rear_counterweight|rear_cw_bushing_\d|rear_main_inner|crankpin_rear_plug|clamp_bolt|clamp_nut|clamp_cotter)",
         "crank_rear", ["F", "R"], 9, 0.6),
        (r"crankcase:(section_skin_)?rear_half|crankcase:pad_face_rear_\d|crankcase:lifting_eye_\d|crankshaft:rear_main_outer",
         "case_rear", ["F", "R"], 9, 0.8),
    ]
    if blower_split:
        R_ += [
            # (blower builder's measured rearward order: rear cover, impeller unit, diffuser,
            #  diaphragm, the three intermediate gears off their shafts, crank blower gear)
            (r"blower:(section_skin_)?rear_cover.*|blower:accessory_(face|stud_\d+)|blower:bearing_outer_rear", "blower_cover", "R", 9, 0.15),
            (r"impeller:.*", "impeller", "R", 9, 0.16),
            (r"blower:diffuser", "blower_diffuser", "R", 9, 0.17),
            (r"blower:diaphragm|blower:bearing_outer_front", "blower_diaphragm", "R", 9, 0.175),
            (r"blowergear(?P<j>\d):.*", "blowergear_{j}", "R", 9, 0.18),
            (r"crank:(blower_gear|blower_gear_spacer|blower_gear_lock_ring)", "crank_blower_gear", "R", 9, 0.19),
        ]
    else:
        R_ += [(r"impeller:.*|blowergear\d:.*|crank:(blower_gear|blower_gear_spacer|blower_gear_lock_ring)",
                "datum", "fixed", 0, 0.0)]
    # the datum: mount ring + blower case (the mount sleeves run through the blower pads)
    R_ += [(r"blower:.*|mount:.*", "datum", "fixed", 0, 0.0)]
    return R_


RULES = rules([])

# Stage windows (seconds) and travel. The clip is START..END, then held.
STAGES = {
    1: (0.0, 2.6), 2: (2.6, 5.0), 3: (5.0, 6.2), 4: (6.2, 7.6), 5: (7.6, 11.2),
    6: (11.2, 14.6), 7: (14.6, 16.2), 8: (16.2, 18.6), 9: (18.6, 21.4),
}
DURATION = 23.0


# ---------------------------------------------------------------------------
# Geometry-backed pieces
# ---------------------------------------------------------------------------
def _pca_axis(P):
    """(principal axis, elongation ratio) of a point cloud: the long axis of a
    bolt, the short axis (ring axis) of a nut/washer."""
    C = P - P.mean(axis=0)
    w, V = np.linalg.eigh(C.T @ C / max(len(P), 1))
    return V, w


def fastener_axis(P, label):
    V, w = _pca_axis(P)
    tail = label.split(":", 1)[-1]
    flat = any(s in tail for s in ("nut", "washer", "retainer", "clip", "pin_plug"))   # a pin plug caps the pin bore
    ax = V[:, 0] if flat else V[:, 2]           # flat: smallest-variance axis; long: largest
    return ax / np.linalg.norm(ax)


# hardware that leaves inside its sub-assembly instead of on its own (documented deviations)
FORCE_PART = r"master:|artrod\d:|crank:bell_|crank:clamp_(bolt|nut|cotter)$|cam:idler_(washer|nut)$"


def unit_of_label(label, R=None):
    for rx, name, dirs, stage, order in (R or RULES):
        m = re.fullmatch(rx, label)
        if m:
            gd = {k: v for k, v in m.groupdict().items() if v is not None}
            if "k2" in gd and "k" not in gd:
                gd["k"] = gd["k2"]
            gd.setdefault("name", (m.group(2) or "") if m.re.groups >= 2 else "")
            return name.format(**gd), dirs, stage, order, gd
    return None


def skin_host(label, labels):
    """section_skin_<x>[_n] -> the leaf it skins."""
    pre, tail = label.split(":", 1)
    base = tail.replace("section_skin_", "", 1)
    cands = [f"{pre}:{base}", f"{pre}:{re.sub(r'_\d+$', '', base)}"]
    if pre == "barrels":
        cands.insert(0, f"barrels:barrel_{base}")
    for c in cands:
        if c in labels:
            return c
    return None


class Planner:
    def __init__(self, geo, exact):
        from lib import explodegeo as xg
        self.g, self.ex, self.xg = geo, exact, xg
        self.labels = [lf["label"] for lf in geo.leaves]
        self.lset = set(self.labels)
        self.rules = rules(self.labels)
        self.units = {}        # name -> dict(leaves, dirs, stage, order, kind)
        self.leaf_unit = [None] * geo.n
        self._assign()

    # ---- pass 1: units
    def _assign(self):
        g, xg = self.g, self.xg
        pending_skins = []
        for i, lab in enumerate(self.labels):
            if "section_skin" in lab:
                pending_skins.append((i, skin_host(lab, self.lset)))
                continue
            hit = unit_of_label(lab, self.rules)
            if hit and not (xg.is_fastener(lab) and not re.search(r"clamp_ring|clamp_stack|clamp_outlet|carb_", lab)
                            and not re.match(FORCE_PART, lab)):
                name, dirs, stage, order, gd = hit
                u = self.units.setdefault(name, {"leaves": [], "dirs": dirs, "stage": stage, "order": order,
                                                 "kind": "part", "gd": gd})
                u["leaves"].append(i)
                self.leaf_unit[i] = name
            elif xg.is_fastener(lab) or re.fullmatch(r"piston\d:pin_plug_[ab]", lab):
                # (wrist-pin plugs retain the pin: they leave with it, sideways, before the piston)
                name = f"f:{lab}"
                self.units[name] = {"leaves": [i], "dirs": "axis", "stage": None, "order": None, "kind": "fastener", "gd": {}}
                self.leaf_unit[i] = name
            elif hit:
                name, dirs, stage, order, gd = hit
                u = self.units.setdefault(name, {"leaves": [], "dirs": dirs, "stage": stage, "order": order,
                                                 "kind": "part", "gd": gd})
                u["leaves"].append(i)
                self.leaf_unit[i] = name
        for i, host in pending_skins:
            if host is None:           # no same-named part: the nearest unit (box centres) skins it
                c = (g.box[i][:3] + g.box[i][3:]) / 2
                pre = self.labels[i].split(":")[0]
                best = min((j for j in range(g.n) if self.leaf_unit[j] is not None and "section_skin" not in self.labels[j]
                            and self.labels[j].split(":")[0] == pre and self.units[self.leaf_unit[j]]["kind"] == "part"),
                           key=lambda j: np.linalg.norm((g.box[j][:3] + g.box[j][3:]) / 2 - c))
                host = self.labels[best]
            hu = self.leaf_unit[self.labels.index(host)]
            if hu is None:
                hit = unit_of_label(host, self.rules)
                hu = hit[0] if hit else None
            if hu is None:
                raise SystemExit(f"[explodeplan] cannot place skin {self.labels[i]}")
            self.units[hu]["leaves"].append(i)
            self.leaf_unit[i] = hu
        missing = [self.labels[i] for i in range(g.n) if self.leaf_unit[i] is None]
        if missing:
            raise SystemExit(f"[explodeplan] {len(missing)} leaves match no unit rule, e.g. {missing[:12]}")
        self._anchor_studs()

    def key(self, n):
        u = self.units[n]
        if u["dirs"] == "fixed":
            return (99, 0, n)          # the datum never leaves: studs in it stay
        return (u["stage"] if u["stage"] is not None else 50, u["order"] or 0, n)

    def _anchor_studs(self):
        """A stud stays in the part it is screwed into: the touching part unit leaving LAST."""
        z = np.zeros(3)
        g = self.g
        for n in [m for m, u in self.units.items() if u["kind"] == "fastener"]:
            i = self.units[n]["leaves"][0]
            if "stud" not in self.labels[i].split(":", 1)[1]:
                continue
            b = g.box[i]
            cand = np.nonzero(np.all(g.box[:, :3] <= b[3:] + 1, axis=1) & np.all(g.box[:, 3:] >= b[:3] - 1, axis=1))[0]
            parts = set()
            for j in cand:
                j = int(j)
                if j == i or self.units[self.leaf_unit[j]]["kind"] != "part":
                    continue
                d = g.depth(i, z, j, z)
                if d is not None and d > TOUCH:
                    parts.add(self.leaf_unit[j])
            if parts:
                anchor = max(parts, key=self.key)
                del self.units[n]
                self.units[anchor]["leaves"].append(i)
                self.leaf_unit[i] = anchor

    def index_of(self, label):
        return self.labels.index(label)

    def unit_box(self, name):
        b = self.g.box[self.units[name]["leaves"]]
        return np.concatenate([b[:, :3].min(0), b[:, 3:].max(0)])

    def unit_points(self, name):
        return np.concatenate([self.g.verts(i) for i in self.units[name]["leaves"]])

    def directions(self, name):
        """Candidate exit directions of a unit, in preference order."""
        from lib import kin
        u = self.units[name]
        specs = u["dirs"] if isinstance(u["dirs"], list) else [u["dirs"]]
        gd = u["gd"]
        out = []
        box = self.unit_box(name)
        c = (box[:3] + box[3:]) / 2
        for s in specs:
            if s == "F":
                out.append(np.array(F))
            elif s == "R":
                out.append(np.array(R))
            elif s == "down":
                out.append(np.array([0, 0, -1.0]))
            elif s in ("cyl", "cyl1"):
                k = int(gd.get("k", 1))
                out.append(np.array(u_cyl(k)))
            elif s == "blade":        # blade axes at in-plane 20, 140, 260 deg (BUILDING.md)
                b = math.radians(20.0 + 120.0 * (int(gd["j"]) - 1))
                out.append(np.array([-math.sin(b), 0.0, math.cos(b)]))
            elif s == "plug":          # along the spark plug's axis, away from its head
                plug = self.index_of(f"heads:plug_{gd['k']}{gd['p']}")
                head = self.index_of(f"heads:head_{gd['k']}")
                P = self.g.verts(plug)
                ax = _pca_axis(P)[0][:, 2]
                hb = self.g.box[head]
                if np.dot(ax, P.mean(0) - (hb[:3] + hb[3:]) / 2) < 0:
                    ax = -ax
                out.append(ax / np.linalg.norm(ax))
            elif s == "rad":
                r = math.hypot(c[0], c[2])
                out.append(np.array([c[0] / r, 0, c[2] / r]))
            elif s == "tappet":
                out.append(np.array(kin.tappet_dir(int(gd["k"]), gd["v"])))
            elif s == "pushrod":
                k, v = int(gd["k"]), gd["v"]
                d = np.array(kin.pushrod_top0(k, v)) - np.array(kin.pushrod_bottom0(k, v))
                out.append(d / np.linalg.norm(d))
            elif s == "artrod":
                k = int(gd["k"])
                a, b = kin.knuckle(0.0, k), kin.wrist_pin(0.0, k)
                d = np.array([b[0] - a[0], 0, b[1] - a[1]])
                out.append(d / np.linalg.norm(d))
            elif s == "axis":
                P = self.unit_points(name)
                ax = fastener_axis(P, self.labels[u["leaves"][0]]) if u["kind"] == "fastener" else _pca_axis(P)[0][:, 2]
                out += [ax, -ax]
            elif s == "fixed":
                pass
            else:
                raise ValueError(s)
        return out


# ---------------------------------------------------------------------------
# 3. blocking: which units does a unit's straight exit path hit?
# ---------------------------------------------------------------------------
BLOCK_STEP = 10.0     # planning resolution; lib.explodecheck verifies at 0.5 mm
SCREEN = 0.25
PLAN_SCREEN = 0.5     # planning only: a mesh-refined penetration this deep is a real clash; the final
                      # lib.explodecheck confirms every reading above 0.25 mm with the exact boolean


def _clear_distance(box, d, others_box):
    """Travel after which `box` moved along d no longer overlaps others_box (inflated)."""
    lo, hi = others_box[:3] - 2, others_box[3:] + 2
    best = 0.0
    for ax in range(3):
        if abs(d[ax]) < 1e-9:
            continue
        s = ((hi[ax] - box[ax]) / d[ax]) if d[ax] > 0 else ((lo[ax] - box[3 + ax]) / d[ax])
        best = max(best, s)
    return best


_P = {}


def _worker_init(step_file):
    sys.path.insert(0, str(SRC))
    import threading
    from lib import gate
    threading.Thread(target=gate._watch_parent, args=(os.getppid(),), daemon=True).start()
    from lib import explodegeo as xg
    _P["g"] = xg.Geo(step_file, refine=True)
    _P["ex"] = xg.Exact(step_file)
    _P["xg"] = xg


def blockers_of(task):
    """task = (unit leaves, direction, max distance, {other leaf -> unit}); returns {unit: first hit distance}."""
    t_start = time.time()
    leaves, d, dmax, owner = task[:4]
    step = task[5] if len(task) > 5 else BLOCK_STEP
    g, ex, xg = _P["g"], _P["ex"], _P["xg"]
    fp = {}                     # pair -> deepest reading the exact boolean found harmless (sliding-fit noise)
    n_exact = 0
    d = np.asarray(d, float)
    mine = set(leaves)
    hits = {}
    z = np.zeros(3)
    exact_cache = {}
    for i in leaves:
        bi0 = g.box[i]
        sw = np.concatenate([np.minimum(bi0[:3], bi0[:3] + d * dmax), np.maximum(bi0[3:], bi0[3:] + d * dmax)])
        cand = np.nonzero(np.all(g.box[:, :3] <= sw[3:] + 1, axis=1) & np.all(g.box[:, 3:] >= sw[:3] - 1, axis=1))[0]
        for j in cand:
            j = int(j)
            if j in mine or str(j) not in owner:
                continue
            uj = owner[str(j)]
            # the part of the path along which the two boxes can meet
            bj = g.box[j]
            s0, s1 = 0.0, dmax
            for ax in range(3):
                if abs(d[ax]) < 1e-9:
                    if bi0[3 + ax] < bj[ax] - 3.2 or bj[3 + ax] < bi0[ax] - 3.2:
                        s0, s1 = 1, 0
                    continue
                a = (bj[ax] - 3.2 - bi0[3 + ax]) / d[ax]
                b = (bj[3 + ax] + 3.2 - bi0[ax]) / d[ax]
                lo_, hi_ = min(a, b), max(a, b)
                s0, s1 = max(s0, lo_), min(s1, hi_)
            if s1 < s0 or (uj in hits and hits[uj] <= s0):
                continue
            s = max(step, s0)
            while s <= s1 + 1e-9:
                if uj in hits and hits[uj] <= s:
                    break
                gp = g.gap(i, d * s, j, z, reach=60.0)
                if gp > step:
                    s += gp            # distance is 1-Lipschitz in the travel: nothing can happen sooner
                    continue
                dep = g.depth(i, d * s, j, z)
                if dep is not None and dep > PLAN_SCREEN:
                    hits[uj] = s
                    break
                s += step
    return {"hits": hits, "seconds": round(time.time() - t_start, 1), "exact": n_exact}


def _blockers_task(task):
    return task[4], blockers_of(task)


def compute_blocking(pl, workers=2, cache_path=None, names=None, kinds=("part", "fastener")):
    """{(unit, dir index): {blocker unit: distance}} for every movable unit."""
    cache = {}
    if cache_path and Path(cache_path).exists():
        cache = json.loads(Path(cache_path).read_text())
    owner = {str(i): pl.leaf_unit[i] for i in range(pl.g.n)}
    allbox = np.concatenate([pl.g.box[:, :3].min(0), pl.g.box[:, 3:].max(0)])
    tasks, keys = [], []
    for name, u in pl.units.items():
        if names and name not in names:
            continue
        if u["dirs"] == "fixed" or u["kind"] not in kinds:
            continue
        for di, d in enumerate(pl.directions(name)):
            sig = f"{name}|{','.join(f'{x:.4f}' for x in d)}|{len(u['leaves'])}"
            if sig in cache:
                continue
            box = pl.unit_box(name)
            dmax = min(300.0, max(60.0, fastener_clearance(pl, name, d) + 10)) if u["kind"] == "fastener" else min(1600.0, _clear_distance(box, d, allbox) + 5)
            tasks.append((u["leaves"], d.tolist(), dmax, owner, sig, 4.0 if u["kind"] == "fastener" else BLOCK_STEP))
            keys.append(sig)
    if tasks:
        t0 = time.time()
        print(f"[explodeplan] blocking: {len(tasks)} unit exits to sweep on {workers} workers", flush=True)
        ctx = mp.get_context("spawn")
        with ctx.Pool(workers, initializer=_worker_init, initargs=(str(STEP_FILE),)) as pool:
            for n, (sig, res) in enumerate(pool.imap_unordered(_blockers_task, tasks)):
                cache[sig] = res["hits"]
                if res["seconds"] > 20:
                    print(f"[explodeplan]   slow: {sig.split('|')[0]} {res['seconds']}s, {res['exact']} booleans", flush=True)
                if cache_path and n % 25 == 24:
                    Path(cache_path).write_text(json.dumps(cache))
                    print(f"[explodeplan]   {n + 1}/{len(tasks)} ({time.time() - t0:.0f}s)", flush=True)
        if cache_path:
            Path(cache_path).write_text(json.dumps(cache))
    return cache


def blocking_for(pl, cache, name):
    u = pl.units[name]
    out = []
    for d in pl.directions(name):
        sig = f"{name}|{','.join(f'{x:.4f}' for x in d)}|{len(u['leaves'])}"
        out.append((d, cache.get(sig, {})))
    return out



# ---------------------------------------------------------------------------
# Fasteners: contact graph, hosts, anchors
# ---------------------------------------------------------------------------
TOUCH = -0.6     # depth reading above this = surfaces within ~0.6 mm


def contacts(pl, leaf_ids):
    """{leaf: [touching leaves]} for the given leaves (sample-depth test at rest)."""
    g = pl.g
    z = np.zeros(3)
    out = {}
    for i in leaf_ids:
        b = g.box[i]
        cand = np.nonzero(np.all(g.box[:, :3] <= b[3:] + 1, axis=1) & np.all(g.box[:, 3:] >= b[:3] - 1, axis=1))[0]
        out[i] = [int(j) for j in cand if j != i and (lambda d: d is not None and d > TOUCH)(g.depth(i, z, int(j), z))]
    return out


def resolve_fasteners(pl, key):
    """Anchor studs into the part they are screwed into (the touching part leaving
    LAST) and give every other fastener its host: the touching part unit leaving
    FIRST (through chains of touching fasteners). Returns {fastener unit: host unit}."""
    fl = [pl.units[n]["leaves"][0] for n in pl.units if pl.units[n]["kind"] == "fastener"]
    touch = contacts(pl, fl)
    host = {}
    parts_of = lambda i: {pl.leaf_unit[j] for j in touch[i] if pl.units[pl.leaf_unit[j]]["kind"] == "part"}
    fl = [i for i in fl if pl.units[pl.leaf_unit[i]]["kind"] == "fastener"]
    for _ in range(6):
        changed = False
        for i in fl:
            n = pl.leaf_unit[i]
            cands = parts_of(i) | {host[pl.leaf_unit[j]] for j in touch[i]
                                   if pl.leaf_unit[j] in host and pl.units[pl.leaf_unit[j]]["kind"] == "fastener"}
            cands.discard(None)
            if cands:
                h = min(cands, key=key)
                if host.get(n) != h:
                    host[n] = h
                    changed = True
        if not changed:
            break
    for i in fl:                   # pins belong to what they pin
        lab = pl.labels[i]
        m = re.fullmatch(r"piston(\d):(wrist_pin|pin_plug_[ab])", lab)
        if m and f"piston_{m.group(1)}" in pl.units:
            host[pl.leaf_unit[i]] = f"piston_{m.group(1)}"
        if re.fullmatch(r"crankcase:through_(bolt|nut)_\d+", lab) and "case_front" in pl.units:
            host[pl.leaf_unit[i]] = "case_front"      # they clamp the case halves, not the ignition ring
        m = re.fullmatch(r"master:(knuckle_pin|knuckle_retainer|retainer_wire)_(\d)|master:retainer_bolt_(\d)_\d", lab)
        if m:
            k = m.group(2) or m.group(3)
            if f"artrod_{k}" in pl.units:
                host[pl.leaf_unit[i]] = f"artrod_{k}"
    for i in fl:
        n = pl.leaf_unit[i]
        if n not in host:          # touches nothing: nearest part unit by box centre
            c = (pl.g.box[i][:3] + pl.g.box[i][3:]) / 2
            best = min((m for m in pl.units if pl.units[m]["kind"] == "part"),
                       key=lambda m: np.linalg.norm((lambda b: (b[:3] + b[3:]) / 2)(pl.unit_box(m)) - c))
            host[n] = best
    return host, touch


# ---------------------------------------------------------------------------
# 4. Sequence
# ---------------------------------------------------------------------------
def fastener_clearance(pl, f, d):
    """Travel a fastener needs along d to clear what it retains: its own length along d + 5 mm
    (a wrist pin must leave the rod's small end entirely)."""
    P = pl.unit_points(f)
    x = P @ np.asarray(d, float)
    return float(x.max() - x.min()) + 5.0


def DATUM_TRAVEL(n):
    from lib import explodelayout
    return explodelayout.min_travel(None, n, None)


def sequence(pl, block, host=None):
    """Priority order with pulled-forward prerequisites. Returns (seq, notes):
    seq = [(unit, direction, requested_by)], in removal order. With `host` (fastener -> unit),
    a unit also waits for every part that blocks ALL exits of one of its fasteners (a wrist pin
    that cannot come out sideways until the crankcase half beside it has gone)."""
    parts = [n for n, u in pl.units.items() if u["kind"] == "part" and u["dirs"] != "fixed"]
    fneed = {}
    # only pins that join the unit to a neighbour it slides off (wrist pins + their plugs,
    # knuckle pins) must fully clear first; other hardware leaves as far as it is free and rides along
    PIN = re.compile(r"f:.*(wrist_pin|pin_plug_[ab]|knuckle_pin_\d)$")
    for f, h in (host or {}).items():
        if not PIN.fullmatch(f):
            continue
        best = None
        for d, hits in blocking_for(pl, block, f):
            need = fastener_clearance(pl, f, d)
            bl = {b for b, s_ in hits.items() if b in pl.units and pl.units[b]["kind"] == "part" and b != h and s_ < need}
            rank = (any(pl.units[b]["dirs"] == "fixed" for b in bl), len(bl))    # never through the datum
            if best is None or rank < best_rank:
                best, best_rank = bl, rank
        if best:
            fneed.setdefault(h, set()).update(best)
    key = lambda n: (pl.units[n]["stage"], pl.units[n]["order"], n)
    removed, visiting, seq, notes = set(), set(), [], []

    grp = lambda n: n

    def options(n):
        out = []
        tmin = DATUM_TRAVEL(n)
        for d, hits in blocking_for(pl, block, n):
            # the datum only blocks an exit it meets before the unit's minimum travel; one met
            # further out is reported (the layout may still push the unit past it; explodecheck verifies)
            bl = {b for b, s_ in hits.items() if b in pl.units and pl.units[b]["kind"] == "part" and b not in removed
                  and grp(b) != grp(n) and not (pl.units[b]["dirs"] == "fixed" and s_ >= tmin + 20)} \
                | {b for b in fneed.get(n, ()) if b not in removed and b != n}
            if any(pl.units[b]["dirs"] == "fixed" for b in bl):
                continue
            out.append((len(bl), d, bl))
        return out

    forced = set()

    def schedule(n, by):
        if n in removed:
            return True
        if n in visiting:
            return False
        visiting.add(n)
        opts = options(n)
        if not opts:
            notes.append(f"{n}: every exit direction is blocked by the fixed datum")
            visiting.discard(n)
            return False
        for _, d, bl in sorted(opts, key=lambda o: o[0]):
            ok = True
            for b in sorted(bl, key=key):
                if not schedule(b, by or n):
                    ok = False
                    break
            if ok:
                removed.add(n)
                seq.append((n, d, by))
                visiting.discard(n)
                return True
        visiting.discard(n)
        return False

    for n in sorted(parts, key=key):
        if not schedule(n, None) and n not in removed:
            # circular blocking: schedule it anyway along its least-blocked exit and REPORT it -
            # lib.explodecheck will show the interpenetration until the geometry is fixed
            opts = options(n)
            if opts:
                _, d, bl = min(opts, key=lambda o: o[0])
                notes.append(f"FORCED {n}: circular blocking, leaves along {np.round(d, 2).tolist()} "
                             f"through {sorted(bl)}")
                removed.add(n)
                seq.append((n, d, None))
            else:
                notes.append(f"STUCK {n}: every exit direction is blocked by the fixed datum")
    return seq, notes


# ---------------------------------------------------------------------------
# 5. Layout: how far each unit travels (reverse placement), and 6. timeline
# ---------------------------------------------------------------------------
GAP = 30.0                 # clearance between exploded neighbours (mm)
MIN_TRAVEL = 60.0


def hull_points(P):
    from scipy.spatial import ConvexHull
    if len(P) < 5:
        return P
    try:
        return P[ConvexHull(P).vertices]
    except Exception:
        return P


def _frame(d):
    """Rotation whose third row is d (world -> frame with d as local z)."""
    d = np.asarray(d, float) / np.linalg.norm(d)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    x = np.cross(a, d)
    x /= np.linalg.norm(x)
    y = np.cross(d, x)
    return np.array([x, y, d])


def _box(P, Rf):
    Q = P @ Rf.T
    return np.concatenate([Q.min(0), Q.max(0)])


def _overlap(a, b, gap):
    return np.all(a[:3] < b[3:] + gap) and np.all(b[:3] < a[3:] + gap)


WHY = {}


class _Hull:
    """Convex hull as (vertices, face planes n.x + d <= 0 inside, world AABB)."""
    __slots__ = ("V", "E", "box")

    def __init__(self, P):
        from scipy.spatial import ConvexHull
        P = np.asarray(P, float)
        try:
            h = ConvexHull(P)
            self.V = P[h.vertices]
            E = h.equations
            # merge near-duplicate planes (triangulated faces): keeps SAT cheap
            key = np.round(E[:, :3], 3)
            _, idx = np.unique(key, axis=0, return_index=True)
            self.E = E[idx]
        except Exception:
            self.V, self.E = P, np.zeros((0, 4))
        self.box = np.concatenate([self.V.min(0), self.V.max(0)])

    def moved(self, t):
        h = _Hull.__new__(_Hull)
        h.V = self.V + t
        h.E = self.E.copy()
        h.E[:, 3] -= self.E[:, :3] @ t
        h.box = self.box + np.concatenate([t, t])
        return h


def _swept(h, a, b):
    """Convex hull of h translated along the segment a -> b."""
    return _Hull(np.concatenate([h.V + a, h.V + b]))


def _apart(A, B, gap):
    """True when convex hulls A and B are separated by more than `gap` along an AABB axis or one
    of their face normals (SAT on face normals: conservative - may call touching edge pairs 'not apart')."""
    if np.any(A.box[:3] - gap > B.box[3:]) or np.any(B.box[:3] - gap > A.box[3:]):
        return True
    for X, Y in ((A, B), (B, A)):
        if len(X.E):
            # plane i separates if every vertex of Y is at least gap outside it
            s = Y.V @ X.E[:, :3].T + X.E[:, 3]          # (nY, nF)
            if np.any(s.min(axis=0) > gap):
                return True
    return False


def place(pl, seq, travel_min, extra=None, skip=None, step=20.0):
    """Travel (mm) for every unit in seq (reverse removal order): a unit's final position must
    be clear (convex hulls + GAP) of the final position and the whole path of every unit removed
    after it. Paths are straight segments (the exit, then any extra segments)."""
    hull = {n: _Hull(pl.unit_points(n)) for n, _, _ in seq}
    placed = []                       # (name, [hulls of each path segment], final hull)
    travel = {}
    for n, d, _ in reversed(seq):
        d = np.asarray(d, float)
        H = hull[n]
        T = travel_min.get(n, MIN_TRAVEL)
        post = (extra or {}).get(n, [])
        for _ in range(600):
            fin = H.moved(d * T + sum(post, np.zeros(3)))
            bad = None
            for m, paths, mfin in placed:
                if skip and skip(n, m):
                    continue
                if any(not _apart(fin, ph, GAP) for ph in paths):
                    bad = m
                    break
            if bad is None:
                break
            WHY[n] = bad
            T += step
        travel[n] = T
        segs = [d * T] + list(post)
        paths, acc = [], np.zeros(3)
        for sg in segs:
            paths.append(_swept(H, acc, acc + sg))
            acc = acc + sg
        placed.append((n, paths, H.moved(acc)))
    return travel


# ---------------------------------------------------------------------------
# Evaluation (the JS re-implements exactly this)
# ---------------------------------------------------------------------------
def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def offset(moves, t):
    """moves: [(t0, t1, dx, dy, dz)] -> displacement at time t."""
    o = np.zeros(3)
    for t0, t1, dx, dy, dz in moves:
        if t <= t0:
            continue
        e = 1.0 if t >= t1 else ease((t - t0) / (t1 - t0))
        o += e * np.array([dx, dy, dz])
    return o


def offset_range(moves, ta, tb):
    """Conservative box [lo(3), hi(3)] of the displacement over [ta, tb]: each eased
    segment is monotonic, so its contribution lies between its values at ta and tb."""
    lo, hi = np.zeros(3), np.zeros(3)
    for t0, t1, dx, dy, dz in moves:
        ea = ease((ta - t0) / (t1 - t0)) if ta < t1 else 1.0
        eb = ease((tb - t0) / (t1 - t0)) if tb < t1 else 1.0
        if ta <= t0:
            ea = 0.0
        if tb <= t0:
            eb = 0.0
        v = np.array([dx, dy, dz])
        a, b = ea * v, eb * v
        lo += np.minimum(a, b)
        hi += np.maximum(a, b)
    return lo, hi





# ---------------------------------------------------------------------------
# Refresh: after a rebuild, re-test every cached hit whose unit or blocker contains a leaf
# whose geometry changed (restricted to that pair: far cheaper than a full sweep), and drop
# the hits that no longer hold. New blockers a rebuild may add are caught by lib.explodecheck.
# ---------------------------------------------------------------------------
def _refresh_task(task):
    sig, leaves, d, dmax, owner, step = task
    return sig, blockers_of((leaves, d, dmax, owner, sig, step))["hits"]


_REFRESH_TESTED = {}


def refresh(pl, cache, changed_leaves, workers=2):
    changed_units = {pl.leaf_unit[i] for i in changed_leaves}
    allbox = np.concatenate([pl.g.box[:, :3].min(0), pl.g.box[:, 3:].max(0)])
    tasks = []
    for name, u in pl.units.items():
        if u["dirs"] == "fixed":
            continue
        for d in pl.directions(name):
            sig = f"{name}|{','.join(f'{x:.4f}' for x in d)}|{len(u['leaves'])}"
            hits = cache.get(sig)
            if not hits:
                continue
            check = [b for b in hits if b in pl.units and (b in changed_units or name in changed_units)]
            if not check:
                continue
            owner = {str(i): pl.leaf_unit[i] for b in check for i in pl.units[b]["leaves"]}
            dmax = (min(300.0, max(60.0, fastener_clearance(pl, name, d) + 10)) if u["kind"] == "fastener"
                    else min(1600.0, _clear_distance(pl.unit_box(name), d, allbox) + 5))
            tasks.append((sig, u["leaves"], d.tolist(), dmax, owner, 4.0 if u["kind"] == "fastener" else BLOCK_STEP))
            _REFRESH_TESTED[sig] = set(check)
    print(f"[explodeplan] refresh: re-testing {len(tasks)} cached exits against changed parts", flush=True)
    if not tasks:
        return cache
    ctx = mp.get_context("spawn")
    with ctx.Pool(workers, initializer=_worker_init, initargs=(str(STEP_FILE),)) as pool:
        for sig, new in pool.imap_unordered(_refresh_task, tasks):
            old = cache[sig]
            tested = _REFRESH_TESTED[sig]
            cache[sig] = {b: (new[b] if b in new else v) for b, v in old.items() if b not in tested or b in new}
    return cache


def changed_leaves(g, old_npz):
    """Leaves whose tight rest box moved > 0.01 mm (or that are new) relative to an older sample cache."""
    import json as _j
    z = np.load(old_npz)
    old = {lf["label"]: lf for lf in _j.loads(str(z["leaves"]))}
    out = []
    for i, lf in enumerate(g.leaves):
        o = old.get(lf["label"])
        if o is None:
            out.append(i)
            continue
        V = z[f"V_{o['proto']}"].astype(np.float64)
        M = np.array(o["L"])
        W = V @ M[:3, :3].T + M[:3, 3]
        ob = np.concatenate([W.min(0), W.max(0)]) if len(W) else np.zeros(6)
        if np.max(np.abs(ob - g.box[i])) > 0.01 or len(W) != len(g.verts(i)):
            out.append(i)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--blocking", default="part,fastener", help="compute the blocking cache for these unit kinds")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--only-blocking", action="store_true")
    ap.add_argument("--refresh-from", default=None, help="older xgeo_*.npz: re-test cached hits touching changed parts")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(SRC))
    from lib import explodegeo as xg
    g = xg.Geo(STEP_FILE)
    g.ensure_triangles()
    pl = Planner(g, None)
    cache_path = ROOT / "tmp" / "kin" / "xblock.json"      # planning cache; survives small rebuilds
    if a.refresh_from:
        cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
        ch = changed_leaves(g, a.refresh_from)
        print(f"[explodeplan] {len(ch)} leaves changed since {Path(a.refresh_from).name}", flush=True)
        cache = refresh(pl, cache, ch, a.workers)
        cache_path.write_text(json.dumps(cache))
    block = compute_blocking(pl, a.workers, cache_path, kinds=tuple(a.blocking.split(",")))
    if a.only_blocking:
        return 0
    from lib import explodelayout
    plan = explodelayout.build(pl, block)
    OUT.write_text(json.dumps(plan))
    print(f"[explodeplan] wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
