"""The ``Operation`` base every planner subclasses, and the context it plans in.

An operation is a small class (one module per op under ``operations/``, registered in ``operations/__init__.py``)::

    class PocketOp(Operation):
        name = "pocket"; plain = "Pocket"; family = "2.5D milling"
        machines = MILLS; status = "full"          # or "lite", with ``limits``: plain-sentence caveats
        keys = ("entry", "ramp_angle_deg", "direction")   # its own job keys, beyond OpSpec's shared ones
        common_keys = SHARED                       # the shared tuning keys it reads (default: all of them)
        tool_types = ("flat", "bull", "ball")      # the tool types it accepts (empty: any)
        feeds_kind = "rough"                       # what it asks feeds.for_op for

        def parse(self, spec: OpSpec, ctx: ParseContext) -> params      # closed keys; teaching errors
        def plan(self, ctx: PlanContext, params) -> Toolpath           # WCS moves, op index stamped
        def summary(self, ctx: PlanContext, params) -> str              # "Pocket #o1.f12 with T1 6 mm flat"

``parse`` runs before the part is read (a malformed job fails fast); the base checks the op's own keys against
``keys``, the shared tuning keys the job wrote against ``common_keys`` (law 9: a ``stepover`` a drill never reads is
refused, not ignored), the tool's presence and type, and returns the ``extra`` dict; an op overrides it to return
its own params.
``plan`` starts at ``ctx.start`` (over the part at the clearance height) and should end at the clearance height; the
run adds the tool change, spindle and coolant events around it and stamps the op range. Facts the checks read go
in ``ctx.meta`` (``unreachable``: corners the tool cannot reach, for ``corner_radius``).

:class:`PlanContext` hands a planner everything in WCS: ``part`` and its mesh (``mesh``), ``sections`` (material at
a height), ``face``/``floor``/``footprint`` lookups, ``stock`` and its ``stock_outline``, ``heights``, the ``tool``,
``feeds(kind)`` with the job's overrides (feed, speed, plunge) applied, ``stepover``/``stepdown`` with the op's defaults, and a ``log``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar

from cadgen._internal.cam.job_errors import CamJobError, check_keys

__all__ = ["Operation", "ParseContext", "PlanContext", "SHARED"]

#: The shared keys (job.OP_COMMON_KEYS) that tune an operation's cut. Each operation lists the ones it reads
#: (``Operation.common_keys``); ``op``, ``tool``, ``name``, ``coolant``, ``clearance_mm`` and ``retract_mm`` every
#: operation reads, and ``faces`` and ``region`` are ``takes_faces`` and ``takes_region``. ``plunge_mm_min`` is read by
#: every operation that has a plunge, whatever its ``common_keys`` say (:meth:`Operation.with_plunge`).
SHARED = ("feed", "speed", "stepdown_mm", "stepover", "stepover_mm", "stock_to_leave_mm", "plunge_mm_min")
#: The feeds kinds (feeds.OP_KINDS) whose cut has a plunge: a milling cutter coming down along its axis at its own,
#: slower feed. A hole maker feeds along its axis at its feed, a lathe tool by the revolution, and a beam or a wire
#: never plunges, so their operations refuse ``plunge_mm_min``.
PLUNGE_KINDS = ("rough", "slot", "finish", "face", "engrave", "thread_mill")


@dataclass(frozen=True)
class ParseContext:
    job: Any                      # job.Job
    setup: Any                    # job.Setup


@dataclass
class PlanContext:
    job: Any
    setup: Any                    # job.Setup
    wcs: Any                      # wcs.WCS
    heights: Any                  # linking.Heights
    part: Any                     # part.Part
    stock: Any                    # stock.StockGeometry
    sections: Any                 # geom2d.Sections, WCS
    spec: Any                     # job.OpSpec
    index: int                    # the global operation index
    tool: Any = None              # tools.Tool
    start: tuple = (0.0, 0.0, 0.0)
    tolerance_mm: float = 0.01
    log: Any = None
    meta: dict = field(default_factory=dict)
    #: Every feeds the op asked for, in order; the first is the one its row shows.
    chosen_feeds: list = field(default_factory=list)
    #: Everything planned before this operation, in program order across setups: ``(wcs, Toolpath)`` per operation
    #: (its op range, tool and events included), so a planner can simulate the stock as it stands (rest machining).
    history: list = field(default_factory=list)

    @property
    def machine(self):
        return self.job.machine

    @property
    def material(self):
        return self.job.material

    @property
    def mesh(self):
        """The part's (vertices, triangles) in this setup's WCS."""
        return self.part.mesh_in(self.wcs)

    def builder(self, start=None):
        from cadgen._internal.cam.ir import ToolpathBuilder

        return ToolpathBuilder(self.start if start is None else start, op=self.index)

    def feeds(self, kind: str, *, stepover_mm: float | None = None):
        from cadgen._internal.cam.feeds import for_op

        chosen = for_op(self.material, self.tool, kind, self.machine, stepover_mm=stepover_mm, feed=self.spec.feed,
                        speed=self.spec.speed, plunge=getattr(self.spec, "plunge_mm_min", None))
        self.chosen_feeds.append(chosen)
        return chosen

    def stepover(self, default_fraction: float) -> float:
        """The op's stepover in mm: ``stepover_mm``, else ``stepover`` x diameter, else the default fraction."""
        if self.spec.stepover_mm is not None:
            return float(self.spec.stepover_mm)
        fraction = self.spec.stepover if self.spec.stepover is not None else default_fraction
        return max(0.01, fraction * self.tool.diameter_mm)

    def stepdown(self) -> float:
        from cadgen._internal.cam.feeds import default_stepdown

        if self.spec.stepdown_mm is not None:
            return float(self.spec.stepdown_mm)
        return default_stepdown(self.material, self.tool)

    def face(self, ref: str):
        return self.part.face(ref, where=f"{self.spec.where}.faces")

    def face_triangles(self, ref: str):
        import numpy as np

        info = self.face(ref)
        return np.asarray(self.part.triangles)[np.asarray(self.part.face_of_triangle) == info.ordinal]

    def floor(self, ref: str) -> tuple[float, Any]:
        """A flat face facing the tool: its WCS height and its footprint (WCS XY). Anything else is refused."""
        import numpy as np

        info = self.face(ref)
        normal = None if info.normal is None else self.wcs.vectors_to_wcs([info.normal])[0]
        if info.surface != "plane" or normal is None or normal[2] < 1.0 - 1e-6:
            facing = "" if normal is None else f" facing ({', '.join(f'{v:.2f}' for v in normal)}) in this setup"
            raise CamJobError(f"{self.spec.where}.faces: {ref} is a {info.surface}{facing}; a {self.spec.op} names "
                              f"flat floors facing the tool (+Z of setup '{self.setup.id}')")
        vertices, _ = self.mesh
        triangles = self.face_triangles(ref)
        z = float(np.asarray(vertices)[np.unique(triangles)][:, 2].mean())
        return z, self.footprint(triangles)

    def footprint(self, triangles):
        from cadgen._internal.cam.geom2d import footprint

        vertices, _ = self.mesh
        return footprint(vertices, triangles)

    @property
    def stock_outline(self):
        """The stock's silhouette on the WCS XY plane."""
        import shapely

        points = self.wcs.to_wcs(self.stock.vertices)[:, :2]
        return shapely.MultiPoint(points).convex_hull

    def say(self, message: str) -> None:
        if self.log is not None:
            self.log(message)


class Operation:
    name: ClassVar[str] = ""
    plain: ClassVar[str] = ""
    family: ClassVar[str] = ""
    machines: ClassVar[tuple[str, ...]] = ()
    status: ClassVar[str] = "full"
    #: Plain-sentence caveats a lite operation carries into its results, its verdict caption and the skill.
    limits: ClassVar[tuple[str, ...]] = ()
    #: The op's own job keys, beyond the ones every operation shares (job.OP_COMMON_KEYS).
    keys: ClassVar[tuple[str, ...]] = ()
    #: The shared tuning keys (:data:`SHARED`) it reads; one the job sets that it does not read is refused.
    common_keys: ClassVar[tuple[str, ...]] = SHARED
    #: Tool types it accepts; empty accepts any.
    tool_types: ClassVar[tuple[str, ...]] = ()
    needs_tool: ClassVar[bool] = True
    #: Whether it names faces (``faces``), a ``region``, either, or neither.
    takes_faces: ClassVar[bool] = False
    takes_region: ClassVar[bool] = False
    feeds_kind: ClassVar[str] = "rough"

    def parse(self, spec, ctx: ParseContext) -> Any:
        """Closed keys, the tool's presence and type; returns the op's own keys (``spec.extra``)."""
        check_keys(spec.extra, self.keys, spec.where, hint=f"a {self.name}")
        self.check_common_keys(spec, self.shared_keys(spec))
        if self.needs_tool:
            if spec.tool is None:
                raise CamJobError(f"{spec.where}: a {self.name} needs \"tool\", one of the job's tools")
            tool = ctx.job.tool(spec.tool)
            if self.tool_types and tool.type not in self.tool_types:
                raise CamJobError(f"{spec.where}: a {self.name} cuts with a {', '.join(self.tool_types)} tool; "
                                  f"{tool.id} is a {tool.type}")
            if "plunge_mm_min" in getattr(spec, "given", ()) and tool.family != "mill":
                raise CamJobError(f"{spec.where}: a {tool.type} does not plunge (it cuts through the sheet where it "
                                  "starts); remove plunge_mm_min")
        if spec.faces and not self.takes_faces:
            raise CamJobError(f"{spec.where}: a {self.name} takes no faces; remove \"faces\"")
        if spec.region is not None and not self.takes_region:
            raise CamJobError(f"{spec.where}: a {self.name} takes no region; remove \"region\"")
        return dict(spec.extra)

    def shared_keys(self, spec) -> tuple[str, ...]:
        """The shared tuning keys this operation reads for ``spec`` (:attr:`common_keys`; ``rest`` by its ``of``),
        ``plunge_mm_min`` among them exactly when it plunges (:meth:`with_plunge`)."""
        return self.with_plunge(self.common_keys)

    def with_plunge(self, allowed) -> tuple[str, ...]:
        """``allowed`` with ``plunge_mm_min`` in it exactly when this operation reads it: it asks
        :func:`feeds.for_op` for a milling cut (it reads ``feed`` and ``speed``, and its feeds kind plunges:
        :data:`PLUNGE_KINDS`)."""
        allowed = tuple(key for key in allowed if key != "plunge_mm_min")
        if "feed" in allowed and "speed" in allowed and self.feeds_kind in PLUNGE_KINDS:
            allowed += ("plunge_mm_min",)
        return allowed

    def check_common_keys(self, spec, allowed) -> None:
        """Refuse a shared tuning key the job set that this operation never reads (law 9)."""
        allowed = self.with_plunge(allowed)
        stray = [key for key in SHARED if key in getattr(spec, "given", ()) and key not in allowed]
        if stray:
            reads = ", ".join(key for key in SHARED if key in allowed) or "none of them"
            raise CamJobError(f"{spec.where}: a {self.name} does not use {' or '.join(stray)}; remove "
                              f"{'it' if len(stray) == 1 else 'them'} (of the shared tuning keys a {self.name} "
                              f"reads {reads})")

    def plan(self, ctx: PlanContext, params) -> Any:
        raise NotImplementedError

    def summary(self, ctx: PlanContext, params) -> str:
        """``Pocket #o1.f12 with T1 6 mm flat``: the plain word, what it cuts, the tool."""
        faces = ctx.spec.faces
        what = "" if not faces else (" " + ", ".join(faces) if len(faces) <= 3 else f" {len(faces)} faces")
        name = f" ({ctx.spec.name})" if ctx.spec.name else ""
        tool = f" with {ctx.tool.id} {ctx.tool.plain}" if ctx.tool is not None else ""
        return f"{self.plain}{name}{what}{tool}"


def region_polygon(spec, *, where: str):
    """An op's ``region``: ``{"polygon": [[x, y], ...], "bottom_z": z}`` in WCS mm -> (shapely Polygon, bottom z or
    None)."""
    import shapely

    from cadgen._internal.cam.job_errors import number_list, read_number

    raw = spec.region
    if not isinstance(raw, dict):
        raise CamJobError(f"{where}.region must be {{\"polygon\": [[x, y], ...], \"bottom_z\": z}} in the setup's WCS")
    check_keys(raw, ("polygon", "bottom_z"), f"{where}.region")
    points = raw.get("polygon")
    if not isinstance(points, list) or len(points) < 3:
        raise CamJobError(f"{where}.region.polygon needs at least three [x, y] points")
    coords = [number_list(p, f"{where}.region.polygon[{i}]", length=2) for i, p in enumerate(points)]
    polygon = shapely.Polygon(coords)
    if not polygon.is_valid or polygon.area <= 0:
        raise CamJobError(f"{where}.region.polygon crosses itself or has no area")
    bottom = read_number(raw, "bottom_z", f"{where}.region", minimum=-1e6) if "bottom_z" in raw else None
    return polygon, bottom
