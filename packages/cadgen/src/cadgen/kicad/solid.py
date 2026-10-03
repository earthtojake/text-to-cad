"""A board as build123d geometry: the populated board KiCad builds in 3D.

A ``@pcb`` model that declares a 3D export (``@step``, ``@glb``, ``@stl``,
``@threemf``) is a geometry model whose tree is its populated board. KiCad
builds that board -- the outline extruded to the board's thickness and
drilled, each footprint's STEP model placed on its side -- with
``kicad-cli pcb export step``; this module runs it on a staged copy and reads
the result back as build123d geometry.

The export is taken from the board's drill/place origin, which cadgen puts at
the board script's own (0, 0): the geometry lands in the script's coordinates,
x and y as the outline was drawn and z = 0 on the board's bottom face, so an
enclosure modelled around the same outline composes the board with no
transform. Each part is labelled with its reference (``R1``); the board body
is labelled ``board``. Parts marked DNP are left out, as they are left off the
board.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

__all__ = ["BOARD_BODY_LABEL", "board_solid"]

BOARD_BODY_LABEL = "board"


def board_solid(pcb_path: Path, *, name: str, install=None):
    """The populated board at ``pcb_path`` as a build123d ``Compound`` labelled ``name``."""
    from cadgen.kicad.cli import run_kicad_cli
    from cadgen.kicad.install import find_kicad

    install = install or find_kicad()
    pcb_path = Path(pcb_path)
    with tempfile.TemporaryDirectory(prefix="cadgen-pcb-solid-") as folder:
        stage = Path(folder)
        shutil.copy2(pcb_path, stage / pcb_path.name)
        project = pcb_path.with_suffix(".kicad_pro")
        if project.is_file():
            shutil.copy2(project, stage / project.name)
        run_kicad_cli(
            install,
            ["pcb", "export", "step", "--drill-origin", "--subst-models", "--no-dnp", "--force", "-o", "board.step", pcb_path.name],
            cwd=stage,
        )
        exported = stage / "board.step"
        if not exported.is_file() or exported.stat().st_size == 0:
            raise RuntimeError(f"KiCad exported no 3D board for {pcb_path.name}")
        # cadgen's own reader, not build123d's: it keeps each occurrence's instance
        # name (KiCad writes the reference, R1) where build123d keeps the product's
        # (the footprint name), and it carries the STEP's colours.
        from cadgen._internal.step_scene_mesh import import_step

        shape = import_step(exported)
    children = list(getattr(shape, "children", ()) or ())
    for child in children:
        label = str(getattr(child, "label", "") or "")
        if not label or label.startswith("=>"):
            child.label = BOARD_BODY_LABEL
    shape.label = name
    return shape
