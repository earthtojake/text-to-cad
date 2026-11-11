"""Geometry for compare.py: surfaces sampled by area, exact point-to-surface distance, rigid fits.

A ``Surface`` is a triangle soup in one world frame with area-weighted samples on it and a KD-tree
over them. Distances come two ways: ``fast`` (to the nearest sample, used inside searches; its floor
is the sample spacing) and ``exact`` (to the closest point of the triangles behind the k nearest
samples, used for every number the report prints).
"""

from __future__ import annotations

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

DENSE = 30000  # samples on a surface that is searched against
QUERY = 3000  # samples taken from a surface that is the query side


class Surface:
    def __init__(self, tris: np.ndarray, n: int = DENSE, seed: int = 0):
        tris = np.asarray(tris, dtype=float).reshape(-1, 3, 3)
        area = 0.5 * np.linalg.norm(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0]), axis=1)
        keep = area > 0
        self.tris, self.area = tris[keep], area[keep]
        self.total_area = float(self.area.sum())
        rng = np.random.default_rng(seed)
        if len(self.tris) == 0:
            self.samples = np.zeros((0, 3))
            self.sample_tri = np.zeros(0, dtype=int)
            self.tree = None
            return
        tri = rng.choice(len(self.tris), size=n, p=self.area / self.total_area)
        u, v = rng.random(n), rng.random(n)
        flip = u + v > 1
        u[flip], v[flip] = 1 - u[flip], 1 - v[flip]
        t = self.tris[tri]
        self.samples = t[:, 0] + u[:, None] * (t[:, 1] - t[:, 0]) + v[:, None] * (t[:, 2] - t[:, 0])
        self.sample_tri = tri
        self.tree = cKDTree(self.samples)

    def __len__(self) -> int:
        return len(self.samples)

    def query_points(self, n: int = QUERY) -> np.ndarray:
        """A random subset of the samples (they are already in random order)."""
        return self.samples[:n]

    def transformed(self, R: np.ndarray, t: np.ndarray, n: int = DENSE) -> Surface:
        return Surface(self.tris @ R.T + t, n=n)

    def distance(self, pts: np.ndarray, exact: bool = True, k: int = 8,
                 closest: bool = False):
        """Distance from each point to this surface (and the closest points, if asked)."""
        pts = np.asarray(pts, dtype=float)
        if self.tree is None or len(pts) == 0:
            d = np.full(len(pts), np.inf)
            return (d, pts.copy()) if closest else d
        if not exact:
            d, i = self.tree.query(pts)
            return (d, self.samples[i]) if closest else d
        k = min(k, len(self.samples))
        _, idx = self.tree.query(pts, k=k)
        idx = idx.reshape(len(pts), k)
        tri = self.sample_tri[idx]  # (Q, k)
        rep = np.repeat(pts, k, axis=0)
        cp = trimesh.triangles.closest_point(self.tris[tri.ravel()], rep).reshape(len(pts), k, 3)
        dd = np.linalg.norm(cp - pts[:, None, :], axis=2)
        j = np.argmin(dd, axis=1)
        d = dd[np.arange(len(pts)), j]
        return (d, cp[np.arange(len(pts)), j]) if closest else d


def kabsch(src: np.ndarray, dst: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The rotation and translation that best map ``src`` onto ``dst`` (least squares)."""
    cs, cd = src.mean(0), dst.mean(0)
    H = (src - cs).T @ (dst - cd)
    U, _, Vt = np.linalg.svd(H)
    D = np.diag([1.0, 1.0, np.sign(np.linalg.det(Vt.T @ U.T)) or 1.0])
    R = Vt.T @ D @ U.T
    return R, cd - R @ cs


def cube_rotations() -> list[np.ndarray]:
    """The 24 proper rotations that map coordinate axes onto coordinate axes."""
    out = []
    for perm in ((0, 1, 2), (0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)):
        for sx in (1, -1):
            for sy in (1, -1):
                for sz in (1, -1):
                    R = np.zeros((3, 3))
                    for row, (col, s) in enumerate(zip(perm, (sx, sy, sz))):
                        R[row, col] = s
                    if np.linalg.det(R) > 0:
                        out.append(R)
    return out


def pca_rotations(src: np.ndarray, dst: np.ndarray) -> list[np.ndarray]:
    """Rotations taking ``src``'s principal axes onto ``dst``'s, every proper sign choice."""
    def axes(p):
        w, V = np.linalg.eigh(np.cov((p - p.mean(0)).T))
        return V[:, np.argsort(w)[::-1]]
    Vs, Vd = axes(src), axes(dst)
    out = []
    for s in ((1, 1, 1), (1, -1, -1), (-1, 1, -1), (-1, -1, 1), (1, 1, -1), (1, -1, 1), (-1, 1, 1), (-1, -1, -1)):
        R = Vd @ np.diag(s) @ Vs.T
        if np.linalg.det(R) > 0:
            out.append(R)
    return out


def rotation_angle_deg(R: np.ndarray) -> float:
    return float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1))))


def icp(src: np.ndarray, target: Surface, R: np.ndarray, t: np.ndarray, iters: int = 30,
        exact_iters: int = 0, trim: float = 0.9) -> tuple[np.ndarray, np.ndarray, float]:
    """Trimmed point-to-point ICP of ``src`` onto ``target``; the last ``exact_iters`` use
    exact closest surface points. Returns R, t and the trimmed mean distance."""
    prev = np.inf
    for it in range(iters + exact_iters):
        p = src @ R.T + t
        d, q = target.distance(p, exact=it >= iters, closest=True)
        # inliers: the closest ``trim`` share, and no farther than a few medians (parts one side
        # has and the other lacks must not pull the fit)
        cut = min(np.quantile(d, trim), max(4 * np.median(d), 5e-4))
        keep = d <= cut
        if keep.sum() < 10:
            keep = d <= np.quantile(d, trim)
        R, t = kabsch(src[keep], q[keep])
        cur = float(d[keep].mean())
        if it < iters and abs(prev - cur) < 1e-9:
            # converged on samples: go straight to the exact iterations
            iters = it + 1
        prev = cur
    d = target.distance(src @ R.T + t, exact=True)
    return R, t, score(d)


def score(d: np.ndarray, cap: float = 0.002) -> float:
    """Mean distance with each point's share capped: what fits counts, what differs adds a constant."""
    return float(np.minimum(d, cap).mean())


def register(src: Surface, dst: Surface) -> dict:
    """The rigid transform taking ``src`` onto ``dst``: ICP from the 24 axis-aligned rotations and
    the principal-axis rotations, the best few refined; returns the winner and the runner-up
    that differs from it by more than 5 degrees."""
    ps = src.query_points(800)
    pd = dst.query_points(800)
    cs, cd = src.samples.mean(0), dst.samples.mean(0)
    starts = cube_rotations() + pca_rotations(ps, pd)
    coarse = []
    for R0 in starts:
        R, t, s = icp(ps, dst, R0, cd - R0 @ cs, iters=25)
        coarse.append((s, R, t))
    coarse.sort(key=lambda c: c[0])
    distinct: list[tuple[float, np.ndarray, np.ndarray]] = []
    for s, R, t in coarse:
        if all(rotation_angle_deg(R @ R2.T) > 5 for _, R2, _ in distinct):
            distinct.append((s, R, t))
        if len(distinct) == 4:
            break
    q = src.query_points()
    fine = []
    for _, R, t in distinct:
        R, t, s = icp(q, dst, R, t, iters=40, exact_iters=15)
        fine.append((s, R, t))
    fine.sort(key=lambda c: c[0])
    best = fine[0]
    alt = next((f for f in fine[1:] if rotation_angle_deg(f[1] @ best[1].T) > 5), None)
    R, t = best[1], best[2]
    d_fwd = dst.distance(q @ R.T + t)
    back = src.transformed(R, t)
    d_back = back.distance(dst.query_points())
    out = {
        "R": R, "t": t, "score_mm": best[0] * 1e3,
        "rms_mm": rms(d_fwd) * 1e3, "median_mm": float(np.median(d_fwd)) * 1e3,
        "within_1mm_pct": 100 * float((d_fwd <= 1e-3).mean()),
        "rms_back_mm": rms(d_back) * 1e3,
        "rotation_deg": rotation_angle_deg(R),
        "translation_mm": float(np.linalg.norm(t)) * 1e3,
        "rotvec_deg": (Rotation.from_matrix(R).as_rotvec() * 180 / np.pi).tolist(),
    }
    if alt is not None:
        d_alt = dst.distance(q @ alt[1].T + alt[2])
        out["alt_rms_mm"] = rms(d_alt) * 1e3
        out["alt_score_mm"] = alt[0] * 1e3
        out["alt_rotation_from_best_deg"] = rotation_angle_deg(alt[1] @ R.T)
    return out


def rms(d: np.ndarray) -> float:
    d = np.asarray(d, dtype=float)
    return float(np.sqrt(np.mean(d ** 2))) if len(d) else float("nan")


def axis_rotation(axis: np.ndarray, angle: float) -> np.ndarray:
    return Rotation.from_rotvec(np.asarray(axis, dtype=float) * angle).as_matrix()


def line_distance(p1: np.ndarray, a1: np.ndarray, p2: np.ndarray, a2: np.ndarray) -> float:
    """Distance between the lines p1 + s a1 and p2 + s a2 (unit axes)."""
    c = np.cross(a1, a2)
    n = np.linalg.norm(c)
    w = p2 - p1
    if n < 1e-3:  # parallel or nearly: the distance of p2 from line 1
        a = a1 if np.dot(a1, a2) >= 0 else -a1
        a = (a + a2) / np.linalg.norm(a + a2)
        return float(np.linalg.norm(w - np.dot(w, a) * a))
    return float(abs(np.dot(w, c)) / n)


def primitive_mesh(gtype: str, size: np.ndarray) -> trimesh.Trimesh | None:
    """A triangle mesh of a MuJoCo primitive geom in its own frame."""
    if gtype == "box":
        return trimesh.creation.box(extents=2 * size[:3])
    if gtype == "sphere":
        return trimesh.creation.icosphere(subdivisions=2, radius=size[0])
    if gtype == "capsule":
        return trimesh.creation.capsule(height=2 * size[1], radius=size[0], count=[24, 12])
    if gtype == "cylinder":
        return trimesh.creation.cylinder(radius=size[0], height=2 * size[1], sections=32)
    if gtype == "ellipsoid":
        m = trimesh.creation.icosphere(subdivisions=2, radius=1.0)
        m.apply_scale(size[:3])
        return m
    return None
