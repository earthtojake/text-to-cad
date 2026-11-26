"""Compare two output folders in reference.py's layout (reference vs core, or wasmtime vs browser), per model.

    python compare.py LEFT_DIR RIGHT_DIR [--json OUT.json] [--models a,b]   (cad's Python: needs numpy)

Prints a table per aspect and writes the numbers as JSON (default: compare.json beside RIGHT_DIR... see --json).
Per model it checks:
  structure   prototypes (index, key, name, color, faceNames, edgeNames, vertexNames, faceColors equal), instances
              (prototype, path, color equal; matrix within 1e-9)
  shape.bin   byte-identical; blake2b-128 == key (both sides)
  mesh.xbm    header (version, counts, offsets) equal, face table ordinals/order, faces whose index count differs,
              edge table (ordinal, point count, class) identical, edge points / vertex table max abs diff, per-face
              area (from the triangles) max relative diff, total triangles each side, deflections
  elements/groups/measure   same keys and list lengths, ints and strings identical, floats: max abs / max rel diff and
              the count beyond (abs > 1e-9 AND rel > 1e-6)
  bytes       how many parts' files are byte-identical, per file
A part present on one side only (or unreadable) counts as missing. Exit status 0 always; read the table.
"""
import argparse, hashlib, json, math, struct, sys
from pathlib import Path

import numpy as np

HEADER = struct.Struct("<4sI6I7I2f3I")
PROTO_KEYS = ("index", "key", "name", "color", "faceNames", "edgeNames", "vertexNames", "faceColors")
INST_KEYS = ("prototype", "path", "color")
FILES = ("key", "shape.bin", "mesh.xbm", "elements.json", "groups.json", "measure.json")
ABS_TOL, REL_TOL = 1e-9, 1e-6


class Float:
    """Accumulates float comparisons."""
    def __init__(self):
        self.n = self.beyond = 0; self.max_abs = self.max_rel = 0.0
        self.shape = self.ints = self.strs = 0  # structural mismatches, int diffs, string/other diffs

    def num(self, a, b):
        self.n += 1
        d = abs(a - b)
        if math.isnan(a) and math.isnan(b): return
        r = d / max(abs(a), abs(b), 1e-300) if d > 0 else 0.0
        self.max_abs = max(self.max_abs, d); self.max_rel = max(self.max_rel, r)
        if d > ABS_TOL and r > REL_TOL: self.beyond += 1

    def walk(self, a, b):
        if isinstance(a, dict) and isinstance(b, dict):
            if a.keys() != b.keys():
                self.shape += 1
            for k in a.keys() & b.keys(): self.walk(a[k], b[k])
        elif isinstance(a, list) and isinstance(b, list):
            if len(a) != len(b): self.shape += 1
            for x, y in zip(a, b): self.walk(x, y)
        elif isinstance(a, bool) or isinstance(b, bool) or a is None or b is None:
            if a is not b and a != b: self.strs += 1
        elif isinstance(a, int) and isinstance(b, int):
            if a != b: self.ints += 1
        elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
            self.num(float(a), float(b))
        elif isinstance(a, str) and isinstance(b, str):
            if a != b: self.strs += 1
        else:
            self.shape += 1

    def merge(self, o):
        self.n += o.n; self.beyond += o.beyond; self.shape += o.shape; self.ints += o.ints; self.strs += o.strs
        self.max_abs = max(self.max_abs, o.max_abs); self.max_rel = max(self.max_rel, o.max_rel)

    def out(self):
        return dict(floats=self.n, max_abs=self.max_abs, max_rel=self.max_rel, beyond=self.beyond,
                    shape_diffs=self.shape, int_diffs=self.ints, str_diffs=self.strs,
                    identical=(self.shape + self.ints + self.strs + self.beyond == 0 and self.max_abs == 0))


def read(p: Path):
    try: return p.read_bytes()
    except OSError: return None


def jload(b):
    try: return json.loads(b)
    except Exception: return None


def cmp_structure(l, r):
    a, b = jload(l), jload(r)
    out = dict(present=a is not None and b is not None, prototypes=[0, 0], instances=[0, 0], protos_bad={}, matrix_max=0.0)
    if a is None or b is None: return out
    pa, pb = a["prototypes"], b["prototypes"]
    out["prototypes"] = [len(pa), len(pb)]
    out["instances"] = [len(a["instances"]), len(b["instances"])]
    bad = {k: 0 for k in PROTO_KEYS}
    for x, y in zip(pa, pb):
        for k in PROTO_KEYS:
            if x.get(k) != y.get(k): bad[k] += 1
    out["protos_bad"] = {k: v for k, v in bad.items() if v}
    ib = {k: 0 for k in INST_KEYS}
    for x, y in zip(a["instances"], b["instances"]):
        for k in INST_KEYS:
            if x.get(k) != y.get(k): ib[k] += 1
        mx, my = x.get("matrix"), y.get("matrix")
        if mx is None or my is None or len(mx) != len(my):
            if mx != my: ib["matrix"] = ib.get("matrix", 0) + 1
        else:
            d = max((abs(p - q) for p, q in zip(np.ravel(mx), np.ravel(my))), default=0.0)
            out["matrix_max"] = max(out["matrix_max"], d)
            if d > 1e-9: ib["matrix"] = ib.get("matrix", 0) + 1
    out["instances_bad"] = {k: v for k, v in ib.items() if v}
    out["ok"] = (out["prototypes"][0] == out["prototypes"][1] and out["instances"][0] == out["instances"][1]
                 and not out["protos_bad"] and not out["instances_bad"])
    return out


def parse_mesh(b):
    h = HEADER.unpack_from(b)
    magic, version = h[0], h[1]
    nodes, idx, faces, edges, pts, verts = h[2:8]
    off = h[8:15]
    arr = lambda o, dt, n, w: np.frombuffer(b, dt, n * w, o).reshape(-1, w) if w > 1 else np.frombuffer(b, dt, n, o)
    return dict(header=h[:15], defl=h[15:17], magic=magic, pos=arr(off[0], "<f4", nodes, 3), normals=arr(off[1], "<f4", nodes, 3), idx=arr(off[2], "<u4", idx, 1),
                faces=arr(off[3], "<u4", faces, 3), edges=arr(off[4], "<u4", edges, 4),
                pts=arr(off[5], "<f4", pts, 3), verts=arr(off[6], "<f4", verts, 4))


def face_areas(m):
    out = []
    for _, first, count in m["faces"]:
        t = m["idx"][first:first + count].reshape(-1, 3)
        if len(t) == 0: out.append(0.0); continue
        p = m["pos"].astype(np.float64)
        c = np.cross(p[t[:, 1]] - p[t[:, 0]], p[t[:, 2]] - p[t[:, 0]])
        out.append(float(np.linalg.norm(c, axis=1).sum() / 2))
    return np.array(out)


def cmp_mesh(l, r):
    out = dict(ok=False)
    try: a, b = parse_mesh(l), parse_mesh(r)
    except Exception as e:
        out["error"] = str(e); return out
    out["header_equal"] = a["header"] == b["header"]
    out["header_counts_equal"] = a["header"][:8] == b["header"][:8]
    out["tri"] = [len(a["idx"]) // 3, len(b["idx"]) // 3]
    out["nodes"] = [len(a["pos"]), len(b["pos"])]
    out["deflections_equal"] = a["defl"] == b["defl"]
    fa, fb = a["faces"], b["faces"]
    out["face_order_equal"] = fa[:, 0].tolist() == fb[:, 0].tolist()
    if len(fa) == len(fb):
        out["faces_index_count_diff"] = int((fa[:, 2] != fb[:, 2]).sum())
        wa, wb = face_areas(a), face_areas(b)
        den = np.maximum(np.maximum(wa, wb), 1e-300)
        out["area_max_rel"] = float((np.abs(wa - wb) / den).max()) if len(wa) else 0.0
    else:
        out["faces_index_count_diff"] = None; out["area_max_rel"] = None
    out["pos_max_abs"] = float(np.abs(a["pos"].astype(float) - b["pos"]).max()) if a["pos"].shape == b["pos"].shape and a["pos"].size else (0.0 if a["pos"].shape == b["pos"].shape else None)
    na, nb = a["normals"], b["normals"]
    out["normal_max_abs"] = float(np.abs(na.astype(float) - nb).max()) if na.shape == nb.shape and na.size else (0.0 if na.shape == nb.shape else None)
    out["indices_identical"] = bool(a["idx"].shape == b["idx"].shape and (a["idx"] == b["idx"]).all())
    # same triangles up to rotation of each triple (orientation kept) and order, compared by node index
    def canon(m):
        t = m["idx"].reshape(-1, 3).astype(np.int64)
        r = np.argmin(t, axis=1)
        rolled = np.stack([t[np.arange(len(t)), (r + k) % 3] for k in range(3)], axis=1)
        return rolled[np.lexsort(rolled.T[::-1])] if len(t) else rolled
    out["triangles_same_set"] = bool(a["idx"].shape == b["idx"].shape and (canon(a) == canon(b)).all())
    out["deflections"] = [list(a["defl"]), list(b["defl"])]
    ea, eb = a["edges"], b["edges"]
    out["edge_table_identical"] = ea.shape == eb.shape and bool((ea[:, [0, 2, 3]] == eb[:, [0, 2, 3]]).all())
    out["edge_points_max_abs"] = float(np.abs(a["pts"].astype(float) - b["pts"]).max()) if a["pts"].shape == b["pts"].shape and a["pts"].size else (0.0 if a["pts"].shape == b["pts"].shape else None)
    va, vb = a["verts"], b["verts"]
    out["vertex_ordinals_equal"] = va.shape == vb.shape and bool((va[:, 0] == vb[:, 0]).all())
    out["vertex_max_abs"] = float(np.abs(va.astype(float) - vb).max()) if va.shape == vb.shape and va.size else (0.0 if va.shape == vb.shape else None)
    out["ok"] = bool(out["header_counts_equal"] and out["face_order_equal"] and out["edge_table_identical"]
                     and out["faces_index_count_diff"] == 0)
    return out


def compare_model(L: Path, R: Path):
    res = {}
    res["structure"] = cmp_structure(read(L / "structure.json"), read(R / "structure.json"))
    pl = sorted((int(p.name) for p in (L / "parts").glob("*") if p.name.isdigit()))
    pr = sorted((int(p.name) for p in (R / "parts").glob("*") if p.name.isdigit()))
    parts = sorted(set(pl) | set(pr))
    res["parts"] = [len(pl), len(pr)]
    ident = {f: 0 for f in FILES}; present = {f: 0 for f in FILES}
    shape = dict(identical=0, total=0, key_l_ok=0, key_r_ok=0, missing=0)
    mesh_all, mesh_agg = [], {}
    fl = {n: Float() for n in ("elements", "groups", "measure")}
    missing = {n: 0 for n in ("mesh.xbm", "elements.json", "groups.json", "measure.json")}
    memo = {}
    tri = [0, 0]
    for i in parts:
        d1, d2 = L / "parts" / str(i), R / "parts" / str(i)
        bl = {f: read(d1 / f) for f in FILES}; br = {f: read(d2 / f) for f in FILES}
        for f in FILES:
            if bl[f] is not None and br[f] is not None:
                present[f] += 1; ident[f] += bl[f] == br[f]
        shape["total"] += 1
        if bl["shape.bin"] is None or br["shape.bin"] is None: shape["missing"] += 1
        else:
            shape["identical"] += bl["shape.bin"] == br["shape.bin"]
            for side, bb, k in (("l", bl, "key_l_ok"), ("r", br, "key_r_ok")):
                key = (bb["key"] or b"").decode().strip()
                shape[k] += hashlib.blake2b(bb["shape.bin"], digest_size=16).hexdigest() == key
        for name, acc in (("elements.json", "elements"), ("groups.json", "groups"), ("measure.json", "measure")):
            if bl[name] is None or br[name] is None: missing[name] += 1; continue
            mk = (name, hashlib.md5(bl[name]).digest(), hashlib.md5(br[name]).digest())
            if mk not in memo:
                f = Float(); a, b = jload(bl[name]), jload(br[name])
                if a is None or b is None: f.shape += 1
                else: f.walk(a, b)
                memo[mk] = f
            fl[acc].merge(memo[mk])
        if bl["mesh.xbm"] is None or br["mesh.xbm"] is None: missing["mesh.xbm"] += 1; continue
        mk = ("mesh", hashlib.md5(bl["mesh.xbm"]).digest(), hashlib.md5(br["mesh.xbm"]).digest())
        if mk not in memo: memo[mk] = cmp_mesh(bl["mesh.xbm"], br["mesh.xbm"])
        m = memo[mk]; mesh_all.append(m)
        if "tri" in m: tri[0] += m["tri"][0]; tri[1] += m["tri"][1]
    res["shape"] = shape
    res["bytes_identical"] = {f: f"{ident[f]}/{len(parts)}" for f in FILES}
    res["missing"] = missing
    ok = [m for m in mesh_all if "error" not in m]
    def nz(vals): return max([v for v in vals if v is not None], default=0.0)
    res["mesh"] = dict(parts=len(mesh_all), errors=len(mesh_all) - len(ok),
        parts_ok=sum(m["ok"] for m in ok), header_equal=sum(m["header_equal"] for m in ok),
        counts_equal=sum(m["header_counts_equal"] for m in ok), face_order_equal=sum(m["face_order_equal"] for m in ok),
        faces_differ=sum(m["faces_index_count_diff"] or 0 for m in ok),
        parts_with_face_diff=sum(1 for m in ok if m["faces_index_count_diff"]),
        edge_table_identical=sum(m["edge_table_identical"] for m in ok),
        edge_points_max_abs=nz(m["edge_points_max_abs"] for m in ok), vertex_max_abs=nz(m["vertex_max_abs"] for m in ok),
        vertex_ordinals_equal=sum(m["vertex_ordinals_equal"] for m in ok), area_max_rel=nz(m["area_max_rel"] for m in ok),
        pos_max_abs=nz(m["pos_max_abs"] for m in ok), normal_max_abs=nz(m["normal_max_abs"] for m in ok),
        triangles_same_set=sum(m["triangles_same_set"] for m in ok), indices_identical=sum(m["indices_identical"] for m in ok), deflections_equal=sum(m["deflections_equal"] for m in ok), tri=tri)
    for k, f in fl.items(): res[k] = f.out()
    res["bytes_identical_all"] = all(v.split("/")[0] == v.split("/")[1] for v in res["bytes_identical"].values()) and res["structure"].get("present", False) and read(L / "structure.json") == read(R / "structure.json")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("left"); ap.add_argument("right")
    ap.add_argument("--json", help="write results here (default RIGHT_DIR/compare.json)")
    ap.add_argument("--models")
    a = ap.parse_args()
    L, R = Path(a.left), Path(a.right)
    names = a.models.split(",") if a.models else sorted(p.name for p in L.iterdir() if p.is_dir() and (R / p.name).is_dir())
    results = {}
    for n in names:
        print(f"... {n}", file=sys.stderr, flush=True)
        results[n] = compare_model(L / n, R / n)
    only_l = sorted(p.name for p in L.iterdir() if p.is_dir() and not (R / p.name).is_dir()) if not a.models else []
    Path(a.json or R / "compare.json").write_text(json.dumps(results, indent=1))
    g = lambda x: "-" if x is None else (f"{x:.2g}" if isinstance(x, float) else str(x))
    def table(title, header, rows):
        print(f"\n== {title}")
        w = [max(len(str(r[i])) for r in [header] + rows) for i in range(len(header))]
        for r in [header] + rows: print("  ".join(str(c).ljust(w[i]) for i, c in enumerate(r)))
    table("structure / shape.bin", ["model", "parts L/R", "struct ok", "inst L/R", "proto diffs", "inst diffs", "matrix max", "shape ident", "key=b2b L/R", "missing"],
          [[n, f"{r['parts'][0]}/{r['parts'][1]}", r["structure"].get("ok"), "{}/{}".format(*r["structure"]["instances"]),
            g(r["structure"]["protos_bad"] or 0), g(r["structure"].get("instances_bad") or 0), g(r["structure"]["matrix_max"]),
            f"{r['shape']['identical']}/{r['shape']['total']}", f"{r['shape']['key_l_ok']}/{r['shape']['key_r_ok']}", r["shape"]["missing"]]
           for n, r in results.items()])
    table("mesh.xbm (parts compared; faces/edges/area/points)", ["model", "parts", "ok", "hdr eq", "counts eq", "face order", "faces idx differ (parts)", "edge tbl ident", "pos max", "normal max", "idx ident", "tri set eq", "edge pts max", "vert max", "area max rel", "tri L/R", "err/missing"],
          [[n, r["mesh"]["parts"], r["mesh"]["parts_ok"], r["mesh"]["header_equal"], r["mesh"]["counts_equal"], r["mesh"]["face_order_equal"],
            f"{r['mesh']['faces_differ']} ({r['mesh']['parts_with_face_diff']})", r["mesh"]["edge_table_identical"], g(r["mesh"]["pos_max_abs"]), g(r["mesh"]["normal_max_abs"]), r["mesh"]["indices_identical"], r["mesh"]["triangles_same_set"], g(r["mesh"]["edge_points_max_abs"]),
            g(r["mesh"]["vertex_max_abs"]), g(r["mesh"]["area_max_rel"]), "{}/{}".format(*r["mesh"]["tri"]),
            f"{r['mesh']['errors']}/{r['missing']['mesh.xbm']}"] for n, r in results.items()])
    for k in ("elements", "groups", "measure"):
        table(k + ".json", ["model", "floats", "max abs", "max rel", "beyond tol", "shape diffs", "int diffs", "str diffs", "missing"],
              [[n, r[k]["floats"], g(r[k]["max_abs"]), g(r[k]["max_rel"]), r[k]["beyond"], r[k]["shape_diffs"], r[k]["int_diffs"], r[k]["str_diffs"], r["missing"][k + ".json"]]
               for n, r in results.items()])
    table("byte-identical files (parts)", ["model"] + list(FILES) + ["ALL (incl structure)"],
          [[n] + [r["bytes_identical"][f] for f in FILES] + [r["bytes_identical_all"]] for n, r in results.items()])
    if only_l: print("\nonly in LEFT:", ", ".join(only_l))
    print(f"\nwrote {a.json or R / 'compare.json'}")


if __name__ == "__main__":
    main()
