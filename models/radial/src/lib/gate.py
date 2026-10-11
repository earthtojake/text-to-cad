"""THE KINEMATIC GATE: no moving part ever interpenetrates anything, over 720 deg.

    cd src && python -m lib.gate [--step 10] [--angles 0,90] [--workers 2]
                                 [--json ../tmp/gate.json] [--file ../STEP/radial.step]
    cd src && python -m lib.gate --static [--workers 2]      # every leaf pair at rest
    cd src && python -m lib.gate --clip exploded-running [--step 10] [--no-exact-near]

Kinematic mode
  1. Reads the BUILT assembly (read_scene: every leaf with its label, shared
     prototype geometry and world placement).
  2. Samples the `running` clip (lib/clips.py) at every crank angle as the build
     samples it, on this STEP's own labels (lib/animcheck.sample), and asserts it
     equals kin.py (lib/animcheck, < 1e-6), so the gate checks the motion the
     keyframes are baked from.
  3. At each angle every moving leaf is re-located by the clip's matrix (a
     TopLoc_Location on the shared prototype, never rebuilt); each deformed valve
     spring is rebuilt by sweeping its wire circle (kin.SPRINGS wire diameter)
     along kin.spring_path(theta), the centreline the viewer's tube deformation
     follows (an undeformed spring is the built STEP body itself).
  4. Candidate pairs: a moving leaf vs any leaf of ANOTHER motion group (one rigid
     group never moves internally: --static covers it); world AABB then
     oriented-box (separating axes) prefilter, both inflated by 1 mm.
  5. The surface-sample test below decides apart / touching / interpenetrating;
     only interpenetrating pairs reach the exact OCC boolean (BRepAlgoAPI_Common +
     GProp volume). A pair COLLIDES when the common volume > 0.5 mm^3, so
     touching without overlap is legal (roller on cam, ring in bore, pin in
     bushing, ball in socket). A boolean that fails even fuzzy is UNDECIDED,
     never clear.
  Results are memoised on the pair's RELATIVE placement.

Clip mode (--clip exploded-running): the clip's matrices and hidden set, sampled
as in kinematic mode (checked against kin.py + lib/explodedrun.py first); EVERY
visible leaf is placed (running motion + its constant offset), deformed springs
are swept along kin.spring_path and offset. Every visible pair is tested except
those whose relative placement is the rest one (same matrix on both, neither a
deformed spring: the static gate's case). By default (--exact-near) every pair
whose surfaces come within NEAR (~2 mm) goes to the exact boolean, and a pair
that never comes near has a vertex of each classified in the other exactly (no
box pre-test), closing the sampled test's blind spot for shallow (< ~0.6 mm)
interference and for thin parts wholly inside another. Samples: the static store.

Static mode (--static): EVERY pair of leaves at rest (same system too: a stud in
an undrilled boss is a violation), same prefilter and tests, grouped by system
pair.

Memory: oriented boxes of all prototypes come from a one-shot process (which
exits). Surface samples are built ONCE per STEP (+ sweep set) by a short-lived
build pool and saved as .npy under tmp/kin/gate_samples/<step sha256>/; workers
map them read-only (mmap_mode='r', shared page cache), build only their KD-trees,
decode a prototype only when it reaches the exact classifier / boolean, and drop
their trees above MEM_SOFT_MB. Default 2 workers (max 4); peak RSS (which counts
the shared mapped samples) and peak private footprint per worker are reported. A
worker exits when its parent dies (no orphans).
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import resource
import sys
import threading
import time
from pathlib import Path

import numpy as np

SRC = Path(__file__).resolve().parent.parent
ROOT = SRC.parent
DEFAULT_FILE = ROOT / "STEP" / "radial.step"

CLASH_MM3 = 0.5          # common volume above which a pair collides
INFLATE = 1.0            # mm: prefilter inflation per pair
MAX_WORKERS = 4
DEFAULT_WORKERS = 2
MEM_SOFT_MB = int(os.environ.get("GATE_MEM_SOFT_MB", 4500))       # a worker above this drops its mesh cache (then its sample caches)

CATEGORIES = ("piston-valve", "rod-rod", "rod-crankcase", "pushrod-fin", "piston-piston", "piston-barrel", "other")

# ---- surface-sample test ------------------------------------------------------------
# BRepExtrema distance on real castings takes seconds to MINUTES per pair, and a
# boolean against a finned barrel or head seconds, so a pair reaches the boolean
# only when surface samples say the bodies really interpenetrate:
#  * every prototype is meshed once (deflection MESH_DEFL; triangles oriented
#    outward from the solid);
#  * per pair, only the triangles inside the two bodies' overlapping boxes are
#    sampled, on a grid of pitch <= SAMPLE per triangle (with the triangle's
#    outward normal): every surface point is within E = SAMPLE + MESH_DEFL of a
#    sample;
#  * a sample p of one body whose nearest sample q of the other lies within
#    NEAR = 2 E + NEAR_TOL is in CONTACT range; its penetration depth is
#    -(p - q).n_q. Surfaces never within NEAR are apart (unless one body contains
#    the other: decided exactly by a point classifier). Depth under PEN_TOL both
#    ways is TOUCHING. A reading deeper than TRUST_DEPTH goes to the exact boolean;
#    a marginal one (PEN_TOL..TRUST_DEPTH) first has its deepest samples checked
#    with the exact solid classifier. The common volume the boolean measures is
#    what is reported.
#  * the grid emits a shared triangle corner (and a shared edge's points, when both
#    triangles grid it from the same end) once per triangle. Only the QUERY side is
#    deduplicated: each distinct position is queried once (bitwise-equal points get
#    bitwise-equal readings, so this changes no depth), while the KD-tree keeps every
#    copy with its own triangle normal, so the k-nearest neighbours - and the
#    SHALLOWEST-plane reading - are exactly those of the undeduplicated samples. Only
#    when the exact classifier is to vet a marginal reading are the DEEPEST samples
#    re-picked from every copy, so it checks exactly the points it always did.
# PEN_TOL is the test's resolution (sampling pitch on small fillet radii, mesh
# chord height): an interference shallower than PEN_TOL everywhere reads as
# contact. Kinematic clashes are millimetres deep.
MESH_DEFL = 0.05
SAMPLE = 1.0
NEAR_TOL = 0.05
E_SAMPLE = SAMPLE + MESH_DEFL
NEAR = 2 * E_SAMPLE + NEAR_TOL
PEN_TOL = 0.25
TRUST_DEPTH = 1.0    # a sample reading this deep always gets the boolean (the classifier only
                     # vets the marginal PEN_TOL..TRUST_DEPTH readings, where sampling error lives)


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------
def _trsf(W):
    from OCP.gp import gp_Trsf
    U, _, Vt = np.linalg.svd(W[:3, :3])          # re-orthonormalise (float noise -> exact rotation)
    R = U @ Vt
    tr = gp_Trsf()
    tr.SetValues(R[0, 0], R[0, 1], R[0, 2], W[0, 3],
                 R[1, 0], R[1, 1], R[1, 2], W[1, 3],
                 R[2, 0], R[2, 1], R[2, 2], W[2, 3])
    return tr


def _located(shape, W):
    from OCP.TopLoc import TopLoc_Location
    return shape if W is None else shape.Moved(TopLoc_Location(_trsf(W)))


def _loc_matrix(loc):
    M = np.eye(4)
    if loc is None:
        return M
    tr = loc.Transformation()
    for i in range(3):
        for j in range(4):
            M[i, j] = tr.Value(i + 1, j + 1)
    return M


def _obb(shape):
    """(centre, axes as columns, half sizes) of an oriented box around `shape`."""
    from OCP.Bnd import Bnd_OBB
    from OCP.BRepBndLib import BRepBndLib
    b = Bnd_OBB()
    BRepBndLib.AddOBB_s(shape, b, False, False, False)
    c = b.Center()
    A = np.array([[d.X(), d.Y(), d.Z()] for d in (b.XDirection(), b.YDirection(), b.ZDirection())]).T
    return np.array([c.X(), c.Y(), c.Z()]), A, np.array([b.XHSize(), b.YHSize(), b.ZHSize()])


def _obb_world(obb, W):
    c, A, h = obb
    if W is None:
        return obb
    return W[:3, :3] @ c + W[:3, 3], W[:3, :3] @ A, h


def _aabb_of_obb(obb):
    c, A, h = obb
    e = np.abs(A) @ h
    return np.concatenate([c - e, c + e])


def _obb_overlap(a, b, margin):
    """Separating-axis test for two oriented boxes, each inflated by margin/2."""
    ca, A, ha = a
    cb, B, hb = b
    ha = ha + margin / 2
    hb = hb + margin / 2
    R = A.T @ B
    t = A.T @ (cb - ca)
    AR = np.abs(R) + 1e-9
    for i in range(3):
        if abs(t[i]) > ha[i] + hb @ AR[i]:
            return False
    for j in range(3):
        if abs(t @ R[:, j]) > ha @ AR[:, j] + hb[j]:
            return False
    for i in range(3):
        for j in range(3):
            i1, i2 = (i + 1) % 3, (i + 2) % 3
            j1, j2 = (j + 1) % 3, (j + 2) % 3
            ra = ha[i1] * AR[i2, j] + ha[i2] * AR[i1, j]
            rb = hb[j1] * AR[i, j2] + hb[j2] * AR[i, j1]
            if abs(t[i2] * R[i1, j] - t[i1] * R[i2, j]) > ra + rb:
                return False
    return True


def _volume(shape):
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    p = GProp_GProps()
    BRepGProp.VolumeProperties_s(shape, p)
    return abs(p.Mass())


def _common_volume(a, b):
    """Boolean common volume; retried fuzzy; -1 when it cannot be decided."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.TopTools import TopTools_ListOfShape
    for fuzzy in (0.0, 1e-4):
        try:
            args, tools = TopTools_ListOfShape(), TopTools_ListOfShape()
            args.Append(a)
            tools.Append(b)
            op = BRepAlgoAPI_Common()
            op.SetArguments(args)
            op.SetTools(tools)
            op.SetRunParallel(False)
            if fuzzy:
                op.SetFuzzyValue(fuzzy)
            op.Build()
            if op.IsDone():
                return _volume(op.Shape())
        except Exception:
            pass
    return -1.0


def _any_inside(shape, points, tol):
    """Exact: is any world point inside a solid of shape by more than tol (classifier IN)?"""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    if not len(points):
        return False
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        c = BRepClass3d_SolidClassifier(ex.Current())
        for p in points:
            c.Perform(gp_Pnt(*map(float, p)), tol)
            if c.State() == TopAbs_IN:
                return True
        ex.Next()
    return False


def _inside(shape, p):
    """Exact: is world point p inside any solid of shape?"""
    from OCP.BRepClass3d import BRepClass3d_SolidClassifier
    from OCP.gp import gp_Pnt
    from OCP.TopAbs import TopAbs_IN, TopAbs_SOLID
    from OCP.TopExp import TopExp_Explorer
    ex = TopExp_Explorer(shape, TopAbs_SOLID)
    while ex.More():
        if BRepClass3d_SolidClassifier(ex.Current(), gp_Pnt(*map(float, p)), 1e-6).State() == TopAbs_IN:
            return True
        ex.Next()
    return False


def _spring_sweep(path, wire_d):
    """Solid spring: the wire circle swept along kin.spring_path segments."""
    from cadgen import build123d as bd
    edges = [bd.Bezier(*[bd.Vector(*p) for p in s["points"]]) for s in path["segments"]]
    wire = bd.Wire(edges)
    prof = bd.Plane(origin=edges[0].position_at(0), z_dir=edges[0].tangent_at(0)) * bd.Circle(wire_d / 2)
    return bd.sweep(bd.Face(bd.Wire(prof.edges())), path=wire, is_frenet=True).wrapped


def _mesh(shape):
    """Outward-oriented triangles of a shape in its own frame: (T (m,3,3), lo (m,3), hi (m,3))."""
    from OCP.BRep import BRep_Tool
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    BRepTools.Clean_s(shape)
    BRepMesh_IncrementalMesh(shape, MESH_DEFL, False, 0.35, True)
    tris = []
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        face = TopoDS.Face_s(ex.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is not None and tri.NbTriangles():
            tr = loc.Transformation()
            V = np.array([tri.Node(i).Transformed(tr).Coord() for i in range(1, tri.NbNodes() + 1)])
            F = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)], dtype=np.int64) - 1
            if face.Orientation() == TopAbs_REVERSED:
                F = F[:, ::-1]
            tris.append(V[F])
        ex.Next()
    BRepTools.Clean_s(shape)          # the OCC triangulation is no longer needed: free it
    if not tris:
        z = np.zeros((0, 3))
        return np.zeros((0, 3, 3)), z, z
    T = np.concatenate(tris).astype(np.float32)
    return T, T.min(axis=1), T.max(axis=1)


def _grid_samples(T):
    """Points on every triangle at pitch <= SAMPLE along both edges from its widest corner,
    with the triangle's unit normal: (P (n,3), N (n,3))."""
    T = T.astype(np.float64)
    ell = np.stack([np.linalg.norm(T[:, 1] - T[:, 2], axis=1), np.linalg.norm(T[:, 2] - T[:, 0], axis=1),
                    np.linalg.norm(T[:, 0] - T[:, 1], axis=1)], axis=1)
    k = np.argmax(ell, axis=1)                      # corner opposite the longest edge
    r = np.arange(len(T))
    O = T[r, k]
    U = T[r, (k + 1) % 3] - O
    W = T[r, (k + 2) % 3] - O
    Nf = np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0])
    nn = np.linalg.norm(Nf, axis=1)
    ok = nn > 1e-12
    Nf = Nf / np.where(ok, nn, 1.0)[:, None]
    n1 = np.clip(np.ceil(np.linalg.norm(U, axis=1) / SAMPLE), 1, 2000).astype(int)
    n2 = np.clip(np.ceil(np.linalg.norm(W, axis=1) / SAMPLE), 1, 2000).astype(int)
    Ps, Ns = [], []
    keys = n1 * 4096 + n2
    order = np.argsort(keys, kind="stable")
    bounds = np.flatnonzero(np.diff(keys[order])) + 1
    for grp in np.split(order, bounds):
        grp = grp[ok[grp]]
        if not len(grp):
            continue
        a, b = n1[grp[0]], n2[grp[0]]
        i, j = np.meshgrid(np.arange(a + 1), np.arange(b + 1), indexing="ij")
        s, t = (i / a).ravel(), (j / b).ravel()
        keep = s + t <= 1 + 1e-9
        s, t = s[keep], t[keep]
        P = O[grp][:, None, :] + s[None, :, None] * U[grp][:, None, :] + t[None, :, None] * W[grp][:, None, :]
        Ps.append(P.reshape(-1, 3))
        Ns.append(np.repeat(Nf[grp], len(s), axis=0))
    if not Ps:
        return np.zeros((0, 3)), np.zeros((0, 3))
    return np.concatenate(Ps), np.concatenate(Ns)


def _first_copy(P):
    """Mask: True at the first row (in array order) of every group of EXACTLY equal points.
    Only bitwise-equal coordinates collapse (never near ones)."""
    n = len(P)
    if n < 2:
        return np.ones(n, dtype=bool)
    o = np.lexsort((P[:, 2], P[:, 1], P[:, 0]))       # stable: equal rows keep array order
    S = P[o]
    new = np.empty(n, dtype=bool)
    new[0] = True
    np.any(S[1:] != S[:-1], axis=1, out=new[1:])
    F = np.zeros(n, dtype=bool)
    F[o[new]] = True
    return F


# ---------------------------------------------------------------------------
# The world
# ---------------------------------------------------------------------------
def leaf_records(scene):
    """One dict per geometry leaf: ref, label, owner (the leaf's own label, or for an
    unlabelled child of a nested compound the nearest '<group>:' ancestor label),
    system (the assembly's second-level occurrence label)."""
    out = []

    def walk(o, owner, system, depth):
        lab = o.label or ""
        if ":" in lab:
            owner = lab
        if depth == 1:
            system = lab
        if o._node.prototype_key is not None:
            out.append({"ref": o.ref, "label": lab, "owner": owner, "system": system or "?"})
        for c in o.children:
            walk(c, owner, system, depth + 1)

    for r in scene.roots:
        walk(r, "", "", 0)
    return out


class World:
    """Leaves of the built assembly; prototypes decode lazily (only candidates ever do)."""

    def __init__(self, step_file):
        from cadgen import read_scene
        from lib import clips
        self.scene = read_scene(step_file)
        self._protos = self.scene._loaded.prototype_shapes
        occ = self.scene._occurrences
        self.leaves = []
        for r in leaf_records(self.scene):
            node = occ[r["ref"]]._node
            kind, args = clips.classify_leaf(r["label"], r["owner"])
            self.leaves.append({
                "ref": r["ref"], "system": r["system"], "proto": node.prototype_key,
                "label": r["label"] if (":" in r["label"] or not r["owner"]) else f'{r["owner"]}/{r["label"]}',
                "L": _loc_matrix(node.location), "kind": kind, "args": args,
                "group": r["label"].split(":", 1)[0] if kind not in ("static", "suspect") else None,
            })

    def proto(self, key):
        return self._protos[key]


def _obb_table(step_file):
    """One-shot (runs in its own process, which then exits and frees every decoded prototype)."""
    sys.path.insert(0, str(SRC))
    w = World(step_file)
    out = {}
    for lf in w.leaves:
        if lf["proto"] not in out:
            c, A, h = _obb(w.proto(lf["proto"]))
            out[lf["proto"]] = (c.tolist(), A.tolist(), h.tolist())
    return out


def _category(a, b):
    ka, kb = a["kind"], b["kind"]
    if {ka, kb} == {"piston", "valve"}:
        return "piston-valve"
    rod = {"master", "artrod"}
    if ka in rod and kb in rod:
        return "rod-rod"
    if ka == kb == "piston":
        return "piston-piston"
    for x, y in ((a, b), (b, a)):
        stat = y["kind"] == "static"
        pre = y["label"].split(":", 1)[0]
        if x["kind"] in rod and stat and (y["system"] == "crankcase" or pre == "crankcase"):
            return "rod-crankcase"
        if x["kind"] == "pushrod" and stat and (y["system"] in ("barrels", "heads") or pre in ("barrels", "heads", "pushrods")):
            return "pushrod-fin"
        if x["kind"] == "piston" and stat and (y["system"] == "barrels" or pre == "barrels"):
            return "piston-barrel"
    return "other"


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------
_W = {}


def _rss_mb():
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return r / (1024 * 1024) if sys.platform == "darwin" else r / 1024


def _cur_rss_mb():
    try:
        import psutil
        return psutil.Process().memory_info().rss / (1024 * 1024)
    except Exception:
        return _rss_mb()


def _watch_parent(ppid):
    while True:
        time.sleep(2.0)
        if os.getppid() != ppid:
            os._exit(3)


_TASK_INFO = []


def _footprint_mb():
    """(current, peak) private physical footprint in MB (macOS task ledger: excludes the clean
    read-only mapped sample files, which RSS counts); (None, None) where unavailable."""
    if sys.platform != "darwin":
        return None, None
    try:
        if not _TASK_INFO:
            import ctypes
            import ctypes.util

            class _VM(ctypes.Structure):
                _fields_ = ([("virtual_size", ctypes.c_uint64), ("region_count", ctypes.c_int32),
                             ("page_size", ctypes.c_int32)]
                            + [(n, ctypes.c_uint64) for n in (
                                "resident_size", "resident_size_peak", "device", "device_peak", "internal",
                                "internal_peak", "external", "external_peak", "reusable", "reusable_peak",
                                "purgeable_volatile_pmap", "purgeable_volatile_resident",
                                "purgeable_volatile_virtual", "compressed", "compressed_peak",
                                "compressed_lifetime", "phys_footprint", "min_address", "max_address")]
                            + [("ledger_phys_footprint_peak", ctypes.c_int64), ("_pad", ctypes.c_uint64 * 32)])
            libc = ctypes.CDLL(ctypes.util.find_library("c"))
            libc.mach_task_self.restype = ctypes.c_uint32
            _TASK_INFO.extend([ctypes, libc, _VM])
        ctypes, libc, _VM = _TASK_INFO
        info, count = _VM(), ctypes.c_uint32(ctypes.sizeof(_VM) // 4)
        if libc.task_info(libc.mach_task_self(), 22, ctypes.byref(info), ctypes.byref(count)) != 0:   # TASK_VM_INFO
            return None, None
        return info.phys_footprint / 2**20, info.ledger_phys_footprint_peak / 2**20
    except Exception:
        return None, None


def _mem_mb():
    """Memory that counts against MEM_SOFT_MB: private footprint (mapped samples are shared)."""
    cur = _footprint_mb()[0]
    return cur if cur is not None else _cur_rss_mb()


def _init(step_file, obbs, ppid, sweeps=None, store=None, exact_near=False):
    sys.path.insert(0, str(SRC))
    _W["exact_near"] = exact_near
    threading.Thread(target=_watch_parent, args=(ppid,), daemon=True).start()
    t0 = time.time()
    _W["world"] = World(step_file)
    _W["obbs"] = {k: (np.array(c), np.array(A), np.array(h)) for k, (c, A, h) in obbs.items()}
    _W["store"] = _open_store(store) if store else None
    _W["cache"] = {}
    _W["springs"] = {}
    _W["meshes"] = {}
    _W["psamples"] = {}
    _W["lsamples"] = {}
    _W["fsamples"] = {}
    _W["pairpts"] = {}
    _W["pairpts_mb"] = 0.0
    _W["sweeps"] = np.array(sweeps if sweeps is not None else np.zeros((0, 6)), dtype=float).reshape(-1, 6)
    movers = [lf["label"] for lf in _W["world"].leaves if lf["kind"] not in ("static", "suspect")]
    _W["sweep_of"] = dict(zip(movers, _W["sweeps"])) if len(movers) == len(_W["sweeps"]) else {}
    _W["t_mesh"] = _W["t_sample"] = _W["t_common"] = 0.0
    _W["slow"] = []
    _W["drops"] = 0
    _W["confirm"] = 0
    _W["init_s"] = time.time() - t0


def _drop_sample_caches():
    _W["pairpts"].clear()
    _W["pairpts_mb"] = 0.0
    _W["springs"].clear()
    _W["psamples"].clear()
    _W["lsamples"].clear()
    _W["fsamples"].clear()


def _mem_guard():
    """Above MEM_SOFT_MB (private footprint) drop the mesh cache first, then the sample caches
    (KD-trees; the mapped samples themselves are shared page cache)."""
    if _mem_mb() > MEM_SOFT_MB:
        if _W["meshes"]:
            _W["meshes"].clear()
        else:
            _drop_sample_caches()
        _W["drops"] += 1


def _proto_mesh(key):
    cache = _W["meshes"]
    if key not in cache:
        _mem_guard()
        t0 = time.time()
        cache[key] = _mesh(_W["world"].proto(key))
        _W["t_mesh"] += time.time() - t0
    return cache[key]


class Body:
    """A shape at world placement W (None = already world), its world box, and a sampler
    box -> (world points, world outward normals, first-copy mask) of its surface inside that box.
    A sampler of a body with a cached KD-tree returns (DISTINCT world points, None, None): its
    surface side is answered by the tree."""
    __slots__ = ("shape", "W", "mesh_fn", "key", "box", "sampler", "cache", "frame", "obb", "first", "lid")

    def __init__(self, shape, W, mesh_fn, key, box, sampler=None, cache=None, frame=None, obb=None, first=None,
                 lid=None):
        self.obb = obb
        self.lid = lid            # the leaf's label (kinematic mode)
        self.shape, self.W, self.mesh_fn, self.key, self.box = shape, W, mesh_fn, key, box
        self.sampler = sampler
        self.cache = cache        # (P, N, KD-tree, distinct P) of cached samples in `frame` (None = world)
        self.frame = frame
        self.first = first        # () -> first mesh vertex in the shape's own frame (float32), None if no mesh

    def mesh(self):
        return self.mesh_fn()

    def samples(self, box, other=None):
        return self.sampler(box, other)

    def world_shape(self):
        # a leaf's prototype decodes only when an exact test needs it
        return _located(self.shape() if callable(self.shape) else self.shape, self.W)

    def M(self):
        return np.eye(4) if self.W is None else self.W


def _box_in_frame(box, M):
    """AABB, in the frame whose world placement is M, of world box [lo, hi]."""
    inv = np.linalg.inv(M)
    c = np.array([[x, y, z] for x in (box[0], box[3]) for y in (box[1], box[4]) for z in (box[2], box[5])])
    lc = c @ inv[:3, :3].T + inv[:3, 3]
    return lc.min(axis=0), lc.max(axis=0)


def _select(P, M, box):
    """World points of cached frame points P (float64, sorted by x) placed at M, inside world box."""
    if not len(P):
        return np.zeros((0, 3))
    lo, hi = _box_in_frame(box, M) if M is not None else (box[:3], box[3:])
    i0, i1 = np.searchsorted(P[:, 0], lo[0], "left"), np.searchsorted(P[:, 0], hi[0], "right")
    P = np.asarray(P[i0:i1])
    P = P[(P[:, 1] >= lo[1]) & (P[:, 1] <= hi[1]) & (P[:, 2] >= lo[2]) & (P[:, 2] <= hi[2])]  # a float64 copy: no recast
    if M is not None:
        P = P @ M[:3, :3].T + M[:3, 3]
    return P[np.all(P >= box[:3], axis=1) & np.all(P <= box[3:], axis=1)]


def _select_full(samples, M, box):
    """World (points, normals, first-copy mask) of a prototype's whole-surface samples (P, N, F, R;
    sorted by x, R = grid order) placed at M, inside world box - in GRID order, i.e. exactly the
    arrays sampling only the triangles that overlap the box produced (a per-pair KD-tree over
    them is then the same tree)."""
    P, N, F, R = samples
    if not len(P):
        return np.zeros((0, 3)), np.zeros((0, 3)), np.zeros(0, dtype=bool)
    lo, hi = _box_in_frame(box, M)
    i0, i1 = np.searchsorted(P[:, 0], lo[0], "left"), np.searchsorted(P[:, 0], hi[0], "right")
    S = np.asarray(P[i0:i1])
    m = (S[:, 1] >= lo[1]) & (S[:, 1] <= hi[1]) & (S[:, 2] >= lo[2]) & (S[:, 2] <= hi[2])
    idx = np.flatnonzero(m) + i0
    Pw = S[m] @ M[:3, :3].T + M[:3, 3]
    keep = np.all(Pw >= box[:3], axis=1) & np.all(Pw <= box[3:], axis=1)
    idx = idx[keep]
    o = np.argsort(np.asarray(R[idx]), kind="stable")
    idx = idx[o]
    return Pw[keep][o], np.asarray(N[idx]) @ M[:3, :3].T, np.asarray(F[idx])


def _pack(P, N):
    """Cached samples: (P sorted by x, N (float32), KD-tree over P, DISTINCT points of P in that order)."""
    from scipy.spatial import cKDTree
    if not len(P):
        return P, N.astype(np.float32), None, P
    o = np.argsort(P[:, 0], kind="stable")
    P = np.ascontiguousarray(P[o])
    return P, np.ascontiguousarray(N[o]).astype(np.float32), cKDTree(P), np.ascontiguousarray(P[_first_copy(P)])


def _region_hit(key):
    """Can some moving part's swept box (padded) reach any leaf using this prototype?"""
    sw = _W["sweeps"]
    pad = NEAR + INFLATE
    for lf in _W["world"].leaves:
        if lf["proto"] != key:
            continue
        box = _aabb_of_obb(_obb_world(_W["obbs"][key], lf["L"]))
        if np.any(np.all(sw[:, :3] - pad <= box[3:], axis=1) & np.all(sw[:, 3:] + pad >= box[:3], axis=1)):
            return True
    return False


def _region_mask(key, tlo, thi):
    """Triangles of a STATIC prototype some moving part's swept box can reach, over every leaf using it."""
    sw = _W["sweeps"]
    pad = NEAR + INFLATE
    sel = np.zeros(len(tlo), dtype=bool)
    for lf in _W["world"].leaves:
        if lf["proto"] != key:
            continue
        box = _aabb_of_obb(_obb_world(_W["obbs"][key], lf["L"]))
        hit = sw[np.all(sw[:, :3] - pad <= box[3:], axis=1) & np.all(sw[:, 3:] + pad >= box[:3], axis=1)]
        for b in hit:
            lo, hi = _box_in_frame(np.concatenate([b[:3] - pad, b[3:] + pad]), lf["L"])
            sel |= np.all(tlo <= hi, axis=1) & np.all(thi >= lo, axis=1)
    return sel


def _kin_samples(role, key, cache):
    """(P, N, KD-tree, distinct P) of a prototype in its own frame: role "m" = whole surface of a
    moving prototype, "s" = a static prototype only where motion can reach it. From the shared
    store (mapped read-only) when there is one, else built here; cached per prototype."""
    if key not in cache:
        from scipy.spatial import cKDTree
        _mem_guard()
        got = _store_arrays(role, key)
        t0 = time.time()
        if got is not None:
            P = got["P"]
            cache[key] = (P, got["N"], cKDTree(P) if len(P) else None, got["U"])
        else:
            T, tlo, thi = _proto_mesh(key)
            t0 = time.time()
            if role == "s":
                sel = _region_mask(key, tlo, thi)
                T = T[sel] if sel.any() else None
            cache[key] = _pack(*(_grid_samples(T) if T is not None else (np.zeros((0, 3)), np.zeros((0, 3)))))
        _W["t_sample"] += time.time() - t0
    return cache[key]


def _proto_samples(key):
    """Whole-surface samples of a (moving) prototype in its own frame, cached."""
    return _kin_samples("m", key, _W["psamples"])


def _static_samples(key):
    """Samples of a STATIC prototype in its own frame, only where some moving part's swept box
    can reach any of the leaves that use it; cached per prototype (shared by its copies)."""
    return _kin_samples("s", key, _W["lsamples"])


def _full_arrays(T):
    """Whole-surface (P, N float64, first-copy mask, grid order) sorted by x (static mode)."""
    P, N = _grid_samples(T)
    o = np.argsort(P[:, 0], kind="stable")
    P = np.ascontiguousarray(P[o])
    return P, np.ascontiguousarray(N[o]), _first_copy(P), o.astype(np.int32)


def _full_samples(key):
    """Static mode: a prototype's whole-surface samples, sampled once per prototype (not per pair)."""
    cache = _W["fsamples"]
    if key not in cache:
        got = _store_arrays("f", key)
        t0 = time.time()
        if got is not None:
            cache[key] = (got["P"], got["N"], got["F"], got["R"])
        else:
            T = _proto_mesh(key)[0]
            t0 = time.time()
            cache[key] = _full_arrays(T)
        _W["t_sample"] += time.time() - t0
    return cache[key]


def _first_vertex(key):
    st = _W.get("store")
    if st is not None and str(key) in st["first"]:
        v = st["first"][str(key)]
        return None if v is None else np.array(v, dtype=np.float32)
    T = _proto_mesh(key)[0]
    return T[0, 0] if len(T) else None


def _in_obb(P, obb):
    """Mask of the points within NEAR of an oriented box."""
    if obb is None or not len(P):
        return np.ones(len(P), dtype=bool)
    c, A, h = obb
    L = np.abs((P - c) @ A)
    return np.all(L <= h + NEAR, axis=1)


def _side(body, box, other):
    """(DISTINCT world sample points of body in box within NEAR of obb - the depth queries,
    the full (P, N) surface there for a body without a cached tree, else None)."""
    P, N, F = body.samples(box, other)
    m = _in_obb(P, other.obb)
    if F is None:
        return P[m], None
    P, N, F = P[m], N[m], F[m]
    return P[F], (P, N)


def _all_copies(body, box, obb, surf):
    """Every sample (duplicates included, sample order) of body in box within NEAR of obb."""
    if surf is not None:
        return surf[0]
    if body.cache is None:
        return np.zeros((0, 3))
    P = _select(body.cache[0], body.frame, box)
    return P[_in_obb(P, obb)]


def _depth_into(P, body, surf, deepest=True):
    """_depth of world points P under `body`: its cached KD-tree when it has one, else its surface
    samples surf = (Q, NQ)."""
    if body.cache is None:
        return None if surf is None else _depth(P, *surf, deepest=deepest)
    if not len(P):
        return None
    Pc, Nc, tree = body.cache[:3]
    if body.frame is not None:
        inv = np.linalg.inv(body.frame)
        P = P @ inv[:3, :3].T + inv[:3, 3]
    return _depth(P, Pc, Nc, tree, deepest=deepest)


DEEPEST = 24     # samples checked with the exact classifier before a boolean is spent
SPRING_CACHE_MAX = 108  # deformed-spring sweeps kept per worker (3 angles x 36 leaves)


def _depth(P, Q, NQ, tree=None, deepest=True):
    """(max penetration, indices into P of the DEEPEST points - None unless `deepest`) of points P
    under the surface sampled by (Q, NQ); None if P never comes NEAR."""
    from scipy.spatial import cKDTree
    if not len(P) or not len(Q):
        return None
    tree = tree or cKDTree(Q)
    d1, i1 = tree.query(P, k=1, distance_upper_bound=NEAR)
    keep = np.flatnonzero(np.isfinite(d1))
    P = P[keep]
    if not len(P):
        return None
    # depth under the NEAREST sample's tangent plane first: the k-nearest minimum below can
    # only be shallower, so a point reading <= PEN_TOL here can never count, and the
    # (costly) k=4 query runs only for the few points that might
    i1 = i1[keep]
    dep = -np.einsum("pj,pj->p", P - Q[i1], NQ[i1].astype(np.float64))
    hot = np.flatnonzero(dep > PEN_TOL)
    if len(hot):
        k = min(4, len(Q))
        d, idx = tree.query(P[hot], k=k, distance_upper_bound=NEAR)
        d, idx = d.reshape(len(hot), k), idx.reshape(len(hot), k)
        ok = np.isfinite(d)
        # each point's depth under each of its k nearest samples' tangent planes; the
        # SHALLOWEST reading counts (an edge sample's plane must not invent a penetration)
        j = np.where(ok, idx, 0)
        dk = -np.einsum("pkj,pkj->pk", P[hot][:, None, :] - Q[j], NQ[j].astype(np.float64))
        dep[hot] = np.where(ok, dk, np.inf).min(axis=1)
    if not deepest:
        return float(dep.max()), None
    top = np.argsort(dep)[::-1][:DEEPEST]
    top = top[dep[top] > PEN_TOL]
    return float(dep.max()), keep[top]


def _contains(outer, inner):
    """inner's box inside outer's, and a point of inner inside outer's solid (exact)."""
    if not (np.all(inner.box[:3] >= outer.box[:3]) and np.all(inner.box[3:] <= outer.box[3:])):
        return False
    p = inner.first()
    if p is None:
        return False
    M = inner.M()
    return _inside(outer.world_shape(), M[:3, :3] @ p.astype(float) + M[:3, 3])


def _vertex_inside(outer, inner):
    """Exact: is a vertex of inner inside outer's solid (no box pre-test)?"""
    p = inner.first()
    if p is None:
        return False
    M = inner.M()
    return _inside(outer.world_shape(), M[:3, :3] @ p.astype(float) + M[:3, 3])


def _pair_test(a, b, key, names):
    """Common volume of bodies a and b (0 when apart or merely touching), memoised on `key`.
    Returns (volume, from_cache, went_to_boolean)."""
    cache = _W["cache"]
    if key in cache:
        return cache[key], True, False
    t0 = time.time()
    depth = None
    box = np.concatenate([np.maximum(a.box[:3], b.box[:3]) - NEAR, np.minimum(a.box[3:], b.box[3:]) + NEAR])
    exact = False
    if np.all(box[:3] <= box[3:]):
        PA, SA = _side(a, box, b)
        PB, SB = _side(b, box, a)
        ra, rb = _depth_into(PA, b, SB, False), _depth_into(PB, a, SA, False)
        if ra is None and rb is None:
            exact = _contains(a, b) or _contains(b, a)
            if not exact and _W.get("exact_near"):
                # no box pre-test: a thin part wholly inside another, whatever the boxes say
                exact = _vertex_inside(a, b) or _vertex_inside(b, a)
        elif _W.get("exact_near"):
            # --exact-near: every pair whose surfaces come within NEAR (~2 mm) gets the exact
            # boolean, so interference shallower than the sampling's PEN_TOL cannot pass unseen
            depth = max(r[0] for r in (ra, rb) if r is not None)
            exact = True
            _W["confirm"] += 1
        else:
            depth = max(r[0] for r in (ra, rb) if r is not None)
            # the classifier vets the DEEPEST samples of a side reading deeper than PEN_TOL (a side
            # reading no deeper has none): pick them from every copy, in the undeduplicated order
            # (same array -> same argsort), so it checks exactly the points it always did
            if PEN_TOL < depth <= TRUST_DEPTH:
                PA = _all_copies(a, box, b.obb, SA) if ra is not None and ra[0] > PEN_TOL else None
                PB = _all_copies(b, box, a.obb, SB) if rb is not None and rb[0] > PEN_TOL else None
                ra = None if PA is None else _depth_into(PA, b, SB)
                rb = None if PB is None else _depth_into(PB, a, SA)
            # samples reading deeper than PEN_TOL: confirm with the EXACT classifier before a boolean
            exact = depth > PEN_TOL and (
                depth > TRUST_DEPTH
                or (ra is not None and _any_inside(b.world_shape(), PA[ra[1]], PEN_TOL / 2))
                or (rb is not None and _any_inside(a.world_shape(), PB[rb[1]], PEN_TOL / 2)))
            _W["confirm"] += depth > PEN_TOL
    t1 = time.time()
    v = _common_volume(a.world_shape(), b.world_shape()) if exact else 0.0
    t2 = time.time()
    _W["t_sample"] += t1 - t0
    _W["t_common"] += t2 - t1
    if exact:
        _W["slow"].append((round(t2 - t1, 2), names[0], names[1], None if depth is None else round(depth, 3), round(v, 2)))
    cache[key] = v
    return v, False, exact


def _key(A, B):
    if A.W is not None and B.W is not None:
        rel = np.linalg.inv(A.W) @ B.W
        return (A.key, B.key, tuple(np.round(rel[:3, :], 5).ravel().tolist()))
    return (A.key, B.key, tuple(np.round(A.M()[:3, :], 5).ravel()), tuple(np.round(B.M()[:3, :], 5).ravel()))


def _no_samples(box, other=None):
    return np.zeros((0, 3)), None, None


PAIR_CACHE_MB = int(os.environ.get("GATE_PAIR_CACHE_MB", 500))    # per worker
PAIR_ENTRY_MB = 8.0      # a pair whose static points exceed this keeps using _select


def _static_points(c, W, box, lid, jbox, other):
    """Distinct world sample points of a STATIC leaf (prototype samples c placed at W) inside world
    box, for the pair with moving leaf `other`. The static leaf never moves, so its points inside
    the mover's swept box (+ NEAR) are placed in the world once per pair and kept sorted by world x;
    every later angle only slices them - the same points _select finds (their order differs, which
    no depth reading depends on). Falls back to _select when a box leaves that region."""
    sw = _W.get("sweep_of", {}).get(other.lid)
    if sw is None:
        return _select(c[3], W, box)
    pc = _W["pairpts"]
    ent = pc.get((lid, other.lid))
    if ent is None:
        R = np.concatenate([np.maximum(sw[:3], jbox[:3]) - NEAR, np.minimum(sw[3:], jbox[3:]) + NEAR])
        S = _select(c[3], W, R) if np.all(R[:3] <= R[3:]) else np.zeros((0, 3))
        S = np.ascontiguousarray(S[np.argsort(S[:, 0], kind="stable")])
        if S.nbytes / 2**20 > PAIR_ENTRY_MB or _W["pairpts_mb"] + S.nbytes / 2**20 > PAIR_CACHE_MB:
            pc[(lid, other.lid)] = (R, None)             # remember not to rebuild it
            return _select(c[3], W, box)
        _W["pairpts_mb"] += S.nbytes / 2**20
        ent = pc[(lid, other.lid)] = (R, S)
    R, S = ent
    if S is None or not (np.all(box[:3] >= R[:3]) and np.all(box[3:] <= R[3:])):
        return _select(c[3], W, box)
    S = S[np.searchsorted(S[:, 0], box[0], "left"):np.searchsorted(S[:, 0], box[3], "right")]
    return S[(S[:, 1] >= box[1]) & (S[:, 1] <= box[4]) & (S[:, 2] >= box[2]) & (S[:, 2] <= box[5])]


def _rigid_body(leaf, W, i=None):
    """Body of a leaf at W. Kinematic mode passes i: moving leaves sample their whole
    (small) prototype once; static leaves sample only where motion can reach them.
    Static mode samples each prototype's whole surface once and selects per pair."""
    key = leaf["proto"]
    obb = _obb_world(_W["obbs"][key], W)
    shape, mesh, first = (lambda: _W["world"].proto(key)), (lambda: _proto_mesh(key)), (lambda: _first_vertex(key))
    box, lid = _aabb_of_obb(obb), leaf["label"]
    if i is not None:
        static = leaf["kind"] in ("static", "suspect")
        c = _static_samples(key) if static else _proto_samples(key)
        if c[2] is None:
            return Body(shape, W, mesh, key, box, _no_samples, frame=W, obb=obb, first=first, lid=lid)
        if static and W is leaf["L"]:
            sampler = (lambda bx, other: (_static_points(c, W, bx, lid, box, other), None, None))
        else:
            sampler = (lambda bx, other: (_select(c[3], W, bx), None, None))
        return Body(shape, W, mesh, key, box, sampler, cache=c, frame=W, obb=obb, first=first, lid=lid)
    fs = _full_samples(key)
    return Body(shape, W, mesh, key, box, lambda bx, other: _select_full(fs, W, bx), obb=obb, first=first, lid=lid)


def _spring_body(leaf, theta):
    """A spring leaf at theta: (None, obb) when undeformed (the STEP body), else (swept Body, obb)."""
    from lib import kin
    k, v, which = leaf["args"]
    vl, vl0 = kin.valve_lift(theta, k, v), kin.valve_lift(0.0, k, v)
    if abs(vl - vl0) < 1e-9:
        return None, _obb_world(_W["obbs"][leaf["proto"]], leaf["L"])
    skey = (leaf["label"], round(vl, 9))
    if skey not in _W["springs"]:
        # bounded: lifts rarely repeat except at an angle's +360 twin, so keep ~2 angles' worth
        # (36 spring leaves each) and drop the oldest instead of growing to GBs
        while len(_W["springs"]) >= SPRING_CACHE_MAX:
            _W["springs"].pop(next(iter(_W["springs"])))
        shape = _spring_sweep(kin.spring_path(theta, k, v, which), kin.SPRINGS[which][1])
        mesh = _mesh(shape)
        _W["springs"][skey] = (shape, mesh, _obb(shape), _pack(*_grid_samples(mesh[0])))
    shape, mesh, obb, smp = _W["springs"][skey]
    first = (lambda: mesh[0][0, 0] if len(mesh[0]) else None)
    if smp[2] is None:
        return Body(shape, None, lambda: mesh, skey, _aabb_of_obb(obb), _no_samples, obb=obb, first=first,
                    lid=leaf["label"]), obb
    return Body(shape, None, lambda: mesh, skey, _aabb_of_obb(obb), lambda bx, other: (_select(smp[3], None, bx), None, None),
                cache=smp, frame=None, obb=obb, first=first, lid=leaf["label"]), obb


def _cache_mb():
    """Private MB held by the caches (mapped store arrays are shared page cache: reported apart)."""
    def nb(x, mapped=False):
        if isinstance(x, np.ndarray):
            m = isinstance(x, np.memmap) or isinstance(x.base, np.memmap) or (x.base is not None and type(x.base).__name__ == "mmap")
            return x.nbytes if m == mapped else 0
        if isinstance(x, (tuple, list)):
            return sum(nb(y, mapped) for y in x)
        if hasattr(x, "data") and hasattr(x, "query"):      # KD-tree: its point index (+ its data if private)
            return 0 if mapped else x.indices.nbytes + nb(x.data)
        return 0
    out = {}
    for name in ("meshes", "psamples", "lsamples", "fsamples"):
        out[name] = round(sum(nb(v) for v in _W[name].values()) / 2**20)
    out["mapped"] = round(sum(nb(v, True) for name in ("psamples", "lsamples", "fsamples") for v in _W[name].values()) / 2**20)
    out["springs"] = round(sum(nb(v[1]) + nb(v[3]) for v in _W["springs"].values()) / 2**20)
    out["pair_points"] = round(_W["pairpts_mb"])
    big = sorted(((nb(v) / 2**20, k) for k, v in _W["meshes"].items()), reverse=True)[:3]
    out["biggest_meshes"] = [(round(m), _proto_label(k)) for m, k in big]
    return out


def _proto_label(key):
    for lf in _W["world"].leaves:
        if lf["proto"] == key:
            return lf["label"]
    return str(key)


def _profile():
    return {"cache_mb": _cache_mb(), "classifier_checks": _W["confirm"], "mesh_s": round(_W["t_mesh"], 1), "sample_s": round(_W["t_sample"], 1),
            "boolean_s": round(_W["t_common"], 1), "booleans": len(_W["slow"]), "cache_drops": _W["drops"],
            "slowest": sorted(_W["slow"], reverse=True)[:6]}


def _scan(leaves, placements, obbs, movers, skip, category, kinematic=False):
    """Shared candidate loop. placements[i]: a W matrix or a ready Body."""
    boxes = np.array([_aabb_of_obb(o) for o in obbs])
    bodies = {}

    def body(i):
        if i not in bodies:
            p = placements[i]
            bodies[i] = p if isinstance(p, Body) else _rigid_body(leaves[i], p, i if kinematic else None)
        return bodies[i]

    clashes, unknown, exact_pairs = [], [], []
    n_cand = n_exact = n_cached = 0
    for i in movers:
        lo, hi = boxes[i, :3] - INFLATE, boxes[i, 3:] + INFLATE
        for j in np.nonzero(np.all(boxes[:, :3] <= hi, axis=1) & np.all(boxes[:, 3:] >= lo, axis=1))[0]:
            j = int(j)
            if skip(i, j) or not _obb_overlap(obbs[i], obbs[j], INFLATE):
                continue
            n_cand += 1
            A, B = body(i), body(j)
            a, b = leaves[i], leaves[j]
            vol, cached, exact = _pair_test(A, B, _key(A, B), (a["label"], b["label"]))
            n_cached += cached
            n_exact += exact
            if exact:
                exact_pairs.append((a["label"], b["label"], round(vol, 3)))
            if vol > CLASH_MM3:
                clashes.append((category(a, b), a["label"], b["label"], round(vol, 3)))
            elif vol < 0:
                unknown.append((category(a, b), a["label"], b["label"]))
    _W["exact_pairs"] = exact_pairs          # which pairs reached the boolean (reported per task)
    return clashes, unknown, n_cand, n_exact, n_cached


def _kin_group_task(group):
    """One angle and its +360 twins, in order, on this worker."""
    return [_kin_task(t) for t in group]


def _kin_task(task):
    theta, mats = task
    leaves = _W["world"].leaves
    t0 = time.time()
    placements, obbs, moving = [None] * len(leaves), [None] * len(leaves), []
    for i, lf in enumerate(leaves):
        if lf["kind"] == "spring":
            b, obbs[i] = _spring_body(lf, theta)
            placements[i] = b if b is not None else lf["L"]
            moving.append(i)
            continue
        M = mats.get(lf["label"])
        W = lf["L"] if M is None else np.asarray(M) @ lf["L"]
        placements[i] = W
        obbs[i] = _obb_world(_W["obbs"][lf["proto"]], W)
        if lf["kind"] not in ("static", "suspect"):
            moving.append(i)
    mv = set(moving)

    def skip(i, j):
        g = leaves[j]["group"]
        return j == i or (j in mv and j < i) or (g is not None and g == leaves[i]["group"])

    clashes, unknown, n_cand, n_exact, n_cached = _scan(leaves, placements, obbs, moving, skip, _category,
                                                        kinematic=True)
    return {"theta": theta, "clashes": clashes, "unknown": unknown, "candidates": n_cand, "exact": n_exact,
            "cached": n_cached, "seconds": time.time() - t0, "rss_mb": _rss_mb(), "footprint_mb": _footprint_mb()[1],
            "pid": os.getpid(),
            "init_s": _W["init_s"], "profile": _profile(), "exact_pairs": _W["exact_pairs"]}


def _static_task(task):
    stripe, nstripes = task
    leaves = _W["world"].leaves
    t0 = time.time()
    placements = [lf["L"] for lf in leaves]
    obbs = [_obb_world(_W["obbs"][lf["proto"]], lf["L"]) for lf in leaves]

    def skip(i, j):
        return j <= i

    def sys_pair(a, b):
        return " x ".join(sorted((a["system"], b["system"])))

    clashes, unknown, n_cand, n_exact, _ = _scan(leaves, placements, obbs, range(stripe, len(leaves), nstripes),
                                                 skip, sys_pair)
    return {"stripe": stripe, "clashes": clashes, "unknown": unknown, "candidates": n_cand, "exact": n_exact,
            "seconds": time.time() - t0, "rss_mb": _rss_mb(), "footprint_mb": _footprint_mb()[1], "pid": os.getpid(),
            "init_s": _W["init_s"],
            "profile": _profile(), "exact_pairs": _W["exact_pairs"]}


XR_CATEGORIES = ("crank-train", "cylinders", "nose-stack", "rear-stack", "between-groups")


def _xr_kind(group):
    if group == "core":
        return "crank-train"
    if group.startswith(("cyl", "cover")):
        return "cylinders"
    return "nose-stack" if group in ("front_half", "cam", "nose", "prop") else "rear-stack"


def _xr_category(a, b):
    return _xr_kind(a["xr"]) if a["xr"] == b["xr"] else "between-groups"


def _xr_spring_body(leaf, theta, M):
    """A spring at theta (kin.spring_path, as the viewer deforms it) moved by its offset M."""
    b, obb = _spring_body(leaf, theta)
    if b is None:
        return None
    shape, mesh, sobb, smp = _W["springs"][b.key]
    obb = _obb_world(sobb, M)
    if smp[2] is None:
        return Body(shape, M, lambda: mesh, b.key, _aabb_of_obb(obb), _no_samples, obb=obb, first=b.first,
                    lid=b.lid)
    return Body(shape, M, lambda: mesh, b.key, _aabb_of_obb(obb),
                lambda bx, other: (_select(smp[3], M, bx), None, None),
                cache=smp, frame=M, obb=obb, first=b.first, lid=b.lid)


def _xr_group_task(group):
    return [_xr_task(t) for t in group]


def _xr_task(task):
    """exploded-running at one crank angle: every VISIBLE leaf placed by the clip's matrix
    (running motion + constant offset). A pair is tested unless its relative placement is the
    rest one (both leaves carry the same matrix, neither a deformed spring: the static gate's
    case); hidden leaves are not in the picture and are skipped."""
    theta, mats, hidden, groups = task
    hidden = set(hidden)
    leaves = _W["world"].leaves
    t0 = time.time()
    n = len(leaves)
    placements, obbs, mkey, deformed, vis = [None] * n, [None] * n, [None] * n, [False] * n, []
    for i, lf in enumerate(leaves):
        lf["xr"] = groups.get(lf["label"], "hidden")
        M = mats.get(lf["label"])
        M = np.eye(4) if M is None else np.asarray(M)
        mkey[i] = tuple(np.round(M[:3, :], 7).ravel().tolist())
        body = _xr_spring_body(lf, theta, M) if lf["kind"] == "spring" else None
        if body is not None:
            placements[i], obbs[i], deformed[i] = body, body.obb, True
        else:
            W = M @ lf["L"]
            placements[i] = W
            obbs[i] = _obb_world(_W["obbs"][lf["proto"]], W)
        if lf["label"] not in hidden:
            vis.append(i)
    visible = set(vis)

    def skip(i, j):
        return (j <= i or j not in visible
                or (not deformed[i] and not deformed[j] and mkey[i] == mkey[j]))

    clashes, unknown, n_cand, n_exact, n_cached = _scan(leaves, placements, obbs, vis, skip, _xr_category)
    return {"theta": theta, "clashes": clashes, "unknown": unknown, "candidates": n_cand, "exact": n_exact,
            "cached": n_cached, "seconds": time.time() - t0, "rss_mb": _rss_mb(), "footprint_mb": _footprint_mb()[1],
            "pid": os.getpid(), "init_s": _W["init_s"], "profile": _profile(), "exact_pairs": _W["exact_pairs"]}


# ---------------------------------------------------------------------------
# Shared sample store: built once per STEP (+ sweep set), mapped read-only by every worker
# ---------------------------------------------------------------------------
STORE_ROOT = ROOT / "tmp" / "kin" / "gate_samples"
STORE_FORMAT = 1
STORE_KEEP = 2           # STEP digests whose stores are kept (most recently used)


def _file_digest(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 24), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _store_dir(step_file, mode, sweeps=None):
    """kin: moving prototypes whole + static prototypes where the sweeps reach (so keyed on the
    sweeps too); static: every prototype whole."""
    import hashlib
    tag = f"v{STORE_FORMAT}_d{MESH_DEFL}_s{SAMPLE}"
    if mode == "kin":
        h = hashlib.sha256(np.ascontiguousarray(np.asarray(sweeps, dtype=float)).tobytes()
                           + repr((NEAR, INFLATE)).encode()).hexdigest()[:16]
        tag = f"kin_{tag}_{h}"
    else:
        tag = f"static_{tag}"
    return STORE_ROOT / _file_digest(step_file) / tag


def _store_entries(mode):
    """(role, prototype) entries a gate of this mode samples; runs in a build worker."""
    ents = set()
    for lf in _W["world"].leaves:
        if mode == "static":
            ents.add(("f", lf["proto"]))
        else:
            ents.add(("s" if lf["kind"] in ("static", "suspect") else "m", lf["proto"]))
    return sorted(ents, key=lambda e: (e[0], e[1]))


def _build_part(task):
    """Sample one share of the prototypes and save it as .npy (runs in a build worker)."""
    mode, entries, out, part = task
    arrays = {k: [] for k in ("P", "N", "U", "F", "R")}
    index, first = {}, {}
    n = u = 0
    for role, key in entries:
        if role == "s" and not _region_hit(key):
            index[f"{role}:{key}"] = [part, n, n, u, u]           # no sweep reaches it: no samples
            continue
        T, tlo, thi = _mesh(_W["world"].proto(key))
        first[str(key)] = T[0, 0].tolist() if len(T) else None
        if role == "f":
            P, N, F, R = _full_arrays(T)
            arrays["F"].append(F)
            arrays["R"].append(R)
            U = np.zeros((0, 3))
        else:
            if role == "s":
                sel = _region_mask(key, tlo, thi)
                T = T[sel] if sel.any() else None
            P, N, _, U = _pack(*(_grid_samples(T) if T is not None else (np.zeros((0, 3)), np.zeros((0, 3)))))
        arrays["P"].append(P)
        arrays["N"].append(N)
        arrays["U"].append(U)
        index[f"{role}:{key}"] = [part, n, n + len(P), u, u + len(U)]
        n, u = n + len(P), u + len(U)
        del T, tlo, thi
    for k, v in arrays.items():
        if v:
            a = np.concatenate(v) if len(v) > 1 else v[0]
            if k == "N" and mode == "kin":
                a = a.astype(np.float32)
            np.save(Path(out) / f"p{part}_{k}.npy", np.ascontiguousarray(a))
    return index, first


def _open_store(path):
    d = Path(path)
    idx = json.loads((d / "index.json").read_text())
    return {"dir": d, "entries": idx["entries"], "first": idx["first"], "maps": {}}


def _store_arrays(role, key):
    """Views (read-only, memory-mapped) of one prototype's stored samples, or None."""
    st = _W.get("store")
    if st is None:
        return None
    e = st["entries"].get(f"{role}:{key}")
    if e is None:
        return None
    part, s, t, us, ut = e
    maps = st["maps"].get(part)
    if maps is None:
        maps = {}
        for f in st["dir"].glob(f"p{part}_*.npy"):
            name = f.stem.split("_", 1)[1]
            try:
                maps[name] = np.load(f, mmap_mode="r")
            except ValueError:                                   # zero-length arrays cannot be mapped
                maps[name] = np.load(f)
        st["maps"][part] = maps
    out = {name: a[s:t] for name, a in maps.items() if name != "U"}
    out["U"] = maps["U"][us:ut] if "U" in maps else np.zeros((0, 3))
    if "P" not in out:
        out["P"], out["N"] = np.zeros((0, 3)), np.zeros((0, 3), dtype=np.float32)
    return out


def _prune_store(keep_dir):
    import shutil
    digests = sorted((p for p in STORE_ROOT.iterdir() if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    for p in digests:
        for tmp in p.glob(".*.tmp"):
            if time.time() - tmp.stat().st_mtime > 86400:
                shutil.rmtree(tmp, ignore_errors=True)
    for p in digests[STORE_KEEP:]:
        if p != keep_dir.parent:
            shutil.rmtree(p, ignore_errors=True)


def build_store(step_file, mode, obbs, sweeps=None, workers=DEFAULT_WORKERS):
    """The shared sample store for this STEP (and sweep set): reused when present, else built by a
    short-lived pool (it exits, freeing every decoded prototype and mesh). Returns (dir, built)."""
    import shutil
    d = _store_dir(step_file, mode, sweeps)
    if (d / "index.json").exists():
        os.utime(d.parent)
        return d, False
    tmp = d.parent / f".{d.name}.{os.getpid()}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    ctx = mp.get_context("spawn")
    with ctx.Pool(max(1, workers), initializer=_init, initargs=(str(step_file), obbs, os.getpid(), sweeps)) as p:
        entries = p.apply(_store_entries, (mode,))
        # biggest prototypes first, dealt round-robin into small parts that the pool balances
        size = {k: float(np.prod(2 * np.asarray(h) + 1.0)) for k, (_, _, h) in obbs.items()}
        entries.sort(key=lambda e: -size[e[1]])
        nparts = max(1, min(len(entries), 8 * max(1, workers)))
        tasks = [(mode, entries[i::nparts], str(tmp), i) for i in range(nparts)]
        index = {"mode": mode, "step": str(step_file), "entries": {}, "first": {}}
        for ents, first in p.imap_unordered(_build_part, tasks):
            index["entries"].update(ents)
            index["first"].update(first)
        p.close()
        p.join()
    (tmp / "index.json").write_text(json.dumps(index))
    try:
        os.rename(tmp, d)
    except OSError:                         # a concurrent gate stored the same samples first
        shutil.rmtree(tmp, ignore_errors=True)
    _prune_store(d)
    return d, True


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------
def _obbs_oneshot(step_file):
    ctx = mp.get_context("spawn")
    with ctx.Pool(1) as p:
        return p.apply(_obb_table, (str(step_file),))


def _pool(n, step_file, obbs, sweeps=None, store=None, exact_near=False):
    ctx = mp.get_context("spawn")
    return ctx.Pool(n, initializer=_init, initargs=(str(step_file), obbs, os.getpid(), sweeps,
                                                     None if store is None else str(store), exact_near))


def _store_for(step_file, mode, obbs, sweeps, workers):
    t0 = time.time()
    store, built = build_store(step_file, mode, obbs, sweeps, workers)
    size = sum(f.stat().st_size for f in store.glob("*.npy")) / 2**20
    print(f"[gate] samples {'built' if built else 'reused'}: {store.relative_to(ROOT)} ({size:.0f} MB, "
          f"{time.time() - t0:.1f}s)", flush=True)
    return store


def _swept_boxes(step_file, obbs, by_theta):
    """World AABB of every moving leaf over all sampled angles (springs: their rest box)."""
    w = World(step_file)                    # lazy: no prototype is decoded here
    ob = {k: (np.array(c), np.array(A), np.array(h)) for k, (c, A, h) in obbs.items()}
    out = []
    for lf in w.leaves:
        if lf["kind"] in ("static", "suspect"):
            continue
        boxes = [_aabb_of_obb(_obb_world(ob[lf["proto"]], lf["L"]))]
        if lf["kind"] != "spring":
            for mats in by_theta.values():
                M = mats.get(lf["label"])
                if M is not None:
                    boxes.append(_aabb_of_obb(_obb_world(ob[lf["proto"]], np.asarray(M) @ lf["L"])))
            if len(boxes) == 1:     # the clip names parts by the document tree's labels, this by read_scene's
                raise SystemExit(f"[gate] moving leaf {lf['label']!r} has no matrix from the clip: "
                                 "read_scene and the document tree disagree on its label")
        b = np.array(boxes)
        out.append(np.concatenate([b[:, :3].min(axis=0), b[:, 3:].max(axis=0)]).tolist())
    return out


def _animation_for(step_file, thetas):
    """The `running` clip's matrices on this STEP's labels, checked equal to kin.py first."""
    from lib import animcheck
    ok, rep, by_theta = animcheck.check(animcheck.built_document(step_file), thetas=thetas, verbose=False)
    if not ok:
        raise SystemExit("[gate] the animation does not equal kin.py for this assembly: "
                         f"max diff {rep['max_matrix_diff']:.2e}; " + "; ".join(rep["problems"][:5]))
    return rep, by_theta


def run_kinematic(step_file, thetas, workers):
    t0 = time.time()
    rep, by_theta = _animation_for(step_file, thetas)
    print(f"[gate] equivalence: running clip == kin at {len(thetas)} angles, {rep['moving']} moving labels: "
          f"max {rep['max_matrix_diff']:.2e} (springs {rep['max_spring_diff']:.2e}) ({time.time() - t0:.1f}s)",
          flush=True)
    t0 = time.time()
    obbs = _obbs_oneshot(step_file)
    print(f"[gate] oriented boxes of {len(obbs)} prototypes ({time.time() - t0:.1f}s)", flush=True)
    sweeps = _swept_boxes(step_file, obbs, by_theta)
    store = _store_for(step_file, "kin", obbs, sweeps, workers)
    # an angle and its +360 twins go to ONE worker, in order: the second revolution then hits
    # that worker's pair memo (same relative placements) instead of redoing the samples
    groups = {}
    for th in thetas:
        groups.setdefault(round(th % 360.0, 6), []).append(th)
    tasks = [[(th, {lab: M.tolist() for lab, M in by_theta[th].items()}) for th in sorted(g)]
             for g in groups.values()]
    t0 = time.time()
    results = []
    pool = _pool(min(workers, len(tasks)), step_file, obbs, sweeps, store)
    try:
        for rs in pool.imap_unordered(_kin_group_task, tasks):
            for r in rs:
                results.append(r)
                print(f"[gate]   {r['theta']:5.0f} deg: {len(r['clashes'])} clashes, {r['candidates']} pairs, "
                      f"{r['exact']} booleans, {r['seconds']:.1f}s, peak rss {r['rss_mb']:.0f} MB "
                      f"(footprint {r['footprint_mb'] or 0:.0f} MB)", flush=True)
        pool.close()
    finally:
        pool.terminate()
    return sorted(results, key=lambda r: r["theta"]), time.time() - t0, rep


def run_clip(step_file, clip, thetas, workers, exact_near=True):
    """Interference of an exploded clip (every leaf may move) over the sampled angles."""
    from lib import animcheck, explodedrun
    t0 = time.time()
    doc = animcheck.built_document(step_file)
    ok, rep, by_theta = animcheck.check(doc, thetas=thetas, verbose=False, clip=clip)
    if not ok:
        raise SystemExit(f"[gate] {clip} does not equal kin.py + its layout: max diff {rep['max_matrix_diff']:.2e}; "
                         + "; ".join(rep["problems"][:5]))
    hidden = rep["hidden"]
    groups = {lab: g for g, labs in explodedrun.layout([lab for lab in doc.labels if ":" in lab])[0].items()
              for lab in labs}
    print(f"[gate] {clip}: clip == kin.py + offsets at {len(thetas)} angles (max {rep['max_matrix_diff']:.2e}, "
          f"springs {rep['max_spring_diff']:.2e}); {len(hidden)} hidden labels skipped ({time.time() - t0:.1f}s)",
          flush=True)
    t0 = time.time()
    obbs = _obbs_oneshot(step_file)
    print(f"[gate] oriented boxes of {len(obbs)} prototypes ({time.time() - t0:.1f}s)", flush=True)
    store = _store_for(step_file, "static", obbs, None, workers)
    tw = {}
    for th in thetas:
        tw.setdefault(round(th % 360.0, 6), []).append(th)
    tasks = [[(th, {lab: M.tolist() for lab, M in by_theta[th].items()}, hidden, groups) for th in sorted(g)]
             for g in tw.values()]
    t0 = time.time()
    results = []
    pool = _pool(min(workers, len(tasks)), step_file, obbs, None, store, exact_near)
    try:
        for rs in pool.imap_unordered(_xr_group_task, tasks):
            for r in rs:
                results.append(r)
                print(f"[gate]   {r['theta']:5.0f} deg: {len(r['clashes'])} clashes, {r['candidates']} pairs, "
                      f"{r['exact']} booleans, {r['seconds']:.1f}s, peak rss {r['rss_mb']:.0f} MB", flush=True)
        pool.close()
    finally:
        pool.terminate()
    return sorted(results, key=lambda r: r["theta"]), time.time() - t0, rep


def print_clip(results, wall, workers, clip, exact_near):
    print(f"\n[gate] {clip.upper()}: {len(results)} crank angles; clash = common volume > {CLASH_MM3} mm^3; "
          + ("EVERY pair within ~2 mm of contact went to the exact boolean" if exact_near
             else "sampled depth test (blind below ~0.6 mm)"))
    print("theta " + "".join(f"{c:>15}" for c in XR_CATEGORIES) + "   pairs  exact  max mm^3  s/sample")
    total, unknown, worst = 0, [], {}
    for r in results:
        counts = {c: 0 for c in XR_CATEGORIES}
        for cat, a, b, v in r["clashes"]:
            counts[cat] += 1
            total += 1
            if v > worst.get(cat, (0,))[0]:
                worst[cat] = (v, a, b, r["theta"])
        vmax = max([v for _, _, v in r["exact_pairs"] if v > 0] or [0.0])
        unknown += [(r["theta"],) + tuple(u) for u in r["unknown"]]
        print(f"{r['theta']:5.0f} " + "".join(f"{counts[c]:>15}" for c in XR_CATEGORIES)
              + f"  {r['candidates']:6d} {r['exact']:6d} {vmax:9.4f} {r['seconds']:8.1f}")
    print("worst pair per category:")
    for c in XR_CATEGORIES:
        if c in worst:
            v, a, b, th = worst[c]
            print(f"  {c:>15}: {a} x {b} = {v:.3f} mm^3 @ {th:.0f} deg")
        else:
            print(f"  {c:>15}: none")
    for th, cat, a, b in unknown[:20]:
        print(f"  UNDECIDED (boolean failed) @ {th:.0f}: {cat} {a} x {b}")
    near = sorted({(a, b, v) for r in results for a, b, v in r["exact_pairs"] if v > 1e-6}, key=lambda x: -x[2])
    print(f"[gate] exact booleans with ANY common volume (> 1e-6 mm^3; a clash needs > {CLASH_MM3}): {len(near)}")
    for a, b, v in near[:15]:
        print(f"      {a} x {b} = {v:.4f} mm^3")
    _profile_lines(results)
    n_pairs = sum(r["candidates"] for r in results)
    n_exact = sum(r["exact"] for r in results)
    print(f"[gate] {total} clashing pair-samples, {len(unknown)} undecided; {n_pairs} pair tests, {n_exact} exact "
          f"booleans; wall {wall:.0f}s on {workers} workers; {_rss_line(results)}")
    return total == 0 and not unknown


def run_static(step_file, workers):
    t0 = time.time()
    obbs = _obbs_oneshot(step_file)
    store = _store_for(step_file, "static", obbs, None, workers)
    pool = _pool(workers, step_file, obbs, None, store)
    try:
        results = pool.map(_static_task, [(s, workers) for s in range(workers)])
        pool.close()
    finally:
        pool.terminate()
    return results, time.time() - t0


def _rss_line(results):
    rss, fp = {}, {}
    for r in results:
        rss[r["pid"]] = max(rss.get(r["pid"], 0), r["rss_mb"])
        fp[r["pid"]] = max(fp.get(r["pid"], 0), r.get("footprint_mb") or 0)
    return (f"peak RSS per worker {', '.join(f'{v:.0f}' for v in rss.values())} MB (total {sum(rss.values()) / 1024:.1f} GB; "
            f"counts the shared mapped samples); peak private footprint {', '.join(f'{v:.0f}' for v in fp.values())} MB "
            f"(total {sum(fp.values()) / 1024:.1f} GB)")


def _profile_lines(results):
    prof = {}
    for r in results:          # counters only grow: a worker's LATEST profile has the most sampling seconds
        if r["pid"] not in prof or r["profile"]["sample_s"] >= prof[r["pid"]]["sample_s"]:
            prof[r["pid"]] = r["profile"]
    for pid, p in prof.items():
        print(f"[gate] worker {pid}: meshing {p['mesh_s']}s, sampling {p['sample_s']}s, "
              f"{p['booleans']} booleans {p['boolean_s']}s, cache drops {p['cache_drops']}; slowest {p['slowest'][:3]}")


def print_kinematic(results, wall, workers):
    print(f"\n[gate] KINEMATIC: {len(results)} crank angles; clash = common volume > {CLASH_MM3} mm^3")
    short = {"piston-valve": "pist-valve", "rod-rod": "rod-rod", "rod-crankcase": "rod-case", "pushrod-fin": "pushrod-fin",
             "piston-piston": "pist-pist", "piston-barrel": "pist-barrel", "other": "other"}
    print("theta " + "".join(f"{short[c]:>12}" for c in CATEGORIES) + "   pairs  bool  s/sample")
    worst, total, unknown = {}, {c: 0 for c in CATEGORIES}, []
    for r in results:
        counts = {c: 0 for c in CATEGORIES}
        for cat, a, b, v in r["clashes"]:
            counts[cat] += 1
            total[cat] += 1
            if v > worst.get(cat, (0,))[0]:
                worst[cat] = (v, a, b, r["theta"])
        unknown += [(r["theta"],) + tuple(u) for u in r["unknown"]]
        print(f"{r['theta']:5.0f} " + "".join(f"{counts[c]:>12}" for c in CATEGORIES)
              + f"  {r['candidates']:6d} {r['exact']:5d}  {r['seconds']:8.1f}")
    print("worst pair per category:")
    for c in CATEGORIES:
        if c in worst:
            v, a, b, th = worst[c]
            print(f"  {c:>13}: {a} x {b} = {v:.1f} mm^3 @ {th:.0f} deg")
        else:
            print(f"  {c:>13}: none")
    for th, cat, a, b in unknown[:20]:
        print(f"  UNDECIDED (boolean failed) @ {th:.0f}: {cat} {a} x {b}")
    _profile_lines(results)
    secs = [r["seconds"] for r in results]
    print(f"[gate] {sum(total.values())} clashing pair-samples, {len(unknown)} undecided; per sample "
          f"{np.mean(secs):.1f}s mean / {max(secs):.1f}s max; wall {wall:.0f}s on {workers} workers; {_rss_line(results)}")
    return sum(total.values()) == 0 and not unknown


def print_static(results, wall):
    clashes = sorted((c for r in results for c in r["clashes"]), key=lambda c: -c[3])
    unknown = [u for r in results for u in r["unknown"]]
    print(f"\n[gate] STATIC interference, every leaf pair at rest: {len(clashes)} clashing pairs, {len(unknown)} "
          f"undecided ({sum(r['candidates'] for r in results)} pairs tested, "
          f"{sum(r['exact'] for r in results)} booleans, {wall:.0f}s)")
    by = {}
    for c in clashes:
        by.setdefault(c[0], []).append(c)
    for cat in sorted(by):
        print(f"  {cat}: {len(by[cat])} pairs")
        for _, a, b, v in by[cat][:10]:
            print(f"      {a} x {b} = {v:.1f} mm^3")
        if len(by[cat]) > 10:
            print(f"      ... {len(by[cat]) - 10} more (see --json)")
    for cat, a, b in unknown[:20]:
        print(f"  UNDECIDED (boolean failed): {cat} {a} x {b}")
    _profile_lines(results)
    print(f"[gate] {_rss_line(results)}")
    return not clashes and not unknown


def main(argv=None):
    ap = argparse.ArgumentParser(description="kinematic collision gate")
    ap.add_argument("--file", default=str(DEFAULT_FILE), help="built assembly STEP")
    ap.add_argument("--step", type=float, default=10.0, help="crank-angle step (deg) over 0..720")
    ap.add_argument("--angles", default=None, help="comma list of crank angles instead of the sweep")
    ap.add_argument("--workers", type=int, default=DEFAULT_WORKERS, help=f"process pool size (max {MAX_WORKERS})")
    ap.add_argument("--static", action="store_true", help="static interference of every leaf pair instead")
    ap.add_argument("--clip", default=None, help="gate an exploded clip instead of `running` (exploded-running)")
    ap.add_argument("--no-exact-near", action="store_true",
                    help="--clip: sampled depth test only (default: every near pair gets the exact boolean)")
    ap.add_argument("--json", default=None)
    a = ap.parse_args(argv)
    workers = max(1, min(MAX_WORKERS, a.workers))
    if not Path(a.file).exists():
        raise SystemExit(f"[gate] {a.file} does not exist: run `python tools/engine.py build` first")
    if a.clip:
        thetas = ([float(x) for x in a.angles.split(",")] if a.angles
                  else [i * a.step for i in range(int(round(720 / a.step)) + 1)])
        results, wall, rep = run_clip(a.file, a.clip, thetas, workers, not a.no_exact_near)
        ok = print_clip(results, wall, workers, a.clip, not a.no_exact_near)
        out = {"mode": a.clip, "ok": ok, "equivalence": rep, "results": results, "wall_s": wall}
    elif a.static:
        results, wall = run_static(a.file, workers)
        ok = print_static(results, wall)
        out = {"mode": "static", "ok": ok, "results": results, "wall_s": wall}
    else:
        thetas = ([float(x) for x in a.angles.split(",")] if a.angles
                  else [i * a.step for i in range(int(round(720 / a.step)) + 1)])
        results, wall, rep = run_kinematic(a.file, thetas, workers)
        ok = print_kinematic(results, wall, workers)
        out = {"mode": "kinematic", "ok": ok, "equivalence": rep, "results": results, "wall_s": wall}
    if a.json:
        Path(a.json).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json).write_text(json.dumps(out, indent=1, default=float))
        print(f"[gate] wrote {a.json}")
    print(f"[gate] {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
