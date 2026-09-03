"""Four camshafts with exact synthesised lobes, cam caps and cap bolts.

A lobe outline is the inner envelope of the roller-centre path for that
valve (lib/kin.lobe_profile), so the roller rides it with zero
interpenetration at every crank angle. Lobes are authored at theta = 0 (cam
angle 0) directly in the engine frame.
"""

from __future__ import annotations

from cadgen import build123d as bd

from lib import fasteners as F, geo, kin, palette as P, spec as S
from lib.castings import safe_fillet, safe_chamfer, fuse_all, is_sound
from lib.heads import CAM_SADDLE_X, CAM_SADDLE_W, HEAD_REAR_X

CAM_SHAFT_D = 24.0
CAM_REAR_X = HEAD_REAR_X + 10.0
CAM_NOSE_X = {1: S.CHAIN_X[1] + 8.0, 2: S.CHAIN_X[2] + 8.0}


def cam_axis(bank: int, kind: str):
    return S.bank_point(bank, 0, S.CAM_M[kind], S.CAM_H)[1:]


def lobe(g: kin.ValveGeom, samples: int = 360):
    yc, zc = g.cam
    pts = [(yc + q[0], zc + q[1]) for q in kin.lobe_profile(g, samples)]
    curve = bd.Spline(*[(y, z) for y, z in pts], periodic=True)
    face = bd.make_face([curve])
    solid = bd.extrude(geo.yz_plane(g.x - S.CAM_LOBE_W / 2) * face, amount=S.CAM_LOBE_W)
    return solid


def build_cam(bank: int, kind: str):
    yc, zc = cam_axis(bank, kind)
    parts = [geo.cyl_x(CAM_REAR_X, CAM_NOSE_X[bank], CAM_SHAFT_D, yc, zc)]
    for xs in CAM_SADDLE_X:
        parts.append(geo.cyl_x(max(xs - CAM_SADDLE_W / 2 - 1.0, HEAD_REAR_X + 2.0), xs + CAM_SADDLE_W / 2 + 1.0, S.CAM_JOURNAL_D, yc, zc))  # never past the rear blank cap
    for c in S.CYLINDERS:
        if c.bank != bank:
            continue
        for side in (-1, 1):
            g = kin.valve_geom(c.number, kind, side)
            parts.append(lobe(g))
    # thrust flange behind the nose journal
    parts.append(geo.cyl_x(S.CAM_FRONT_X + 1.0, S.CAM_FRONT_X + 5.0, 36.0, yc, zc))
    cam = fuse_all(parts)
    assert is_sound(cam), f"cam {bank}/{kind} not sound"
    return P.style(cam, f"camshaft:{bank}_{kind}", P.STEEL_DARK)


def build_caps(bank: int, kind: str, sectioned: bool = True):
    yc, zc = cam_axis(bank, kind)
    parts = []
    m = S.CAM_M[kind]
    for k, xs in enumerate(CAM_SADDLE_X):
        top = S.bank_point(bank, xs, m, S.CAM_H)
        if geo.in_section_void(top, bank, sectioned):
            continue
        cap = bd.Box(CAM_SADDLE_W, 52.0, S.CAM_CAP_H, align=(bd.Align.CENTER, bd.Align.CENTER, bd.Align.MIN))
        cap = cap - bd.Cylinder(S.CAM_JOURNAL_D / 2 + 0.1, 40, align=(bd.Align.CENTER,) * 3).rotate(bd.Axis.Y, 90)
        cap, _ = safe_fillet(cap, [e for e in cap.edges() if abs(e.center().Z - S.CAM_CAP_H) < 1e-3 and abs(e.center().Y) > 20], 5.0)
        cap = geo.locate(cap, top, S.bank_up(bank), (1, 0, 0))
        parts.append(P.style(cap, f"cam_cap:{bank}_{kind}_{k + 1}", P.MACHINED))
        for sm in (-1, 1):
            seat = S.bank_point(bank, xs, m + sm * 20.0, S.CAM_H + S.CAM_CAP_H)
            bolt = F.socket_cap_bolt(8.0, 45.0)
            parts.append(P.style(geo.locate(bolt, seat, S.bank_up(bank), (1, 0, 0)),
                                 f"cam_cap_bolt:{bank}_{kind}_{k + 1}_{'a' if sm < 0 else 'b'}", P.STEEL_DARK))
    return parts


def build(sectioned: bool = True):
    parts = []
    for bank in (1, 2):
        for kind in ("intake", "exhaust"):
            parts.append(build_cam(bank, kind))
            parts += build_caps(bank, kind, sectioned)
    return parts
