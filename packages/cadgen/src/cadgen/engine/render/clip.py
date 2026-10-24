"""The viewer's Clip, drawn by OCCT (``occt.py``'s ``Scene._clip``): one plane cutting the model
and its cut capped, as core's ``lib/viewer/sectionCaps.js`` caps it.

**The viewer.** ``display.clip`` is one plane along an axis, at ``at`` (else the middle of the
model at rest), keeping the lower side (``invert`` the upper). Each mesh is capped where it is cut
by a stencil pass and an unlit plane (``MeshBasicMaterial``) in the mesh's own colour, or in
#e9a451 when ``partColors`` is false: a flat fill, hiding whatever is behind the cut, lit by
nothing. The grid is never cut (``grid.unclipped``).

**Why OCCT needs carriers.** OCCT caps a closed group of a presentation cut by a capping plane
(``OpenGl_CappingAlgo``). A part here is triangulation-only faces (``shapes.py``), which OCCT's
presentation builder marks open, so it caps nothing: what showed in the cut was the part's lit
inside. So the view's plane cuts with capping off, and each instance carries its cap on a
presentation of its own -- a carrier:

- one ``AIS_Shape`` of the part's whole surface per prototype (its one face, or for a painted
  part one face crafted from its mesh), shown per instance by ``AIS_ConnectedInteractive`` as the
  part is, its presentation's groups drawn with an empty fill aspect (nothing of the carrier is
  drawn but its cap) and marked closed;
- each carrier's connected object its own clip plane list, overriding the view's: the same plane,
  capping on, the cap unlit (no object material, texture or shader) in the cap's colour, one plane
  per colour shared by the instances of that colour.

The cap's colour is the instance's -- its colour or its part's, else the look's fill; the palette's
colour in Parts -- linear and raised to ``LOOK.colour_power`` as a lit face's albedo is (power 1 in
Preview's PBR); #e9a451 as it is (sRGB) when ``partColors`` is false. Wireframe draws no faces and so
no caps. The carriers' connected objects join ``scene.shown``, so the next ``show`` takes them away
with the rest; a carrier lives with its scene (a version patched is a scene made again).

OCCT's path tracer (``--path-trace``) cuts nothing by the view's clip plane and draws an empty-fill
carrier as a solid, so a path-traced picture has its caps withdrawn (``withdraw``) and is uncut.
"""

from __future__ import annotations

import time
from typing import Any

import numpy as np

from cadgen.engine.render.look import LOOK

CAP = "#e9a451"  # the viewer's cap when it is not in the part's colour


def plane(scene: Any, clip: dict[str, Any]) -> Any:
    """The clip's plane (``gp_Pln``), its normal pointing into the half the cut keeps (OCCT keeps
    the half-space the normal points into)."""
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt

    axis = "xyz".index(clip.get("axis", "x"))
    low, high = scene.rest_bounds()
    at = float(clip.get("at", (low[axis] + high[axis]) / 2))
    normal, point = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
    normal[axis] = 1.0 if clip.get("invert") else -1.0
    point[axis] = at
    return gp_Pln(gp_Pnt(*point), gp_Dir(*normal))


def _linear(value: Any) -> np.ndarray:
    """A ``#rrggbb`` (sRGB) or an rgb(a) tuple (linear) as linear RGB."""
    if isinstance(value, str):
        from cadgen.engine.render.grid import hex_colour, to_linear

        return to_linear(hex_colour(value))
    return np.asarray(value[:3], float)


def cap_colour(scene: Any, index: int, clip: dict[str, Any]) -> tuple[float, float, float]:
    """Instance ``index``'s cap colour, linear, as the frame buffer is to hold it."""
    if clip.get("partColors", True) is False:
        return tuple(float(c) for c in _linear(CAP))  # type: ignore[return-value]
    from cadgen.engine.render.occt import PARTS

    instance = scene.structure["instances"][index]
    if scene.mode == "parts":
        rgba: Any = PARTS[instance.get("palette", index) % len(PARTS)]
    else:
        rgba = instance.get("color") or scene.prototypes[instance["prototype"]].get("color") or LOOK.fill
    power = 1.0 if scene.preview else LOOK.colour_power
    return tuple(round(float(c), 6) for c in np.clip(_linear(rgba), 0, 1) ** power)  # type: ignore[return-value]


def _surface(scene: Any, p: int) -> Any:
    """Prototype ``p``'s whole surface as one shape: its one face, else a face crafted from its mesh."""
    faces = scene.parts[p].faces
    if len(faces) == 1:
        return next(iter(faces.values()))
    from cadgen.engine.render.shapes import craft, read

    mesh = scene.meshes[scene.prototypes[p]["key"]]
    triangles = np.asarray(mesh.indices, np.int64).reshape(-1, 3)
    if not len(triangles):
        return None
    return read(craft([(mesh.positions, triangles, mesh.normals)], {}))


def _carrier(scene: Any, p: int) -> Any:
    carriers = scene.carriers
    if p not in carriers:
        from OCP.AIS import AIS_Shape

        surface = _surface(scene, p)
        carriers[p] = AIS_Shape(surface) if surface is not None else None
    return carriers[p]


def _hollow(scene: Any, carrier: Any) -> None:
    """The carrier's presentation drawn as nothing but its cap: every group an empty fill, closed.
    Done again whenever OCCT has computed the presentation afresh (its groups open again)."""
    from OCP.Aspect import Aspect_InteriorStyle
    from OCP.Graphic3d import Graphic3d_AspectFillArea3d

    presentation = scene.canvas.context.MainPrsMgr().Presentation(carrier, 1)
    if presentation is None:
        return
    groups = presentation.Groups()  # by Size and Value: listing the sequence costs milliseconds a call
    count = groups.Size()
    if not count or groups.Value(1).IsClosed():
        return
    for at in range(1, count + 1):
        group = groups.Value(at)
        empty = Graphic3d_AspectFillArea3d()
        empty.SetInteriorStyle(Aspect_InteriorStyle.Aspect_IS_EMPTY)
        group.SetGroupPrimitivesAspect(empty)
        group.SetClosed(True)


def _planes(cut: Any, colour: tuple[float, float, float]) -> Any:
    """A carrier's own plane list: the cut, capping in ``colour`` (linear), unlit."""
    from OCP.Aspect import Aspect_InteriorStyle
    from OCP.Graphic3d import (Graphic3d_AspectFillArea3d, Graphic3d_ClipPlane, Graphic3d_SequenceOfHClipPlane,
                               Graphic3d_TypeOfShadingModel)
    from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB

    capping = Graphic3d_ClipPlane(cut)
    capping.SetCapping(True)
    capping.SetUseObjectMaterial(False)
    capping.SetUseObjectTexture(False)
    capping.SetUseObjectShader(False)
    aspect = Graphic3d_AspectFillArea3d()
    aspect.SetInteriorStyle(Aspect_InteriorStyle.Aspect_IS_SOLID)
    aspect.SetShadingModel(Graphic3d_TypeOfShadingModel.Graphic3d_TypeOfShadingModel_Unlit)
    aspect.SetInteriorColor(Quantity_Color(*colour, Quantity_TOC_RGB))
    capping.SetCappingAspect(aspect)
    planes = Graphic3d_SequenceOfHClipPlane()
    planes.SetOverrideGlobal(True)
    planes.Append(capping)
    return planes


def apply(scene: Any, clip: dict[str, Any] | None) -> float:
    """``display.clip`` on the scene just shown (``Scene.show``): the view's plane cutting, and a
    capped carrier per instance shown; or no plane. The seconds it took."""
    from OCP.AIS import AIS_ConnectedInteractive
    from OCP.Graphic3d import Graphic3d_ClipPlane, Graphic3d_SequenceOfHClipPlane

    from cadgen.engine.render.occt import _trsf

    clock = time.perf_counter()
    scene.caps = []
    view = scene.canvas.view
    view.SetClipPlanes(Graphic3d_SequenceOfHClipPlane())
    if not clip or clip.get("enabled") is False:
        return time.perf_counter() - clock
    cut = plane(scene, clip)
    cutting = Graphic3d_ClipPlane(cut)
    cutting.SetCapping(False)
    view.AddClipPlane(cutting)
    if scene.mode == "wireframe":
        return time.perf_counter() - clock
    context = scene.canvas.context
    lists: dict[tuple[float, float, float], Any] = {}
    hollowed: set[int] = set()
    for index, instance in enumerate(scene.structure["instances"]):
        if index in getattr(scene, "hidden", ()):
            continue
        p = instance["prototype"]
        carrier = _carrier(scene, p)
        if carrier is None:
            continue
        colour = cap_colour(scene, index, clip)
        if colour not in lists:
            lists[colour] = _planes(cut, colour)
        connected = AIS_ConnectedInteractive()
        connected.Connect(carrier, _trsf(scene.placement(index)))
        connected.SetClipPlanes(lists[colour])
        context.Display(connected, 1, -1, False)
        scene.shown.append(connected)
        scene.caps.append(connected)
        if p not in hollowed:
            _hollow(scene, carrier)
            hollowed.add(p)
    seconds = time.perf_counter() - clock
    scene.timings["caps"] = seconds
    return seconds


def withdraw(scene: Any) -> None:
    """The caps taken away: OCCT's path tracer cuts nothing by a clip plane and would draw each
    carrier whole, as a solid over its part."""
    context = scene.canvas.context
    for connected in scene.caps:
        context.Remove(connected, False)
    scene.shown = [shown for shown in scene.shown if not any(shown is cap for cap in scene.caps)]
    scene.caps = []
