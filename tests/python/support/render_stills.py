"""What the tests of cadgen's OCCT stills share (``tests/python/packages/cad/engine/test_render*.py``,
and the render process's in ``cad_server``): the picture size and platform, the X variables a test takes
away from a request, the material fixture, a document built and served in this process, and a picture
read and matched against another. A test that draws asks ``gl`` first (``opengl.require``)."""

from __future__ import annotations

import io
import json
import textwrap
from pathlib import Path

import numpy as np

from cad.engine.render import context
from tests.python.support import opengl

SIZE = (320, 240)
PLATFORM = context.platform()  # a row a platform draws apart has a golden of its own there
# What reaches an X display: taken from the engine's environment and its requests, where a test draws with none.
X_VARIABLES = ("DISPLAY", "XAUTHORITY", "WAYLAND_DISPLAY", "CAD_ENGINE_DISPLAY", "CAD_ENGINE_XAUTHORITY")

# The material fixture: a steel block, a brushed aluminium plate, a PLA part with a lacquered top,
# a glass pane, and two placements of one bracket apart by a look alone. Its pane is hinged on the
# plate's back edge, to pose.
BENCH = """
import build123d as bd
from cad.build123d import mechanism_state
from cad.engine import paint, xbf
from bd_materials import FinishedMaterial, metals, plastics, glass
from bd_materials.core import RangeMaterial
from threejs_materials import PbrProperties

LACQUER = FinishedMaterial(RangeMaterial(name="Red lacquer", density=1200),
    pbr=PbrProperties.create("lacquer", color="#cb2727", metalness=0, roughness=0.4,
                             clearcoat=1, clearcoat_roughness=0.05))
STEEL = FinishedMaterial(metals.mild_steel().material,
    pbr=PbrProperties.create("steel", color="#c5c7c8", metalness=1, roughness=0.4))
ALUMINUM = FinishedMaterial(metals.aluminum().material,
    pbr=PbrProperties.create("aluminum", color="#f5f6f6", metalness=1, roughness=0.35, anisotropy=0.3))
PLA = FinishedMaterial(plastics.pla().material,
    pbr=PbrProperties.create("PLA", color="#ededeB", metalness=0, roughness=0.45))
GLASS = FinishedMaterial(glass.soda_lime().material,
    pbr=PbrProperties.create("glass", color="#ffffff", metalness=0, roughness=0.02, ior=1.52,
        transmission=1, attenuation_color=(0.822786, 0.930111, 0.871367), attenuation_distance=0.05))
STAINLESS = FinishedMaterial(metals.stainless().material,
    pbr=PbrProperties.create("stainless", color="#d6d4d1", metalness=1, roughness=0.3, anisotropy=0.3))


@xbf("XBF/bench.xbf")
def bench():
    block = bd.Box(30, 30, 30)
    block.label, block.material = "block", STEEL
    plate = bd.Pos(50, 0, -10) * bd.Box(40, 30, 4)
    plate.label, plate.material = "plate", ALUMINUM
    print_ = bd.Pos(100, 0, 0) * bd.Cylinder(12, 30)
    print_.label, print_.material = "print", PLA
    pane = bd.Box(40, 3, 30, align=(bd.Align.CENTER, bd.Align.MIN, bd.Align.MIN))
    pane.label, pane.material = "pane", GLASS
    pane.color = bd.Color("#ffffff")  # Keep base alpha 1; transmission is the material's.
    paint(print_, print_.faces().sort_by(bd.Axis.Z)[-1], LACQUER)
    left = bd.Pos(0, -50, 0) * bd.Box(10, 10, 10)
    left.label, left.material = "left", STAINLESS
    right = left.moved(bd.Location((20, 0, 0)))
    right.label, right.material = "right", FinishedMaterial(STAINLESS.material, pbr=STAINLESS.pbr.override(roughness=0.2, anisotropy=0))
    bd.RevoluteJoint("hinge", plate, axis=bd.Axis((0, 15, 2), (1, 0, 0)), angular_range=(-90, 90))
    bd.RigidJoint("foot", pane, joint_location=bd.Location((0, 0, 0), (0, 90, 0)))
    plate.joints["hinge"].connect_to(pane.joints["foot"], angle=0)
    root = bd.Compound(children=[block, plate, print_, pane, left, right], label="bench")
    return mechanism_state(root, "open", hinge=60)
"""


def gl() -> None:
    """Skip, saying why, where no OpenGL context can be made (on CI with a display, fail)."""
    opengl.require(context.available())


def pixels(data: bytes) -> np.ndarray:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as image:
        return np.asarray(image.convert("RGB")).astype(np.int16)


def mismatch(found: np.ndarray, golden: np.ndarray) -> float:
    """The share of ``found``'s pixels more than 32 levels (in some channel) from every pixel of
    ``golden`` within one pixel of them."""
    if found.shape != golden.shape:
        return 1.0
    height, width = golden.shape[:2]
    padded = np.pad(golden, ((1, 1), (1, 1), (0, 0)), mode="edge")
    best = np.full((height, width), 255, np.int16)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            best = np.minimum(best, np.abs(found - padded[dy:dy + height, dx:dx + width]).max(-1))
    return float((best > 32).mean())


def drawn(data: bytes, size: tuple[int, int]) -> np.ndarray:
    """The picture: PNG, the size asked, and more than its backdrop."""
    found = pixels(data)
    assert data[:8] == b"\x89PNG\r\n\x1a\n" and found.shape == (size[1], size[0], 3), found.shape
    backdrop = found[0, 0]
    assert (np.abs(found - backdrop).max(-1) > 8).mean() > 0.01, "a backdrop alone"  # a line drawing covers little
    return found


def shapes(structure: dict) -> int:
    """How many parts a renderer makes shapes of: one per geometry and paints (the fixture's two
    brackets, one geometry apart by a material alone, are one)."""
    return len({(p["key"], json.dumps(p.get("faceColors") or {}, sort_keys=True)) for p in structure["prototypes"]})


def build(folder: Path, source: str, name: str) -> Path:
    from cad.engine import build as engine_build

    script = folder / f"{name}.py"
    script.write_text(textwrap.dedent(source), encoding="utf-8")
    reports = engine_build.build(script, None, cwd=folder)
    assert all(report["ok"] for report in reports), reports
    return folder / f"XBF/{name}.xbf"


def served(document: Path) -> tuple[dict, dict[str, bytes]]:
    """The document as the engine serves it, and every part's buffer, meshed in this process."""
    from cad.engine.serve import Server

    server = Server(mesh_mode="inline")
    try:
        doc = server.document(server.add(document))
        server.mesh_all(doc, None)
        structure = server.structure(doc)
        return structure, {p["key"]: server.cache.get(p["key"]) for p in structure["prototypes"]}
    finally:
        server.stop()
