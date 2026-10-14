"""Stock: its starting solid, and the simulators that cut it (one per machine kind, registered lazily).

:func:`build_stock` turns the job's ``stock`` into a :class:`StockGeometry` in part coordinates (bounds, a closed
mesh, its volume): a box (a margin round the part, or a size), a cylinder (bar for a lathe or a 4th axis), a sheet,
or another STEP (a casting).

A cylinder's radius is measured on the exact part, meshed finely for it (:data:`BAR_DEFLECTION_MM`), never on the
part's display tessellation, whose chords can cut inside the part: the bar is never thinner than the part. Its
radial margin goes all round; its axial margin at each end (a lathe's bar: at the chuck end, the face end being
``face_stock_mm``). A STEP blank holds the part when its box holds the part's and the part less the blank (a
boolean cut) leaves no volume: a blank with a pocket where the part stands out is refused, though its box holds the
part's. A stock that does not hold the part is refused: a plan cut from it would be plausible and wrong.

A simulator follows the :class:`StockSim` protocol::

    sim = SimClass(stock: StockGeometry, part: Part, *, cell_mm: float, tolerance_mm: float)
    sim.supports(wcs) -> str | None          # None when it can simulate that setup, else why not (plain words)
    sim.cut(toolpath, tools, wcs) -> SimReport   # one setup's toolpath, in program order
    sim.mesh() -> (vertices (V, 3), triangles (T, 3))   # the stock now, part mm
    sim.volume() -> float                    # mm^3
    sim.material_left(part, *, stock_to_leave_mm, tolerance_mm) -> MaterialLeft | None

:data:`SIM_REGISTRY` maps a machine kind to ``"module:Class"``; :func:`create_stock_sim` imports it, and when that
module is not in this cadgen it falls back (a heightfield for a multi-axis mill, else :class:`NullSim`) and says so
as an ``adapted`` step, never a refusal. Stdlib at import; numpy inside.

What a mill's simulator does with each move (:func:`move_modes`, read from the toolpath's ``spindle`` and ``cycle``
events, so every simulator and the stock replay agree):

* a move made with the spindle stopped (after a ``spindle`` ``off`` event, before the next start) removes no stock: a
  tool that is not turning does not cut. It is judged like a rapid: material in its way is a crash.
* a back bore's stopped moves (inside a ``back_bore`` cycle: down through the hole, across under the part, up out of
  it) are the bar's neck passing through the hole: judged with the neck's radius (``shank_diameter_mm`` / 2) from the
  tip up. The oriented head's own passage through the hole is the planner's (``drill``: the shift against the head,
  the neck and the hole).
* a back bore's cutting moves (the spindle on, inside the cycle) are its head (``flute_length_mm`` tall) feeding up
  from under the part: it cuts from the far side, the head's top into the material, never the column above it.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from cadgen._internal.cam.job_errors import CamJobError

__all__ = ["BACK_CUT", "BAR_DEFLECTION_MM", "CUT", "IDLE", "MaterialLeft", "NECK", "NullSim", "PASS", "SIM_REGISTRY",
           "SimReport", "StockGeometry", "StockSim", "build_stock", "create_stock_sim", "move_modes"]

#: :func:`move_modes`: a move that cuts from the tool's side (a turning tool's feed, plunge or arc).
CUT = 1
#: A rapid, or any move made with the spindle stopped: it removes nothing, and material in its way is a crash.
PASS = 2
#: A back bore's head feeding up from under the part (the spindle on, inside a ``back_bore`` cycle).
BACK_CUT = 3
#: A back bore's move with the spindle stopped: the bar's neck through the hole.
NECK = 4
#: Anything else (a dwell): neither cuts nor moves.
IDLE = 0

#: The chord deflection (mm) the part is meshed at to measure its radius about a bar's centre line: the mesh's nodes
#: lie on the surfaces, so a face turned about that line gives its radius exactly and any other is within this.
BAR_DEFLECTION_MM = 1e-4
#: The part's volume a STEP blank may leave outside it, as a fraction of the part's (the boolean's own noise).
_OUTSIDE_FRACTION = 1e-6

_PACKAGE = "cadgen._internal.cam"

#: Machine kind -> the simulator that cuts its stock.
SIM_REGISTRY: dict[str, str] = {
    "mill": f"{_PACKAGE}.stock_heightfield:HeightfieldSim",
    "router": f"{_PACKAGE}.stock_heightfield:HeightfieldSim",
    "mill4": f"{_PACKAGE}.stock_dexel:DexelSim",
    "mill5": f"{_PACKAGE}.stock_dexel:DexelSim",
    "lathe": f"{_PACKAGE}.stock_lathe:LatheSim",
    "laser": f"{_PACKAGE}.stock_sheet:SheetSim",
    "plasma": f"{_PACKAGE}.stock_sheet:SheetSim",
    "waterjet": f"{_PACKAGE}.stock_sheet:SheetSim",
    "wire_edm": f"{_PACKAGE}.stock_sheet:SheetSim",
}
#: What a kind falls back to when its own simulator is not in this cadgen.
_FALLBACK = {"mill4": f"{_PACKAGE}.stock_heightfield:HeightfieldSim",
             "mill5": f"{_PACKAGE}.stock_heightfield:HeightfieldSim"}


@dataclass
class StockGeometry:
    kind: str
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    vertices: Any                 # (V, 3) closed mesh, part mm
    triangles: Any                # (T, 3)
    volume_mm3: float
    #: A cylinder's axis ("x", "y", "z"), centre line point and radius.
    cylinder: dict | None = None
    thickness_mm: float | None = None

    @property
    def points(self):
        return self.vertices

    def as_dict(self) -> dict:
        out = {"kind": self.kind, "min_mm": [round(v, 4) for v in self.bounds_min],
               "max_mm": [round(v, 4) for v in self.bounds_max], "volume_mm3": round(self.volume_mm3, 3)}
        if self.cylinder:
            out["cylinder"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.cylinder.items()}
        if self.thickness_mm is not None:
            out["thickness_mm"] = self.thickness_mm
        return out


@dataclass
class SimReport:
    """What cutting one setup found. ``depth_by_op``: ``{op: {"depth_mm", "at"}}``, the deepest the tool went
    below the material within reach of its side (for the reach check); ``rapid_hits``: one dict per operation whose
    rapids (or moves with the spindle stopped) passed through uncut stock (``op``, ``move``, ``at`` part mm,
    ``depth_mm``, ``count``), and one more when a back bore's neck did (with ``neck_diameter_mm``)."""

    setup: str
    removed_mm3_by_op: dict[int, float] = field(default_factory=dict)
    depth_by_op: dict[int, dict] = field(default_factory=dict)
    rapid_hits: list[dict] = field(default_factory=list)
    #: Why this setup was not simulated (plain words), or None.
    skipped: str | None = None


@dataclass
class MaterialLeft:
    volume_mm3: float
    area_mm2: float
    max_mm: float
    at: tuple[float, float, float] | None
    bounds_min: tuple[float, float, float] | None = None
    bounds_max: tuple[float, float, float] | None = None


class StockSim(Protocol):
    kind: str

    def supports(self, wcs) -> str | None: ...

    def cut(self, toolpath, tools: dict, wcs) -> SimReport: ...

    def mesh(self): ...

    def volume(self) -> float: ...

    def material_left(self, part, *, stock_to_leave_mm: float, tolerance_mm: float) -> MaterialLeft | None: ...


class NullSim:
    """No simulation: the stock stays as it started. Used when this cadgen has no simulator for a machine kind."""

    kind = "none"

    def __init__(self, stock: StockGeometry, part=None, *, cell_mm: float = 1.0, tolerance_mm: float = 0.01):
        self.stock = stock

    def supports(self, wcs) -> str | None:
        return "this cadgen has no stock simulator for this machine"

    def cut(self, toolpath, tools, wcs) -> SimReport:
        return SimReport(setup=wcs.setup_id, skipped=self.supports(wcs))

    def mesh(self):
        return self.stock.vertices, self.stock.triangles

    def volume(self) -> float:
        return self.stock.volume_mm3

    def material_left(self, part, *, stock_to_leave_mm: float, tolerance_mm: float):
        return None


def _load(target: str):
    module, cls = target.split(":")
    if importlib.util.find_spec(module) is None:
        return None
    return getattr(importlib.import_module(module), cls)


def create_stock_sim(kind: str, stock: StockGeometry, part, *, cell_mm: float, tolerance_mm: float):
    """``(simulator, adapted steps)`` for a machine kind."""
    adapted: list[dict] = []
    cls = _load(SIM_REGISTRY[kind])
    if cls is None and kind in _FALLBACK:
        cls = _load(_FALLBACK[kind])
        adapted.append({"step": "stock_sim", "words": f"the {kind}'s tri-dexel stock simulator is not in this cadgen "
                        "yet: the stock is simulated as a heightfield, so tilted and side setups are not simulated"})
    if cls is None:
        adapted.append({"step": "stock_sim", "words": f"this cadgen has no stock simulator for a {kind} yet: the "
                        "stock is not simulated, so material left and rapids into stock are not checked"})
        cls = NullSim
    sim = cls(stock, part, cell_mm=cell_mm, tolerance_mm=tolerance_mm)
    # A simulator that coarsened its own grid says so (``sim.adapted``: fit-ladder steps).
    return sim, adapted + list(getattr(sim, "adapted", ()))


def move_modes(toolpath):
    """(N,) how a mill's simulator treats each move of ``toolpath``: :data:`CUT`, :data:`PASS`, :data:`BACK_CUT`,
    :data:`NECK` or :data:`IDLE` (see the module docstring).

    The spindle turns until a ``spindle`` event with ``dir`` ``off`` stops it, and again from the next ``spindle``
    event that starts it; a toolpath with no spindle events turns throughout (a test's bare path, an operation whose
    spindle started before it). A tool change alone does not stop it here: the operation after one starts it again
    before its first move."""
    import numpy as np

    from cadgen._internal.cam.ir import ARC_CCW, ARC_CW, FEED, PLUNGE, RAPID

    moves = toolpath.moves
    n = len(moves)
    stopped = np.zeros(n, dtype=bool)
    back = np.zeros(n, dtype=bool)
    turning, since = True, 0
    for event in toolpath.events:
        at = min(max(int(event.at), 0), n)
        if event.kind == "spindle":
            if not turning:
                stopped[since:at] = True
            turning, since = event.data.get("dir", "cw") != "off", at
        elif event.kind == "cycle" and event.data.get("cycle") == "back_bore":
            back[at:min(int(event.data.get("end", at)), n)] = True
    if not turning:
        stopped[since:] = True
    kinds = moves["kind"] if n else np.zeros(0, dtype=np.uint8)
    cutting = np.isin(kinds, (FEED, PLUNGE, ARC_CW, ARC_CCW))
    moving = cutting | (kinds == RAPID)
    out = np.full(n, IDLE, dtype=np.int8)
    out[cutting & ~stopped] = CUT
    out[moving & (stopped | (kinds == RAPID))] = PASS
    out[cutting & ~stopped & back] = BACK_CUT
    out[moving & stopped & back] = NECK
    return out


# --- the starting stock --------------------------------------------------------------------------------

def _box_mesh(low, high):
    import numpy as np

    x0, y0, z0 = low
    x1, y1, z1 = high
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], dtype=float)
    t = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4],
                  [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]], dtype=np.int64)
    return v, t


def _cylinder_mesh(axis: str, centre, radius: float, start: float, end: float, segments: int = 96):
    import numpy as np

    angles = np.linspace(0.0, 2 * math.pi, segments, endpoint=False)
    u, v = {"z": (0, 1), "x": (1, 2), "y": (2, 0)}[axis]
    w = "xyz".index(axis)
    ring = np.zeros((segments, 3))
    ring[:, u] = centre[u] + radius * np.cos(angles)
    ring[:, v] = centre[v] + radius * np.sin(angles)
    low, high = ring.copy(), ring.copy()
    low[:, w], high[:, w] = start, end
    caps = np.zeros((2, 3))
    caps[:, u], caps[:, v] = centre[u], centre[v]
    caps[0, w], caps[1, w] = start, end
    vertices = np.vstack([low, high, caps])
    tris = []
    for i in range(segments):
        j = (i + 1) % segments
        tris += [[i, j, segments + j], [i, segments + j, segments + i],
                 [2 * segments, j, i], [2 * segments + 1, segments + i, segments + j]]
    return vertices, np.asarray(tris, dtype=np.int64)


def build_stock(spec, part, *, base_dir: Path | None = None) -> StockGeometry:
    """The job's stock around ``part``, in part coordinates."""
    import numpy as np

    low, high = (np.asarray(v, dtype=float) for v in part.bbox)
    if spec.kind in ("box", "sheet"):
        if spec.size_mm is not None:
            size = np.asarray(spec.size_mm)
            centre = (low + high) / 2.0
            s_low = np.array([centre[0] - size[0] / 2, centre[1] - size[1] / 2, low[2]])
            s_high = s_low + size
            # Refused only when the stock does not hold the part: smaller than it on some side.
            if np.any(s_low > low + 1e-9) or np.any(s_high < high - 1e-9):
                raise CamJobError(f"stock.size_mm {list(spec.size_mm)} is smaller than the part "
                                  f"({' x '.join(f'{v:g}' for v in (high - low))} mm); make it larger or use margin_mm")
        else:
            m = spec.margin_mm
            s_low = low - np.array([m[0], m[2], m[4]])
            s_high = high + np.array([m[1], m[3], m[5]])
            if spec.kind == "sheet" and spec.thickness_mm is not None:
                s_high[2] = s_low[2] + spec.thickness_mm
                if spec.thickness_mm + 1e-9 < high[2] - low[2]:
                    raise CamJobError(f"stock.thickness_mm {spec.thickness_mm:g} is thinner than the part "
                                      f"({high[2] - low[2]:g} mm)")
        vertices, triangles = _box_mesh(s_low, s_high)
        volume = float(np.prod(s_high - s_low))
        return StockGeometry(spec.kind, tuple(s_low), tuple(s_high), vertices, triangles, volume,
                             thickness_mm=float(s_high[2] - s_low[2]) if spec.kind == "sheet" else None)
    if spec.kind == "cylinder":
        w = "xyz".index(spec.axis)
        others = [i for i in range(3) if i != w]
        centre = (low + high) / 2.0
        if spec.face_stock_mm is not None:
            centre[others] = _turning_axis(part, w, centre[others])
        reach = _reach_about(part, others, centre[others])
        radial, axial = spec.margin_mm[0], spec.margin_mm[1]
        radius = spec.diameter_mm / 2 if spec.diameter_mm else reach + radial
        if radius + 1e-6 < reach:
            raise CamJobError(f"stock.diameter_mm {2 * radius:g} does not hold the part: it reaches {2 * reach:.4g} mm "
                              f"across about its {spec.axis} axis")
        length = spec.length_mm if spec.length_mm else (high[w] - low[w]) + 2 * axial
        if length + 1e-6 < high[w] - low[w]:
            raise CamJobError(f"stock.length_mm {length:g} is shorter than the part ({high[w] - low[w]:g} mm)")
        # A stated length starts at the part's -axis end; a margin goes on both ends.
        start = low[w] if spec.length_mm else low[w] - axial
        end = start + length
        if spec.face_stock_mm is not None:
            # A lathe's bar: proud of the part's +axis end by the face stock, the rest of it back towards the chuck.
            face = spec.face_stock_mm
            length = spec.length_mm if spec.length_mm else (high[w] - low[w]) + face + axial
            end = high[w] + face
            start = end - length
            if start > low[w] + 1e-6:
                raise CamJobError(f"stock.length_mm {length:g} is shorter than the part plus face_stock_mm "
                                  f"({high[w] - low[w] + face:g} mm); give a longer bar")
        vertices, triangles = _cylinder_mesh(spec.axis, centre, radius, start, end)
        s_low, s_high = centre.copy(), centre.copy()
        s_low[others], s_high[others] = centre[others] - radius, centre[others] + radius
        s_low[w], s_high[w] = start, end
        return StockGeometry("cylinder", tuple(s_low), tuple(s_high), vertices, triangles,
                             math.pi * radius * radius * length,
                             cylinder={"axis": spec.axis, "center": [float(c) for c in centre], "radius": radius,
                                       "start": float(start), "end": float(end)})
    # from_step: another STEP, tessellated like the part.
    from cadgen._internal.cam.part import read_part

    path = Path(spec.path).expanduser()
    if not path.is_absolute():
        candidates = [d / path for d in (base_dir, part.document.parent) if d is not None]
        path = next((c for c in candidates if c.is_file()), candidates[0] if candidates else path)
    if not path.is_file():
        raise CamJobError(f"stock.path: no STEP at {path}")
    blank = read_part(path, deflection_mm=0.05)
    vertices, triangles = np.asarray(blank.vertices), np.asarray(blank.triangles)
    tri = vertices[triangles]
    volume = float(np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6.0)
    b_low, b_high = vertices.min(axis=0), vertices.max(axis=0)
    if np.any(b_low > low + 1e-6) or np.any(b_high < high - 1e-6):
        raise CamJobError(f"the stock STEP {path.name} does not enclose the part; place it around the part in the "
                          "part's coordinates")
    outside = _volume_outside(getattr(part, "shape", None), getattr(blank, "shape", None))
    if outside is not None:
        raise CamJobError(f"the stock STEP {path.name} does not hold the part: {outside:,.4g} mm3 of the part stands "
                          "outside it, though its bounding box holds the part's; model the blank where it sits round "
                          "the part, in the part's coordinates")
    return StockGeometry("from_step", tuple(b_low), tuple(b_high), vertices, triangles, abs(volume))


def _volume_outside(part_shape, blank_shape) -> float | None:
    """The part's volume outside the blank (mm3) when it is more than the boolean's noise, else None; None too when
    either has no solid (a drawing's part: the box check above is then the whole check)."""
    if part_shape is None or blank_shape is None:
        return None
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    def volume(shape) -> float:
        props = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, props)
        return abs(props.Mass())

    solid = getattr(part_shape, "wrapped", part_shape)
    cut = BRepAlgoAPI_Cut(solid, getattr(blank_shape, "wrapped", blank_shape))
    if not cut.IsDone():
        raise CamJobError("stock.path: the kernel could not compare the blank with the part; check both are solids")
    outside = volume(cut.Shape())
    return outside if outside > _OUTSIDE_FRACTION * max(volume(solid), 1.0) else None


def _reach_about(part, others: list[int], centre) -> float:
    """The part's largest distance from the centre line through ``centre`` (its coordinates across the bar's axis):
    over its display mesh's vertices and, when the part has an exact shape, the nodes of a copy of it meshed at
    :data:`BAR_DEFLECTION_MM` (the display mesh's chords can stand inside a face that is not turned about the line)."""
    import numpy as np

    points = [np.asarray(part.vertices, dtype=float)]
    shape = getattr(part, "shape", None)
    if shape is not None:
        points.append(_fine_nodes(getattr(shape, "wrapped", shape)))
    across = np.vstack([p for p in points if len(p)])[:, others] - np.asarray(centre, dtype=float)
    return float(np.sqrt((across * across).sum(axis=1)).max()) if len(across) else 0.0


def _fine_nodes(shape):
    """The vertices of ``shape`` and the nodes of a copy of it meshed at :data:`BAR_DEFLECTION_MM` ((N, 3) mm); the
    copy, because meshing writes into the shape."""
    import numpy as np
    from OCP.BRep import BRep_Tool
    from OCP.BRepBuilderAPI import BRepBuilderAPI_Copy
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.TopAbs import TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS

    copy = BRepBuilderAPI_Copy(shape).Shape()
    BRepMesh_IncrementalMesh(copy, BAR_DEFLECTION_MM, False, 0.1, False)
    nodes: list[tuple[float, float, float]] = []
    explorer = TopExp_Explorer(copy, TopAbs_VERTEX)
    while explorer.More():
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(explorer.Current()))
        nodes.append((point.X(), point.Y(), point.Z()))
        explorer.Next()
    explorer = TopExp_Explorer(copy, TopAbs_FACE)
    while explorer.More():
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(TopoDS.Face_s(explorer.Current()), location)
        if triangulation is not None:
            trsf = location.Transformation()
            for index in range(1, triangulation.NbNodes() + 1):
                point = triangulation.Node(index).Transformed(trsf)
                nodes.append((point.X(), point.Y(), point.Z()))
        explorer.Next()
    return np.asarray(nodes, dtype=float).reshape(-1, 3)


def _turning_axis(part, w: int, fallback):
    """Where the part's turning axis crosses the plane across axis ``w``: the line its round faces (cylinders and
    cones along ``w``) share, weighted by area; ``fallback`` (the box's centre) when it has none."""
    import numpy as np

    others = [i for i in range(3) if i != w]
    groups: dict[tuple, float] = {}
    for face in getattr(part, "faces", {}).values():
        if face.surface not in ("cylinder", "cone") or face.axis is None or abs(abs(face.axis[w]) - 1.0) > 1e-6:
            continue
        key = tuple(round(float(face.axis_point[i]), 4) + 0.0 for i in others)
        groups[key] = groups.get(key, 0.0) + face.area_mm2
    if not groups:
        return np.asarray(fallback, dtype=float)
    return np.asarray(max(groups, key=groups.get), dtype=float)
