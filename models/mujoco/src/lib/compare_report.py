"""compare.py's Markdown report and its one-line summaries, from the dicts compare_core makes."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path


def f(x, nd: int = 2, signed: bool = False) -> str:
    if x is None:
        return "–"
    if isinstance(x, bool):
        return "yes" if x else "no"
    if isinstance(x, (int, float)):
        if math.isnan(x):
            return "–"
        s = f"{x:+.{nd}f}" if signed else f"{x:.{nd}f}"
        if float(s) == 0:  # no "-0.00"
            s = ("+" if signed else "") + s.lstrip("+-")
        return s
    return str(x)


def g3(x) -> str:
    return "–" if x is None else f"{x:.3g}"


def _rel(path: str, root: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(root))
    except ValueError:
        return path


def table(head: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    out += ["| " + " | ".join(r) + " |" for r in rows]
    return "\n".join(out)


# ---------------------------------------------------------------------------------------------
def verdict_table(results: list[tuple[str, dict]]) -> str:
    head = [""] + [label for label, _ in results]
    V = [r["verdict"] for _, r in results]

    def row(name, fn):
        return [name] + [fn(v, r) for v, (_, r) in zip(V, results)]

    rows = [
        row("Topology", lambda v, r: v["topology"]),
        row("Base registration RMS (mm)", lambda v, r: f(v["base_rms_mm"])
            + (" (ambiguous)" if r["base"].get("ambiguous") else "")),
        row("Worst axis angle (deg) / axis line offset (mm)",
            lambda v, r: f"{f(v['max_axis_angle_deg'])} / {f(v['max_axis_offset_mm'])}"),
        row("Worst link shape residual RMS, ours→theirs / theirs→ours (mm)",
            lambda v, r: f"{f(v['max_link_resid_mm'])} / {f(v['max_link_resid_back_mm'])}"),
        row("Total mass diff (%) / worst link (%)",
            lambda v, r: f"{f(v['total_mass_diff_pct'], 1, True)} / {f(v['max_link_mass_diff_pct'], 1)}"),
        row("Worst link COM distance (mm)", lambda v, r: f(v["max_com_dist_mm"], 1)),
        row("Gravity torque error, RMS / worst joint max (%)",
            lambda v, r: f"{f(v['gravity_rel_rms_pct'], 1)} / {f(v['gravity_rel_max_pct'], 1)}"),
        row("Largest zero offset (their value at our zero)",
            lambda v, r: "–" if not v["max_abs_offset"] else
            f"{v['max_abs_offset']['joint']} {f(v['max_abs_offset']['value'], 1, True)} {v['max_abs_offset']['unit']}"),
    ]
    return table(head, rows)


def discrepancies(r: dict) -> str:
    items = r["verdict"]["discrepancies"]
    if not items:
        return "No discrepancy above its threshold."
    return "\n".join(f"{i}. {x['text']}" for i, x in enumerate(items, 1))


# ---------------------------------------------------------------------------------------------
def _consumer_rows(co: dict, ct: dict) -> list[list[str]]:
    def coll(c):
        if not c["collision_geoms"]:
            return "none"
        return f"{c['collision_geoms']} (" + ", ".join(f"{k} {v}" for k, v in c["collision_by_type"].items()) + ")"

    def contact(c):
        if not c["contact_params"]:
            return "–"
        parts = []
        for p in c["contact_params"][:3]:
            fr = "/".join(g3(x) for x in p["friction"])
            parts.append(f"condim {p['condim']}, friction {fr}, solref {'/'.join(g3(x) for x in p['solref'])}"
                         + (f", priority {p['priority']}" if p["priority"] else "") + f" (×{p['count']})")
        more = len(c["contact_params"]) - 3
        return "; ".join(parts) + (f"; +{more} more" if more > 0 else "")

    def acts(c):
        if not c["actuators"]:
            return "none"
        groups = Counter()
        for a in c["actuators"]:
            gains = ", ".join(f"{k} {g3(a[k])}" for k in ("kp", "kv", "gear") if a.get(k))
            fr = a["forcerange"]
            key = a["type"] + (f" ({gains}" if gains else " (") + (f", force ±{g3(max(abs(x) for x in fr))}" if fr else "") + ")"
            groups[key.replace(" ()", "")] += 1
        n_ctrl = sum(1 for a in c["actuators"] if a["ctrlrange"])
        return "; ".join(f"{n} {k}" for k, n in groups.items()) + f"; ctrlrange on {n_ctrl}"

    def dyn(c):
        groups = Counter()
        for v in c["joint_dynamics"].values():
            groups[(g3(v["armature"]), g3(v["damping"]), g3(v["frictionloss"]), g3(v["stiffness"]))] += 1
        if not groups:
            return "–"
        return "; ".join(f"{a}/{d}/{fl}" + (f", stiffness {s}" if s != "0" else "") + f" (×{n})"
                         for (a, d, fl, s), n in groups.most_common())

    def eqs(c):
        if not c["equalities"]:
            return "none"
        return "; ".join(f"{e['type']} {'–'.join(map(str, e['objects']))}" for e in c["equalities"])

    def opt(c):
        o = c["option"]
        return f"{o['integrator']}, {o['cone']} cone, impratio {g3(o['impratio'])}, timestep {g3(o['timestep'] * 1e3)} ms"

    def excl(c):
        return "; ".join("–".join(p) for p in c["excludes"]) if c["excludes"] else "none"

    def other(c):
        return f"{c['cameras']} cameras, {c['sensors']} sensors, {c['tendons']} tendons, {c['contact_pairs']} contact pairs"

    rows = [
        ("Collision geoms (by type)", coll), ("Contact params on collision geoms", contact),
        ("Actuators", acts), ("Joint armature/damping/frictionloss", dyn), ("Equality constraints", eqs),
        ("Option", opt), ("Keyframes", lambda c: str(len(c["keyframes"])) if c["keyframes"] else "none"),
        ("Contact excludes", excl), ("Cameras, sensors, tendons, pairs", other),
    ]
    out = []
    for name, fn in rows:
        a, b = fn(co), fn(ct)
        note = "not from CAD" if a in ("none", "–") and b not in ("none", "–") else ""
        if name == "Joint armature/damping/frictionloss" and all(
                v["armature"] == v["damping"] == v["frictionloss"] == 0 for v in co["joint_dynamics"].values()) \
                and any(v["armature"] or v["damping"] or v["frictionloss"] for v in ct["joint_dynamics"].values()):
            note = "not from CAD"
        if name == "Contact params on collision geoms" and a != b and all(
                (p["condim"], p["friction"], p["solref"], p["priority"]) == (3, [1.0, 0.005, 0.0001], [0.02, 1.0], 0)
                for p in co["contact_params"]):
            note = "not from CAD (ours: MuJoCo's defaults)"
        if name == "Option" and a != b:
            note = "consumer's choice"
        out.append([name, a, b, note])
    return out


def section(label: str, r: dict, root: Path) -> str:
    o, t = r["ours"], r["theirs"]
    L = [f"## {label}", ""]
    L.append(f"Ours `{_rel(o['path'], root)}` ({o['kind'].upper()}: {o['bodies']} bodies, {len(o['joints'])} joints, "
             f"{o['geoms']} geoms) vs theirs `{_rel(t['path'], root)}` ({t['kind'].upper()}: {t['bodies']} bodies, "
             f"{len(t['joints'])} joints, {t['geoms']} geoms). Joints paired by {r['correspondence']['method']}.")
    c = r["correspondence"]
    if c["unmatched_ours"] or c["unmatched_theirs"] or c["parent_mismatch"]:
        L.append(f"Unmatched: ours {c['unmatched_ours'] or '–'}, theirs {c['unmatched_theirs'] or '–'}; "
                 f"different parent: {c['parent_mismatch'] or '–'}.")
    if r["warnings"]:
        L += ["", "Warnings:", ""] + [f"- {w}" for w in r["warnings"]]
    L += ["", "Largest discrepancies, ranked:", "", discrepancies(r), ""]

    b = r["base"]
    L += ["### Base registration (root link shape, ICP)", ""]
    alt = (f"{f(b.get('alt_rotation_from_best_deg'), 0)} deg away: {f(b.get('alt_rms_mm'))} mm"
           if b.get("alt_rms_mm") is not None else "–")
    L.append(table(["ours link", "theirs link", "RMS (mm)", "median (mm)", "within 1 mm (%)", "back RMS (mm)",
                    "rotation (deg)", "translation (mm)", "runner-up"],
                   [[b["ours_link"], b["theirs_link"], f(b.get("rms_mm")), f(b.get("median_mm")),
                     f(b.get("within_1mm_pct"), 1), f(b.get("rms_back_mm")), f(b.get("rotation_deg")),
                     f(b.get("translation_mm"), 1), alt]]))
    L.append("")

    L += ["### Joints: zeros, axes, link shapes", "",
          ("Their value at our zero is the calibration offset (deg, or mm for a slide); sign is +1 when the axes "
           "point the same way. Axis angle and line offset are taken at the matched pose in their world; the "
           "residuals are each link's surface distance to the other's."), ""]
    rows = []
    for j in r["joints"]:
        rows.append([j["joint"] if j["joint"] == j["theirs_joint"] else f"{j['joint']} / {j['theirs_joint']}",
                     j["type"], f(j["offset_display"], 2, True) + (" (ambiguous)" if j["ambiguous"] else ""),
                     f"{int(j['sign']):+d}", f(j["axis_angle_deg"]), f(j["axis_offset_mm"]),
                     f(j.get("resid_ours_to_theirs_rms_mm")), f(j.get("within_1mm_pct"), 1),
                     f(j.get("resid_theirs_to_ours_rms_mm")), f(j.get("within_1mm_back_pct"), 1)])
    L.append(table(["joint", "type", "their value at our zero (deg/mm)", "sign", "axis angle (deg)",
                    "axis line offset (mm)", "ours→theirs RMS (mm)", "within 1 mm (%)", "theirs→ours RMS (mm)",
                    "within 1 mm (%)"], rows))
    L.append("")

    L += ["### Ranges (ours carried into their coordinate)", ""]
    rows = []
    for j in r["joints"]:
        rg = j["range"]
        om, th = rg.get("ours_mapped"), rg.get("theirs")
        rows.append([j["joint"], j["unit"], f(om[0], 1) if om else "–", f(om[1], 1) if om else "–",
                     f(th[0], 1) if th else "–", f(th[1], 1) if th else "–", f(rg.get("d_lo"), 1, True),
                     f(rg.get("d_hi"), 1, True), f(rg.get("overlap_pct"), 1) if rg.get("overlap_pct") is not None
                     else rg.get("note", "–")])
    L.append(table(["joint", "unit", "ours lo", "ours hi", "theirs lo", "theirs hi", "Δ lo", "Δ hi", "overlap (%)"],
                   rows))
    L.append("")

    L += ["### Mass properties (each joint's child link: body + fixed descendants, at the matched pose)", ""]

    def mrow(name, m):
        po, pt = m.get("principal_ours_kgm2"), m.get("principal_theirs_kgm2")
        return [name, f(m["mass_ours_kg"] * 1e3, 1), f(m["mass_theirs_kg"] * 1e3, 1), f(m.get("mass_diff_pct"), 1, True),
                f(m.get("com_dist_mm"), 1), " / ".join(g3(x * 1e4) for x in po) if po else "–",
                " / ".join(g3(x * 1e4) for x in pt) if pt else "–", f(m.get("inertia_rel_diff_pct"), 1)]
    rows = [mrow(f"root ({r['base']['ours_link']})", r["root_mass"])]
    rows += [mrow(f"{j['joint']} ({j['ours_link']} / {j['theirs_link']})", j["mass"]) for j in r["joints"]]
    rows.append(mrow("**total**", r["total_mass"]))
    L.append(table(["link", "mass ours (g)", "theirs (g)", "Δ (%)", "COM Δ (mm)", "principal ours (kg·cm²)",
                    "principal theirs (kg·cm²)", "inertia Δ, Frobenius (%)"], rows))
    L.append("")

    gr = r["gravity"]
    if gr:
        L += [f"### Gravity torques ({gr['configs']} configurations in both ranges, qvel = 0)", "",
              (f"Error relative to the joint's RMS torque (floored at 5% of the largest joint's: a vertical axis "
               f"carries next to none). Overall: {f(gr['rel_rms_pct'], 1)}% RMS; worst single sample "
               f"{f(gr['rel_max_pct'], 1)}% of that joint's peak. {gr['gravity_note']}."), ""]
        rows = [[p["joint"], p["unit"], g3(p["theirs_rms"]), g3(p["err_rms"]), g3(p["err_max"]),
                 f(p["rel_rms_pct"], 1) + (" (floored)" if p.get("floored") else ""), f(p["rel_max_pct"], 1)]
                for p in gr["per_joint"]]
        L.append(table(["joint", "unit", "theirs RMS", "error RMS", "error max", "rel RMS (%)", "rel max (%)"], rows))
        for n in gr["notes"]:
            L.append(f"\n- {n}")
        L.append("")

    L += ["### Collision and the consumer's own", "",
          "What a simulation author adds that the CAD cannot give: ours lacks these by design.", ""]
    L.append(table(["", "ours", "theirs", ""], _consumer_rows(r["consumer"]["ours"], r["consumer"]["theirs"])))
    L.append("")
    return "\n".join(L)


def render(robot: str, title: str, results: list[tuple[str, dict]], missing: list[str], root: Path,
           command: str) -> str:
    L = [f"# {title}: ours vs the hand-made references", "",
         (f"`{command}`. Every file is loaded by MuJoCo (a URDF with its visuals and fixed links kept). "
          "World frames and joint zeros are not compared directly: the root links' shapes are registered (ICP), "
          "then each joint's zero is found by turning their joint until their child link lies on ours, parent "
          "first. Distances are to the other surface; masses are each joint's child link."), ""]
    if missing:
        L += [f"- {m}" for m in missing] + [""]
    if results:
        L += ["## Verdict", "", verdict_table(results), ""]
        for label, r in results:
            L += [section(label, r, root), ""]
    return "\n".join(L).rstrip() + "\n"


def summary(robot: str, label: str, r: dict) -> str:
    v = r["verdict"]
    return (f"{robot} {label}: topology {'match' if v['topology_ok'] else 'DIFFERS'}; "
            f"axes ≤{f(v['max_axis_angle_deg'])} deg / {f(v['max_axis_offset_mm'])} mm; "
            f"base RMS {f(v['base_rms_mm'])} mm; link residual ≤{f(v['max_link_resid_mm'])} mm; "
            f"mass {f(v['total_mass_diff_pct'], 1, True)}% total (worst link {f(v['max_link_mass_diff_pct'], 1)}%); "
            f"gravity torque {f(v['gravity_rel_rms_pct'], 1)}% RMS")
