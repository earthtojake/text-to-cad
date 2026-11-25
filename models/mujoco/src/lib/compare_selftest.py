"""Check that compare.py recovers what it is built to find: a model against itself moved.

    python src/lib/compare_selftest.py

Each case writes a temporary copy of a Menagerie MJCF with the whole robot inside one extra body at a
known pose (a rigid transform of its world), every joint's ``ref`` shifted by a known amount, some
joints' axes flipped (and their ranges carried along), then compares the original ("ours") with the
copy ("theirs"). The registration must return the transform, each joint its offset and sign, and
everything else -- axes, link shapes, ranges, mass, gravity torques -- must agree to rounding.
A last case pairs the maker's SO-101 URDF with the moved Menagerie copy: different files, so only
the kinematics are held to tolerances there.

Exits non-zero when a check fails.
"""

from __future__ import annotations

import math
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from scipy.spatial.transform import Rotation

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from lib.compare_core import compare
from lib.compare_model import describe
from sources import ROBOTS

TOL = {"rotation_deg": 0.05, "translation_mm": 0.1, "offset_deg": 0.05, "offset_mm": 0.05,
       "axis_angle_deg": 0.05, "axis_offset_mm": 0.1, "resid_mm": 0.3, "range": 0.05,
       "mass_pct": 1e-6, "com_mm": 0.01, "inertia_pct": 1e-3, "gravity_pct": 0.1}


def moved_copy(src: Path, R: np.ndarray, t: np.ndarray, offsets: dict[str, float], flips: set[str],
               folder: Path) -> Path:
    """``src`` with its robot moved by (R, t), each joint's ref shifted by ``offsets`` and the axes of
    ``flips`` reversed; asset paths made absolute so the copy loads from anywhere."""
    tree = ET.parse(src)
    root = tree.getroot()
    comp = root.find("compiler")
    if comp is None:
        comp = ET.SubElement(root, "compiler")
    base = src.parent.resolve()
    asset = comp.attrib.pop("assetdir", None)
    for k in ("meshdir", "texturedir"):
        v = comp.get(k, asset or "")
        comp.set(k, str((base / v).resolve()))
    degree = comp.get("angle", "degree") == "degree"
    for inc in root.iter("include"):
        inc.set("file", str((base / inc.get("file")).resolve()))
    world = root.find("worldbody")
    frame = ET.Element("body", {"name": "selftest_frame", "pos": " ".join(map(repr, t.tolist())),
                                "quat": " ".join(map(repr, np.roll(Rotation.from_matrix(R).as_quat(), 1).tolist()))})
    for b in list(world.findall("body")):
        world.remove(b)
        frame.append(b)
    world.append(frame)
    for j in root.iter("joint"):
        name = j.get("name")
        if name not in offsets:
            continue
        slide = j.get("type") == "slide"
        k = 1.0 if slide or not degree else 180 / math.pi
        d = offsets[name]
        j.set("ref", repr(d * k))
        flip = name in flips
        if flip:
            axis = np.array([float(x) for x in j.get("axis", "0 0 1").split()])
            j.set("axis", " ".join(map(repr, (-axis).tolist())))
        if j.get("range"):
            lo, hi = (float(x) / k for x in j.get("range").split())
            lo, hi = (d - hi, d - lo) if flip else (lo + d, hi + d)
            j.set("range", f"{lo * k!r} {hi * k!r}")
    for key in list(root.iter("keyframe")):
        root.remove(key)  # its qpos no longer means the same pose
    out = folder / src.name
    tree.write(out)
    return out


def joint_names(path: Path) -> list[tuple[str, bool]]:
    d = describe("x", path)
    return [(j.name, j.kind == "slide") for j in d.joints]


def checks_for(r: dict, R: np.ndarray, t: np.ndarray, offsets: dict[str, float], flips: set[str],
               full: bool) -> list[tuple[str, float, float]]:
    """(what, error, tolerance) for every check of one result."""
    out = []
    Rg, tg = np.array(r["base"]["R"]), np.array(r["base"]["t_m"])
    rot_err = math.degrees(Rotation.from_matrix(Rg @ R.T).magnitude())
    out.append(("base rotation (deg)", rot_err, TOL["rotation_deg"]))
    out.append(("base translation (mm)", float(np.linalg.norm(tg - t)) * 1e3, TOL["translation_mm"]))
    for j in r["joints"]:
        n = j["joint"]
        hinge = j["type"] == "hinge"
        exp = offsets[n]
        err = (math.remainder(j["offset"] - exp, 2 * math.pi) if hinge else j["offset"] - exp)
        err *= 180 / math.pi if hinge else 1e3
        out.append((f"{n} offset ({'deg' if hinge else 'mm'})", abs(err),
                    TOL["offset_deg"] if hinge else TOL["offset_mm"]))
        out.append((f"{n} sign", 0.0 if j["sign"] == (-1 if n in flips else 1) else 1.0, 0.5))
        out.append((f"{n} axis angle (deg)", j["axis_angle_deg"], TOL["axis_angle_deg"]))
        if hinge:
            out.append((f"{n} axis line offset (mm)", j["axis_offset_mm"], TOL["axis_offset_mm"]))
        if full:
            out.append((f"{n} link residual (mm)", max(j["resid_ours_to_theirs_rms_mm"],
                                                       j["resid_theirs_to_ours_rms_mm"]), TOL["resid_mm"]))
            rg = j["range"]
            if rg.get("d_lo") is not None:
                out.append((f"{n} range ends ({j['unit']})", max(abs(rg["d_lo"]), abs(rg["d_hi"])), TOL["range"]))
            m = j["mass"]
            out.append((f"{n} link mass (%)", abs(m["mass_diff_pct"]), TOL["mass_pct"]))
            out.append((f"{n} link COM (mm)", m["com_dist_mm"], TOL["com_mm"]))
            out.append((f"{n} link inertia (%)", m["inertia_rel_diff_pct"], TOL["inertia_pct"]))
    if full:
        out.append(("total mass (%)", abs(r["total_mass"]["mass_diff_pct"]), TOL["mass_pct"]))
        out.append(("gravity torque RMS (%)", r["gravity"]["rel_rms_pct"], TOL["gravity_pct"]))
        out.append(("gravity torque max (%)", r["gravity"]["rel_max_pct"], TOL["gravity_pct"]))
    return out


def main() -> int:
    rng = np.random.default_rng(7)
    so101, wxai = ROBOTS["so101"], ROBOTS["wxai"]
    cases = [
        ("so101 Menagerie vs itself moved", so101.menagerie_path, so101.menagerie_path, (25, -40, 70),
         (0.12, -0.07, 0.30), True),
        ("wxai Menagerie vs itself moved", wxai.menagerie_path, wxai.menagerie_path, (-15, 35, 160),
         (-0.25, 0.10, -0.05), True),
        ("so101 vendor URDF vs Menagerie moved", so101.vendor_urdf_file, so101.menagerie_path, (90, 0, -30),
         (0.0, 0.2, 0.1), False),
    ]
    failed = 0
    with tempfile.TemporaryDirectory(prefix="compare_selftest_") as tmp:
        for i, (label, ours, theirs_src, euler, trans, full) in enumerate(cases):
            t0 = time.time()
            R = Rotation.from_euler("xyz", euler, degrees=True).as_matrix()
            t = np.array(trans)
            names = joint_names(theirs_src)
            offsets = {n: (rng.uniform(-0.01, 0.01) if slide else rng.uniform(-1.0, 1.0)) for n, slide in names}
            flips = {n for k, (n, _) in enumerate(names) if k % 2 == 1}
            folder = Path(tmp) / str(i)
            folder.mkdir()
            moved = moved_copy(theirs_src, R, t, offsets, flips, folder)
            r = compare(describe("ours", ours), describe("theirs", moved), configs=20)
            results = checks_for(r, R, t, offsets, flips, full)
            bad = [c for c in results if not (c[1] <= c[2])]
            failed += len(bad)
            worst = {}
            for what, err, tol in results:
                kind = what.split(" ", 1)[1] if what.split(" ")[0] in offsets else what
                if err / tol >= worst.get(kind, (0, 0, 1))[1] / worst.get(kind, (0, 0, 1))[2]:
                    worst[kind] = (what, err, tol)
            print(f"\n{label}  [{time.time() - t0:.0f} s]: {len(results) - len(bad)}/{len(results)} checks pass")
            print(f"  moved by {euler} deg (xyz), {tuple(x * 1e3 for x in trans)} mm; offsets "
                  + ", ".join(f"{n} {math.degrees(v) if not s else v * 1e3:+.1f}{'' if not s else ' mm'}"
                              + (" (flipped)" if n in flips else "") for (n, s), v in zip(names, offsets.values())))
            print(f"  {'worst of each check':<42}{'error':>12}{'tolerance':>12}")
            for kind, (what, err, tol) in worst.items():
                print(f"  {what:<42}{err:>12.2e}{tol:>12.2e}  {'ok' if err <= tol else 'FAIL'}")
            for what, err, tol in bad:
                print(f"  FAIL {what}: {err:.3g} > {tol:.3g}")
            for w in r["warnings"]:
                print(f"  warning: {w}")
    print("\nself-test " + ("passed" if not failed else f"FAILED ({failed} checks)"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
