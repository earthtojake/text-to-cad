"""A harness document as the picture the CAD Viewer draws: WireViz's own diagram.

WireViz draws it: ``wireviz`` (with Graphviz's ``dot``) renders the document
to SVG, and the payload carries that SVG unchanged, as one sheet. It is the
plot payload a KiCad board's is (``cadgen.plot``: the same schema
version, the same sheet fields), so the viewer and ``cadgen snapshot`` draw a
harness the way they draw a board: ``{schemaVersion, kind: "harness",
unrouted: null, sheets: [{name, svg, width, height, background}]}``, sizes in
millimetres (Graphviz measures in points).

Everything runs on a staged copy of the document's bytes. The payload is
derived data: cached in the store's ``drawing`` index, keyed by those bytes,
this module's scheme, and the WireViz and Graphviz versions that drew it.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from cadgen.plot import PLOT_SCHEMA_VERSION, PlotError
from cadgen.viewer.content_types import extension_of, format_of

__all__ = ["HARNESS_BACKGROUND", "build_plot", "plot_payload_bytes"]

#: WireViz's default page colour, behind a diagram whose document sets none.
HARNESS_BACKGROUND = "#ffffff"
_POINT_MM = 25.4 / 72.0
_SHEET = "harness"


def _stem(path: Path) -> str:
    return path.name[: -len(extension_of(path))]


def _size_mm(svg: str) -> tuple[float, float]:
    match = re.search(r'<svg\b[^>]*?\bwidth="([\d.]+)pt"[^>]*?\bheight="([\d.]+)pt"', svg, re.DOTALL)
    if match is None:
        raise PlotError("WireViz's diagram has no size in points")
    return round(float(match.group(1)) * _POINT_MM, 4), round(float(match.group(2)) * _POINT_MM, 4)


def _background(svg: str) -> str:
    # Graphviz paints the page first: the graph's own polygon, filled with its bgcolor.
    match = re.search(r'<g id="graph0"[^>]*>\s*(?:<title>[^<]*</title>\s*)?<polygon fill="(#[0-9a-fA-F]{6})" stroke="none"', svg)
    return match.group(1).lower() if match else HARNESS_BACKGROUND


def _checked(path: Path) -> Path:
    path = Path(path).resolve()
    if format_of(path) != "harness":
        raise PlotError(f"{path.name} is not a harness document (.harness.yml)")
    if not path.is_file():
        raise PlotError(f"{path.name} does not exist")
    return path


def build_plot(path: Path, *, install=None, document: bytes | None = None) -> dict:
    """The plot payload of the harness document at ``path``."""
    from cadgen.wireviz.cli import WirevizRunError, run_wireviz
    from cadgen.wireviz.install import find_wireviz

    path = _checked(path)
    install = install or find_wireviz()
    data = document if document is not None else path.read_bytes()
    try:
        written = run_wireviz(install, data, formats="s", name=_SHEET)
    except WirevizRunError as error:
        raise PlotError(f"WireViz could not draw {path.name}: {error}") from None
    svg_bytes = written.get(f"{_SHEET}.svg")
    if not svg_bytes:
        raise PlotError(f"WireViz drew nothing for {path.name}")
    svg = svg_bytes.decode("utf-8")
    width, height = _size_mm(svg)
    return {
        "schemaVersion": PLOT_SCHEMA_VERSION,
        "kind": "harness",
        "wirevizVersion": install.version,
        "sheets": [{"name": _stem(path), "svg": svg, "width": width, "height": height, "background": _background(svg)}],
        "unrouted": None,
    }


def plot_payload_bytes(path: Path) -> bytes:
    """The payload as JSON bytes, from the store when these bytes were drawn before."""
    from cadgen.store import drawings
    from cadgen.wireviz.install import find_wireviz

    path = _checked(path)
    install = find_wireviz()
    document = path.read_bytes()
    scheme = f"wireviz-plot:{PLOT_SCHEMA_VERSION}:{install.version}:{install.graphviz_version}"
    key = drawings.drawing_input_key(hashlib.sha256(document).hexdigest(), scheme=scheme)
    cached = drawings.read(key)
    if cached is not None:
        return cached
    data = json.dumps(build_plot(path, install=install, document=document), separators=(",", ":")).encode("utf-8")
    drawings.write(key, data)
    return data
