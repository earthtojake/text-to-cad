"""Explode timeline + layout (see lib/explodeplan.py for the passes).

build(planner, blocking) -> plan dict:
  {"duration", "hold", "units": {name: {"leaves": [labels], "moves": [[t0, t1, dx, dy, dz], ...],
                                     "stage", "wave", "host"?}},
   "sequence": [...], "notes": [...]}
Moves are eased (smoothstep) straight translations; a leaf's displacement at t
is the sum of its unit's moves (explodeplan.offset).
"""

from __future__ import annotations

import math
import re

import numpy as np

from lib import explodeplan as ep

TOTAL = 22.5            # seconds of motion; the clip then holds the full explode
HOLD = 1.5
WINDOWS = {1: (0.0, 1.8), 2: (1.8, 5.0), 3: (5.0, 6.6), 4: (6.6, 9.0), 5: (9.0, 12.8),
           6: (12.8, 16.6), 7: (16.6, 18.2), 8: (18.2, 19.8), 9: (19.8, 22.5)}
BLOOM_LEAD, BLOOM_STEP, BLOOM_MOVE = 0.25, 0.28, 0.9     # cylinders bloom in firing order
PART_MOVE = 0.6         # natural seconds for a part unit's exit move
FAST_MOVE = 0.3         # natural seconds for a fastener's own exit
FASTENER_EXIT = 45.0    # desired own-exit travel of a fastener (mm), capped by what is free

# Layout: extra travel segments after the exit move, and minimum exit travels.
# the collector pieces fan out after the ring has moved rearward, in turns that let each
# piece leave radially past its slip joints (measured: the ends free first, clamp rings last)
FAN_WAVES = [("collector_l3", "collector_r3", "collector_outlet", "clamp_outlet", "collector_top"),
             ("collector_l2", "collector_r2", "collector_bottom"),
             ("collector_l1", "collector_r1"),
             ("clamp_ring_1", "clamp_ring_3", "clamp_ring_4", "clamp_ring_5", "clamp_ring_6", "clamp_ring_7",
              "clamp_ring_8")]
FAN = 240.0


def extra_segments(pl, name, d):
    if name.startswith("prop_blade_"):
        return [np.array([0.0, -760.0, 0.0])]        # off the hub along its own axis, then straight forward
    if name.startswith("exh_collector_") and d[1] > 0.9:
        b = pl.unit_box(name)
        c = (b[:3] + b[3:]) / 2
        r = math.hypot(c[0], c[2])
        return [np.array([c[0] / r, 0.0, c[2] / r]) * FAN]
    return []


def min_travel(pl, name, d):
    m = {"prop_blade": 190.0, "cover_": 700.0, "rocker_": 560.0, "tube_": 900.0, "pushrod_": 560.0,
         "cyl_": 470.0, "piston_": 240.0, "artrod_": 90.0, "tappet_": 180.0, "intake_": 380.0,
         "exh_stack_": 300.0, "exh_collector_": 260.0, "rshaft_": 160.0, "pinplug_": 90.0,
         "ignition": 250.0, "carburettor": 260.0}
    for pre, v in m.items():
        if name.startswith(pre):
            return v
    return ep.MIN_TRAVEL


def build(pl, block):
    notes = []
    host, touch = ep.resolve_fasteners(pl, pl.key)
    seq, snotes = ep.sequence(pl, block, host)
    notes += snotes
    order = {n: i for i, (n, _, _) in enumerate(seq)}
    dir_of = {n: np.asarray(d, float) for n, d, _ in seq}

    # --- effective stage (a prerequisite pulled forward runs in its requester's stage)
    stage = {}
    for n, d, by in seq:
        own = pl.units[n]["stage"]
        stage[n] = pl.units[by]["stage"] if by else own
        if by and pl.units[by]["stage"] < own:
            notes.append(f"{n} (stage {own}) pulled forward into stage {stage[n]}: it blocks {by}")

    # --- part blockers actually in the way when a unit leaves
    pulled_by = {}
    for m, _, by in seq:
        if by:
            pulled_by.setdefault(by, set()).add(m)
    PIN = re.compile(r"f:.*(wrist_pin|knuckle_pin_\d)$")
    for f, h in host.items():          # a unit also waits for whatever blocks every exit of its pin
        if not PIN.fullmatch(f):
            continue
        best = None
        for d, hits in ep.blocking_for(pl, block, f):
            need = ep.fastener_clearance(pl, f, d)
            bl = {b for b, s_ in hits.items() if b in pl.units and pl.units[b]["kind"] == "part" and b != h and s_ < need}
            rank = (any(pl.units[b]["dirs"] == "fixed" for b in bl), len(bl))
            if best is None or rank < best[0]:
                best = (rank, bl)
        if best:
            pulled_by.setdefault(h, set()).update(b for b in best[1] if pl.units[b]["dirs"] != "fixed")

    def part_blockers(n):
        # the parts in its path, and the prerequisites it pulled forward (the case half that
        # frees a wrist pin must be gone before that piston's pin comes out)
        out = set(pulled_by.get(n, ()))
        for d, hits in ep.blocking_for(pl, block, n):
            if np.allclose(d, dir_of[n]):
                return out | {b for b in hits if b in pl.units and pl.units[b]["kind"] == "part"}
        return out

    # --- waves within each stage
    wave = {}
    fan_top = {}
    for S in sorted(set(stage.values())):
        members = [n for n, _, _ in seq if stage[n] == S]
        orders = sorted({pl.units[n]["order"] for n in members})
        rank = {o: i for i, o in enumerate(orders)}
        for n in members:
            w = rank[pl.units[n]["order"]]
            for b in part_blockers(n):
                if b in wave and stage.get(b) == S:
                    w = max(w, wave[b] + 1)
            wave[n] = w
        coll = [n for n in members if n.startswith("exh_collector_") and dir_of[n][1] > 0.9]
        if coll:     # collector ring rearward as one piece, then its pieces fan out in turns
            if True:
                w0 = max(wave[n] for n in coll)
                fan_top[S] = w0 + len(FAN_WAVES)
                for n in coll:
                    wave[n] = w0
                for n in members:
                    if not n.startswith("exh_collector_") and pl.units[n]["order"] > 0.3:
                        wave[n] = max(wave[n], w0 + 1 + len(FAN_WAVES))
        if S == 2:   # planets separate one by one along the shaft axis
            base = max((wave[n] for n in members if n.startswith("planet_")), default=0)
            for n in members:
                if n.startswith("planet_"):
                    wave[n] = base + int(n.split("_")[1]) - 1
            for n in members:
                if not n.startswith("planet_") and pl.units[n]["order"] > 0.6:
                    wave[n] = max(wave[n], base + 6)

    # --- fastener deadlines: before the host leaves, and before any unit whose path it blocks
    fast = [n for n, u in pl.units.items() if u["kind"] == "fastener"]
    fblock = {}                          # fastener -> units it blocks
    for n, _, _ in seq:
        for d, hits in ep.blocking_for(pl, block, n):
            if np.allclose(d, dir_of[n]):
                for b in hits:
                    if b in pl.units and pl.units[b]["kind"] == "fastener":
                        fblock.setdefault(b, set()).add(n)

    # --- times: each stage owns a window; its waves share it (fastener exit in the first 30 %
    #     of a wave's slot, the part move in the rest); the bloom staggers in firing order
    slots, slotlen = {}, {}
    for S in sorted(set(stage.values())):
        a0, b0 = WINDOWS[S]
        W = max([wave[n] for n in stage if stage[n] == S] + [fan_top.get(S, 0)]) + 1
        if S == 6:
            W = max(W, 2)
            web0 = a0 + BLOOM_LEAD + 8 * BLOOM_STEP + BLOOM_MOVE + 0.1
            L = (b0 - web0) / (W - 1)
            for w in range(1, W):
                slots[(S, w)] = (web0 + (w - 1) * L + 0.3 * L, web0 + w * L)
            slotlen[S] = L
            slots[(S, 0)] = (a0 + BLOOM_LEAD, a0 + BLOOM_LEAD + BLOOM_MOVE)
            continue
        L = (b0 - a0) / W
        slotlen[S] = L
        for w in range(W):
            slots[(S, w)] = (a0 + w * L + 0.3 * L, a0 + (w + 1) * L)
    scale = 1.0
    start, end = {}, {}
    for n, _, _ in seq:
        a, b = slots[(stage[n], wave[n])]
        if stage[n] == 6 and n.startswith("cyl_"):
            f = ep.FIRING.index(int(n.split("_")[1]))
            a0 = WINDOWS[6][0] + BLOOM_LEAD + f * BLOOM_STEP
            a, b = a0, a0 + BLOOM_MOVE
        elif stage[n] == 6 and wave[n] == 0:
            a, b = slots[(6, 1)]
        start[n], end[n] = a, b

    # --- layout: travel of every part unit (groups that move as one share a travel)
    extra = {n: extra_segments(pl, n, dir_of[n]) for n, _, _ in seq}
    tmin = {n: min_travel(pl, n, dir_of[n]) for n, _, _ in seq}
    group = [n for n, _, _ in seq if n.startswith("exh_collector_") and dir_of[n][1] > 0.9]
    for _ in range(4):
        travel = ep.place(pl, seq, tmin, extra)
        if not group:
            break
        tg = max(travel[n] for n in group)
        if all(abs(travel[n] - tg) < 1e-6 for n in group):
            break
        for n in group:
            tmin[n] = tg

    # the datum (mount + blower case) is not placed: a unit whose exit meets it further out than
    # its minimum travel stops short of it
    for n, _, _ in seq:
        for d, hits in ep.blocking_for(pl, block, n):
            if np.allclose(d, dir_of[n]):
                s_ = hits.get("datum")
                if s_ is not None and travel[n] > s_ - 5 and not extra[n]:
                    notes.append(f"{n}: travel {travel[n]:.0f} capped at {s_ - 5:.0f} mm by the datum")
                    travel[n] = s_ - 5

    units = {}
    for n, _, _ in seq:
        d = dir_of[n]
        segs = [d * travel[n]] + list(extra[n])
        lens = [np.linalg.norm(s) for s in segs]
        tot = sum(lens)
        a = start[n]
        moves = []
        if n.startswith("exh_collector_") and len(segs) == 2 and d[1] > 0.9:
            # ring move in its slot, the fan in its turn afterwards
            moves.append([round(start[n], 4), round(end[n], 4)] + [round(float(x), 3) for x in segs[0]])
            k = next(i for i, grp in enumerate(FAN_WAVES) if any(n.endswith(x) for x in grp))
            fa, fb = slots[(stage[n], wave[n] + 1 + k)]
            moves.append([round(fa * scale, 4), round(fb * scale, 4)] + [round(float(x), 3) for x in segs[1]])
            segs = []
        for s, L in zip(segs, lens):
            b = a + (end[n] - start[n]) * L / tot
            moves.append([round(a, 4), round(b, 4)] + [round(float(x), 3) for x in s])
            a = b
        units[n] = {"leaves": [pl.labels[i] for i in pl.units[n]["leaves"]], "moves": moves,
                    "stage": stage[n], "wave": wave[n], "dir": d.round(4).tolist(), "travel": travel[n]}
    units["datum"] = {"leaves": [pl.labels[i] for i in pl.units["datum"]["leaves"]], "moves": [], "stage": 0}

    # --- fasteners: own exit (free distance along its axis), then ride with the host.
    # Fasteners of one host that touch and leave along the same line (nut on washer on
    # a stud) form a stack that moves as one, by the smallest free distance in it.
    choice = {}
    for n in fast:
        h = host[n] if host[n] in units else "datum"
        hstart = start.get(h, TOTAL * 2)
        deadline = min([hstart] + [start[b] for b in fblock.get(n, ()) if b in start])
        hd = dir_of.get(h, np.zeros(3))
        best = None
        for d, hits in ep.blocking_for(pl, block, n):
            gone = lambda b: (b in end and end[b] <= deadline) or (host.get(b) in end and end[host.get(b)] <= deadline)
            present = [s_ for b, s_ in hits.items() if b in pl.units and not gone(b)
                       and not (pl.units[b]["kind"] == "fastener" and host.get(b) == host[n])]
            need = max(FASTENER_EXIT, ep.fastener_clearance(pl, n, d))
            free = min(present + [1e6])
            score = (min(free, need), float(np.dot(d, hd)))
            if best is None or score > best[0]:
                best = (score, np.asarray(d, float), free)
        choice[n] = (h, deadline, best)
    # stacks: union touching same-host fasteners whose exit lines agree
    parent = {n: n for n in fast}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for n in fast:
        i = pl.units[n]["leaves"][0]
        for j in touch.get(i, []):
            m = pl.leaf_unit[j]
            if m in choice and m != n and choice[m][0] == choice[n][0] and choice[n][2] and choice[m][2] \
                    and abs(float(np.dot(choice[n][2][1], choice[m][2][1]))) > 0.95:
                parent[find(n)] = find(m)
    stacks = {}
    for n in fast:
        stacks.setdefault(find(n), []).append(n)
    for members in stacks.values():
        # the longest member (a wrist pin, not its plug) sets the stack's line
        lead = max(members, key=lambda x: ep.fastener_clearance(pl, x, choice[x][2][1]) if choice[x][2] else 0.0)
        h, _, best = choice[lead]
        deadline = min(choice[m][1] for m in members)
        d = best[1] if best else None
        free = min((choice[m][2][2] for m in members if choice[m][2]), default=0.0)
        for m in members:
            moves = []
            if d is not None and free >= 3.0 and (h != "datum" or m in fblock):
                dm = d if np.dot(choice[m][2][1], d) > 0 else d   # one line, one sense for the stack
                # the whole stack must clear: the longest member sets the travel (a wrist pin, not its plug)
                dist = min(free - 1.0, max([FASTENER_EXIT] + [ep.fastener_clearance(pl, x, d) for x in members]))
                t1 = deadline - 0.02
                fl = min(0.3, 0.28 * slotlen.get(units[h]["stage"] if h in units else 9, 0.5))
                t0 = max(0.0, t1 - fl)
                moves.append([round(t0, 4), round(t1, 4)] + [round(float(x), 3) for x in dm * dist])
            elif h != "datum":
                notes.append(f"{m}: no free exit along its axis; rides with {h}")
            units[m] = {"leaves": [pl.labels[i] for i in pl.units[m]["leaves"]],
                        "moves": moves + (units[h]["moves"] if h in units else []),
                        "stage": units[h]["stage"] if h in units else 0, "host": h}
    return {"duration": round(TOTAL + HOLD, 3), "motion": TOTAL, "units": units,
            "sequence": [[n, stage[n], wave[n], by] for n, _, by in seq], "notes": notes}
