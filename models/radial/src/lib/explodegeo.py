"""Collision geometry for the exploded view: every leaf of the built assembly as
surface samples, queried under pure TRANSLATIONS (the explode moves parts only
by translation, so a leaf at time t is its STEP placement plus an offset).

Shared by the explode planner (lib/explodeplan.py) and the checker
(lib/explodecheck.py). One process builds the per-prototype samples once and
caches them on disk (tmp/kin/xgeo_<document hash>.npz); every later process
loads that file.

Samples: each prototype is meshed (deflection MESH_DEFL) with outward triangles
and sampled on a grid of pitch <= SAMPLE per triangle with the triangle normal
(the gate's sampler). Every surface point lies within E = SAMPLE + MESH_DEFL of
a sample. `depth(i, oi, j, oj)` is the deepest penetration of either body's
samples under the other's surface (shallowest reading of the 4 nearest
tangent planes, so a sample on a sharp edge does not invent a penetration);
None when the surfaces never come within NEAR. The gate's PEN_TOL/NEAR apply.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parent.parent
ROOT = SRC.parent
CACHE = ROOT / "tmp" / "kin"

SAMPLE = 1.5
MESH_DEFL = 0.05
E = SAMPLE + MESH_DEFL
NEAR = 2 * E + 0.05
PEN_TOL = 0.25
STEP_PATH = [None]
REFINE_MAX = 300      # flagged points re-measured against the mesh (the deepest half + an even spread)

FASTENER_SUFFIXES = ("bolt", "nut", "stud", "screw", "washer", "pin", "clip", "clamp", "wire", "cotter", "retainer")


def is_fastener(label):
    tail = label.split(":", 1)[-1]
    words = tail.split("_")
    # a role word anywhere in the tail after its first word (clamp_ring_bolt_1, retainer_bolt_2_1, bnut)
    # or as the whole role (retainer); numbers and side tags are not roles
    tags = {"lo", "hi", "a", "b", "L", "R", "F"}
    roles = [w for w in words if not w.isdigit() and not (len(w) <= 3 and w[:-1].isdigit()) and w not in tags]
    if not roles:
        return False
    last = roles[-1]
    return last in FASTENER_SUFFIXES or last.endswith("nut") and last != "nut" and len(last) <= 5


def _doc_hash(step_file):
    h = hashlib.sha1()
    with open(step_file, "rb") as f:
        while True:
            b = f.read(1 << 22)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:16]


def _build_cache(step_file, out):
    """Mesh + sample every prototype (run in a child process: frees OCC memory on exit)."""
    sys.path.insert(0, str(SRC))
    from lib import animgen, gate
    w = gate.World(step_file)
    leaves = [{"ref": lf["ref"], "label": lf["label"], "system": lf["system"], "proto": str(lf["proto"]),
               "L": lf["L"].tolist(), "kind": lf["kind"], "args": list(lf["args"]) if isinstance(lf["args"], tuple) else None}
              for lf in w.leaves]
    arrays = {}
    for key in {lf["proto"] for lf in w.leaves}:
        T, _, _ = gate._mesh(w.proto(key))
        if not len(T):
            P = N = np.zeros((0, 3), np.float32)
            V = np.zeros((0, 3), np.float32)
        else:
            gate.SAMPLE = SAMPLE
            P, N = gate._grid_samples(T)
            P, idx = np.unique(np.round(P, 2), axis=0, return_index=True)
            N = N[idx]
            V = np.unique(np.round(T.reshape(-1, 3), 2), axis=0)
        arrays[f"P_{key}"] = P.astype(np.float32)
        arrays[f"N_{key}"] = N.astype(np.float32)
        arrays[f"V_{key}"] = V.astype(np.float32)
    np.savez(out, leaves=np.array(json.dumps(leaves)), **arrays)


def _build_tri_cache(step_file, out):
    """Triangles of every prototype (for exact point-to-mesh depth refinement)."""
    sys.path.insert(0, str(SRC))
    from lib import gate
    w = gate.World(step_file)
    arrays = {}
    for key in {lf["proto"] for lf in w.leaves}:
        T, _, _ = gate._mesh(w.proto(key))
        arrays[f"T_{key}"] = T.astype(np.float32)
    np.savez(out, **arrays)


def _closest_on_triangles(p, A, B, C):
    """Closest points on triangles (A, B, C: (n,3)) to point p (Ericson, vectorised)."""
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - B
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - C
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    denom = va + vb + vc
    with np.errstate(divide="ignore", invalid="ignore"):
        v = vb / denom
        w = vc / denom
    res = A + ab * v[:, None] + ac * w[:, None]
    # region tests (vertex / edge regions), applied in reverse priority
    with np.errstate(divide="ignore", invalid="ignore"):
        m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)
        wbc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        res[m] = (B + (C - B) * wbc[:, None])[m]
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        w2 = d2 / (d2 - d6)
        res[m] = (A + ac * w2[:, None])[m]
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        v2 = d1 / (d1 - d3)
        res[m] = (A + ab * v2[:, None])[m]
    m = (d6 >= 0) & (d5 <= d6)
    res[m] = C[m]
    m = (d3 >= 0) & (d4 <= d3)
    res[m] = B[m]
    m = (d1 <= 0) & (d2 <= 0)
    res[m] = A[m]
    return res


def _closest_on_triangles_many(P, A, B, C):
    """Closest points on triangles (A, B, C) to points P, row by row (Ericson, vectorised)."""
    ab, ac, ap = B - A, C - A, P - A
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = P - B
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = P - C
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    va = d3 * d6 - d5 * d4
    vb = d5 * d2 - d1 * d6
    vc = d1 * d4 - d3 * d2
    with np.errstate(divide="ignore", invalid="ignore"):
        denom = va + vb + vc
        v, w = vb / denom, vc / denom
        res = A + ab * v[:, None] + ac * w[:, None]
        m = (va <= 0) & (d4 - d3 >= 0) & (d5 - d6 >= 0)
        wbc = (d4 - d3) / ((d4 - d3) + (d5 - d6))
        res[m] = (B + (C - B) * wbc[:, None])[m]
        m = (vb <= 0) & (d2 >= 0) & (d6 <= 0)
        w2 = d2 / (d2 - d6)
        res[m] = (A + ac * w2[:, None])[m]
        m = (vc <= 0) & (d1 >= 0) & (d3 <= 0)
        v2 = d1 / (d1 - d3)
        res[m] = (A + ab * v2[:, None])[m]
    m = (d6 >= 0) & (d5 <= d6)
    res[m] = C[m]
    m = (d3 >= 0) & (d4 <= d3)
    res[m] = B[m]
    m = (d1 <= 0) & (d2 <= 0)
    res[m] = A[m]
    return res


class Geo:
    def __init__(self, step_file, refine=False):
        step_file = str(step_file)
        STEP_PATH[0] = step_file
        self.refine = refine
        CACHE.mkdir(parents=True, exist_ok=True)
        path = CACHE / f"xgeo_{_doc_hash(step_file)}.npz"
        if not path.exists():
            import multiprocessing as mp
            t0 = time.time()
            p = mp.get_context("spawn").Process(target=_build_cache, args=(step_file, str(path)))
            p.start()
            p.join()
            if p.exitcode:
                raise RuntimeError("explodegeo: building the sample cache failed")
            print(f"[xgeo] sampled every prototype ({time.time() - t0:.0f}s) -> {path.name}", flush=True)
        self.path = path
        self._tri_path = CACHE / f"xgeo_tri_{path.stem.split('_', 1)[1]}.npz"
        self._tri = None
        self._tris = {}
        z = np.load(path)
        self.leaves = json.loads(str(z["leaves"]))
        self._z = z
        self._s = {}
        self.n = len(self.leaves)
        self.index = {lf["label"]: i for i, lf in enumerate(self.leaves)}
        self.L = np.array([lf["L"] for lf in self.leaves])
        self.Linv = np.linalg.inv(self.L)
        self.proto = [lf["proto"] for lf in self.leaves]
        # tight world boxes at rest (from mesh vertices)
        boxes = []
        self._vbox = {}
        for i, lf in enumerate(self.leaves):
            V = self.verts(i)
            if len(V):
                boxes.append(np.concatenate([V.min(0), V.max(0)]))
            else:
                boxes.append(np.zeros(6))
        self.box = np.array(boxes)

    def _in_local_box(self, key, lo, hi):
        """Indices of prototype `key`'s samples inside the local box [lo, hi] (sphere prefilter
        through the KD-tree, so a small box never scans a big part's million samples)."""
        P, _, tree = self.local_samples(key)
        if tree is None:
            return np.zeros(0, dtype=np.int64)
        c = (lo + hi) / 2
        r = float(np.linalg.norm(hi - lo)) / 2 + 1e-6
        idx = np.asarray(tree.query_ball_point(c, r), dtype=np.int64)
        if not len(idx):
            return idx
        Q = P[idx]
        return idx[np.all(Q >= lo, axis=1) & np.all(Q <= hi, axis=1)]

    def local_samples(self, key):
        if key not in self._s:
            from scipy.spatial import cKDTree
            P = self._z[f"P_{key}"].astype(np.float64)
            N = self._z[f"N_{key}"].astype(np.float64)
            self._s[key] = (P, N, cKDTree(P) if len(P) else None)
        return self._s[key]

    def ensure_triangles(self):
        """Build the triangle cache now (call in the main process, before any pool)."""
        if not self._tri_path.exists():
            import multiprocessing as mp
            t0 = time.time()
            p = mp.get_context("spawn").Process(target=_build_tri_cache, args=(str(STEP_PATH[0]), str(self._tri_path)))
            p.start()
            p.join()
            print(f"[xgeo] triangle cache ({time.time() - t0:.0f}s) -> {self._tri_path.name}", flush=True)

    def triangles(self, key):
        """(A, B, C, face normals, KD-tree over centroids, max circumradius) of a prototype."""
        if key not in self._tris:
            if self._tri is None:
                if not self._tri_path.exists():
                    import multiprocessing as mp
                    p = mp.get_context("spawn").Process(target=_build_tri_cache,
                                                        args=(str(STEP_PATH[0]), str(self._tri_path)))
                    p.start()
                    p.join()
                self._tri = np.load(self._tri_path)
            from scipy.spatial import cKDTree
            T = self._tri[f"T_{key}"].astype(np.float64)
            A, B, C = T[:, 0], T[:, 1], T[:, 2]
            Nf = np.cross(B - A, C - A)
            Nf /= np.maximum(np.linalg.norm(Nf, axis=1), 1e-12)[:, None]
            cen = (A + B + C) / 3
            rad = float(np.max(np.linalg.norm(T - cen[:, None, :], axis=2))) if len(T) else 0.0
            self._tris[key] = (A, B, C, Nf, cKDTree(cen) if len(T) else None, rad)
        return self._tris[key]

    def mesh_depth(self, X, key):
        """Signed depth (+ inside) of points X (prototype frame of `key`) under its triangle mesh:
        distance to the closest triangle, negative (outside) when any equally-close triangle's
        normal says outside. Vectorised over all (point, nearby triangle) pairs."""
        A, B, C, Nf, tree, rad = self.triangles(key)
        out = np.full(len(X), -np.inf)
        if tree is None or not len(X):
            return out
        lists = tree.query_ball_point(X, NEAR + rad)
        counts = np.array([len(l) for l in lists])
        if counts.sum() == 0:
            return out
        tri = np.concatenate([np.asarray(l, dtype=np.int64) for l in lists if len(l)])
        pid = np.repeat(np.arange(len(X)), counts)
        P = X[pid]
        q = _closest_on_triangles_many(P, A[tri], B[tri], C[tri])
        d = np.linalg.norm(q - P, axis=1)
        sgn = np.einsum("ij,ij->i", P - q, Nf[tri])
        order = np.lexsort((d, pid))
        pid_s, d_s, sgn_s = pid[order], d[order], sgn[order]
        first = np.ones(len(pid_s), bool)
        first[1:] = pid_s[1:] != pid_s[:-1]
        dmin = np.full(len(X), np.inf)
        dmin[pid_s[first]] = d_s[first]
        # outside if any triangle within 1e-6 of the minimum distance has a non-negative sign
        near_min = d_s <= dmin[pid_s] + 1e-6
        outside = np.zeros(len(X), bool)
        np.logical_or.at(outside, pid_s[near_min & (sgn_s >= 0)], True)
        has = counts > 0
        out[has] = np.where(outside[has], -dmin[has], dmin[has])
        return out

    def verts(self, i):
        """World mesh vertices of leaf i at rest."""
        V = self._z[f"V_{self.proto[i]}"].astype(np.float64)
        M = self.L[i]
        return V @ M[:3, :3].T + M[:3, 3]

    def world_samples(self, i, off):
        P, N, _ = self.local_samples(self.proto[i])
        M = self.L[i]
        return P @ M[:3, :3].T + M[:3, 3] + off, N @ M[:3, :3].T

    def _one_way(self, i, oi, j, oj, box):
        """Depth of i's samples (inside box) under j's surface; (depth, n_near) or None."""
        P, N, _ = self.local_samples(self.proto[i])
        Q, NQ, tree = self.local_samples(self.proto[j])
        if not len(P) or tree is None:
            return None
        Mi, Mj_inv = self.L[i], self.Linv[j]
        Mi_inv = self.Linv[i]
        c = np.array([[x, y, z] for x in (box[0], box[3]) for y in (box[1], box[4]) for z in (box[2], box[5])]) - oi
        lc = c @ Mi_inv[:3, :3].T + Mi_inv[:3, 3]
        m0 = self._in_local_box(self.proto[i], lc.min(0), lc.max(0))
        if not len(m0):
            return None
        W = P[m0] @ Mi[:3, :3].T + Mi[:3, 3] + oi
        m = np.all(W >= box[:3], axis=1) & np.all(W <= box[3:], axis=1)
        if not m.any():
            return None
        W = W[m] - oj
        X = W @ Mj_inv[:3, :3].T + Mj_inv[:3, 3]          # into j's prototype frame
        d1, _ = tree.query(X, k=1, distance_upper_bound=NEAR)
        X = X[np.isfinite(d1)]
        if not len(X):
            return None
        k = min(4, len(Q))
        d, idx = tree.query(X, k=k, distance_upper_bound=NEAR)
        d, idx = d.reshape(len(X), k), idx.reshape(len(X), k)
        ok = np.isfinite(d)
        jj = np.where(ok, idx, 0)
        dep = -np.einsum("pkj,pkj->pk", X[:, None, :] - Q[jj], NQ[jj])
        dep = np.where(ok, dep, np.inf).min(axis=1)
        top = float(dep.max())
        if self.refine and top > PEN_TOL:
            # sample tangent planes misread thin walls and edges (a point beside a 1.5 mm wall can
            # read the far face): re-measure flagged points against the triangle mesh. A real
            # penetration has many inside points, so a subset (the deepest + a spread) decides.
            flag = np.flatnonzero(dep > PEN_TOL)
            if len(flag) > REFINE_MAX:
                order = flag[np.argsort(-dep[flag])]
                rest = order[REFINE_MAX // 2:]
                pick = np.concatenate([order[:REFINE_MAX // 2],
                                       rest[np.linspace(0, len(rest) - 1, REFINE_MAX // 2).astype(int)]])
            else:
                pick = flag
            top = max(float(np.max(np.where(dep <= PEN_TOL, dep, -np.inf))) if np.any(dep <= PEN_TOL) else -np.inf,
                      float(self.mesh_depth(X[pick], self.proto[j]).max()))
        return top, len(X)

    def depth(self, i, oi, j, oj):
        """Deepest penetration between leaves i and j at offsets oi, oj (mm); None = apart."""
        bi, bj = self.box[i].copy(), self.box[j].copy()
        bi[:3] += oi; bi[3:] += oi
        bj[:3] += oj; bj[3:] += oj
        box = np.concatenate([np.maximum(bi[:3], bj[:3]) - NEAR, np.minimum(bi[3:], bj[3:]) + NEAR])
        if np.any(box[:3] > box[3:]):
            return None
        a = self._one_way(i, oi, j, oj, box)
        b = self._one_way(j, oj, i, oi, box)
        vals = [x[0] for x in (a, b) if x is not None]
        return max(vals) if vals else None

    def gap(self, i, oi, j, oj, reach=200.0):
        """Lower bound (mm) on the surface distance of i and j at these offsets:
        min sample distance minus 2E (every surface point lies within E of a sample).
        Looks only within `reach` of the other body's box; returns reach if nothing is that close."""
        bi = self.box[i] + np.concatenate([oi, oi])
        bj = self.box[j] + np.concatenate([oj, oj])
        sep = np.maximum(0, np.maximum(bi[:3] - bj[3:], bj[:3] - bi[3:]))
        sd = float(np.linalg.norm(sep))
        if sd >= reach:
            return reach
        # query with the body that has FEWER samples near the other's box (a piston inside a
        # finned barrel: the barrel's bore strip, not the whole piston)
        def near_pts(i_, oi_, bj_):
            P_ = self.local_samples(self.proto[i_])[0]
            if not len(P_):
                return P_
            lo_, hi_ = bj_[:3] - reach - oi_, bj_[3:] + reach - oi_
            Mi_inv_ = self.Linv[i_]
            c_ = np.array([[x, y, z] for x in (lo_[0], hi_[0]) for y in (lo_[1], hi_[1]) for z in (lo_[2], hi_[2])])
            lc_ = c_ @ Mi_inv_[:3, :3].T + Mi_inv_[:3, 3]
            m_ = self._in_local_box(self.proto[i_], lc_.min(0), lc_.max(0))
            W_ = P_[m_] @ self.L[i_][:3, :3].T + self.L[i_][:3, 3] + oi_
            return W_[np.all(W_ >= bj_[:3] - reach, axis=1) & np.all(W_ <= bj_[3:] + reach, axis=1)]
        Wi = near_pts(i, oi, bj)
        Wj = near_pts(j, oj, bi)
        if len(Wj) < len(Wi):
            i, j, oi, oj, Wi = j, i, oj, oi, Wj
        _, _, tree = self.local_samples(self.proto[j])
        if not len(Wi) or tree is None:
            return reach
        Mj_inv = self.Linv[j]
        X = (Wi - oj) @ Mj_inv[:3, :3].T + Mj_inv[:3, 3]
        d, _ = tree.query(X, k=1, distance_upper_bound=reach + 2 * E)
        dm = float(d.min())
        if not np.isfinite(dm):
            return reach
        return max(0.0, dm - 2 * E)

    def clearance_boxes(self, i, oi, j, oj, pad=0.0):
        bi, bj = self.box[i] + np.concatenate([oi, oi]), self.box[j] + np.concatenate([oj, oj])
        return np.any(bi[:3] - pad > bj[3:]) or np.any(bj[:3] - pad > bi[3:])


class Exact:
    """Exact OCC common volume of two leaves at translation offsets (lazy scene load)."""

    def __init__(self, step_file):
        self.step_file = str(step_file)
        self._w = None

    def world(self):
        if self._w is None:
            sys.path.insert(0, str(SRC))
            from lib import gate
            self._w = gate.World(self.step_file)
        return self._w

    def volume(self, i, oi, j, oj):
        from lib import gate
        w = self.world()
        a, b = w.leaves[i], w.leaves[j]
        Wa, Wb = a["L"].copy(), b["L"].copy()
        Wa[:3, 3] += oi
        Wb[:3, 3] += oj
        return gate._common_volume(gate._located(w.proto(a["proto"]), Wa), gate._located(w.proto(b["proto"]), Wb))
