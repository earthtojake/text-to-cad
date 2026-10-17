#!/usr/bin/env python3
"""Draw a planar slice of a cadjoint scene's signed distance field as a PNG.

Requires: Python 3.11+, cadjoint, jax (install requirements.txt)

Usage:
    python cadjoint_slice.py SCENE.py OUT.png [--object scene] [--axis z] [--at 0]
        [--step 2] [--pixels 900] [--bounds U0 V0 U1 V1]

The slice is the plane `axis = at`, drawn with the other two axes across and
up (x: y across, z up; y: x across, z up; z: x across, y up). Inside the
part (negative distance) is blue, outside is orange, darker with distance;
thin lines are iso-distance contours every `--step` model units and the
thick black line is the surface itself, distance zero.

What it is for: a mesh shows where the surface is, the field shows how far
everything is from it. Read wall thickness as twice the deepest blue
contour inside a wall, see how far a blend reaches from a seam, and find a
feature that vanished below the mesh resolution, all without meshing.

The plane's extent comes from cadjoint's `fit_bounds`, as the export's does, unless
`--bounds` gives it in the slice's own across/up coordinates. Prints one
JSON object with the extent, the pixel size and the field's range in the
slice; exits 1 with `{"ok": false, "error": ...}` on failure.
"""

from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

AXES = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}  # (across, up) per slice axis
INSIDE = (38, 92, 168)
OUTSIDE = (226, 120, 38)
PAPER = (247, 247, 245)


def write_png(path: Path, rgb) -> None:
    """Write an (H, W, 3) uint8 array as a PNG, with nothing but zlib."""
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    )


def colour(distance, pixel: float, step: float):
    """Shade by side and depth, then draw contours every step and the zero line.

    Inside and outside are scaled separately, so a 2 mm wall stays visibly
    blue next to 30 mm of air. Lines are drawn where the field crosses a
    contour value within half a pixel, measured with the field's own
    gradient, so they stay one pixel wide where the field changes slowly (a
    cavity's medial axis) and are left out where it does not change at all.
    """
    import numpy as np

    inside = distance < 0
    depth = np.zeros_like(distance)
    if inside.any():
        depth[inside] = -distance[inside] / max(float(-distance.min()), 1e-12)
    if (~inside).any():
        depth[~inside] = distance[~inside] / max(float(distance.max()), 1e-12)
    depth = np.clip(depth, 0.0, 1.0)[..., None] ** 0.6
    tint = np.where(inside[..., None], np.asarray(INSIDE), np.asarray(OUTSIDE))
    rgb = np.asarray(PAPER) * (1 - 0.8 * depth) + tint * 0.8 * depth

    gy, gx = np.gradient(distance, pixel)
    gradient = np.hypot(gx, gy)
    slope = np.maximum(gradient, 1e-3) * pixel  # field change per pixel
    offset = distance / step - np.round(distance / step)
    # Where the field is flat in this plane -- a slice along a wall's
    # mid-plane reads the same distance everywhere -- a contour has no
    # position, so none is drawn rather than a filled patch.
    varies = gradient > 0.05
    contour = varies & (np.abs(offset) * step < 0.5 * slope) & (np.abs(distance) > slope)
    rgb[contour] = rgb[contour] * 0.55
    rgb[np.abs(distance) < 1.2 * slope] = (0, 0, 0)
    return np.clip(rgb, 0, 255).astype(np.uint8)


def slice_field(scene: Path, out: Path, name: str, axis: str, at: float, step, pixels: int, bounds):
    import jax.numpy as jnp
    import numpy as np

    from cadjoint.meshing.bounds import fit_bounds
    from cadjoint_export import load_object

    obj = load_object(scene, name)
    sdf = lambda points: jnp.asarray(obj(jnp.asarray(points)))  # noqa: E731
    across, up = AXES[axis]
    if bounds is None:
        origin, extent = fit_bounds(sdf)
        u0, v0 = origin[across], origin[up]
        u1, v1 = u0 + extent[across], v0 + extent[up]
    else:
        u0, v0, u1, v1 = bounds
    if u1 <= u0 or v1 <= v0:
        raise ValueError("--bounds needs U0 < U1 and V0 < V1")
    pixel = max(u1 - u0, v1 - v0) / pixels
    width = max(1, round((u1 - u0) / pixel))
    height = max(1, round((v1 - v0) / pixel))
    u = u0 + (np.arange(width) + 0.5) * pixel
    v = v1 - (np.arange(height) + 0.5) * pixel  # image rows run downward
    uu, vv = np.meshgrid(u, v)
    points = np.zeros((height, width, 3), dtype=np.float32)
    points[..., across] = uu
    points[..., up] = vv
    points[..., "xyz".index(axis)] = at
    distance = np.asarray(sdf(points.reshape(-1, 3))).reshape(height, width)
    if step is None:
        step = float(np.round(max(u1 - u0, v1 - v0) / 20.0, 1)) or pixel * 10
    write_png(out, colour(distance, pixel, step))
    return {
        "ok": True,
        "path": str(out.resolve()),
        "object": name,
        "plane": f"{axis} = {at:g}",
        "across": "xyz"[across],
        "up": "xyz"[up],
        "extent": [[u0, v0], [u1, v1]],
        "pixel": pixel,
        "contour_step": step,
        "field_range": [float(distance.min()), float(distance.max())],
        "crosses_surface": bool(distance.min() < 0 < distance.max()),
    }


def main(argv: list[str] | None = None) -> int:
    if sys.version_info < (3, 11):
        print(json.dumps({
            "ok": False,
            "error": f"Python {sys.version.split()[0]} is too old; cadjoint needs 3.11 or newer "
            "(create the environment with `uv venv --managed-python --python 3.12`).",
        }))
        return 1
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("scene", type=Path, help="cadjoint scene file (.py)")
    parser.add_argument("out", type=Path, help="output .png")
    parser.add_argument("--object", default="scene", help="name the scene binds the SDF to")
    parser.add_argument("--axis", choices=sorted(AXES), default="z", help="slice normal")
    parser.add_argument("--at", type=float, default=0.0, help="slice position along the axis")
    parser.add_argument("--step", type=float, help="contour spacing (default: extent / 20)")
    parser.add_argument("--pixels", type=int, default=900, help="pixels along the longer side")
    parser.add_argument(
        "--bounds", type=float, nargs=4, metavar=("U0", "V0", "U1", "V1"),
        help="the slice's extent in its across/up coordinates instead of the scan",
    )
    args = parser.parse_args(argv)
    if not 64 <= args.pixels <= 4096:
        parser.error("--pixels must be between 64 and 4096")
    try:
        report = slice_field(
            args.scene, args.out, args.object, args.axis, args.at, args.step, args.pixels,
            args.bounds,
        )
    except Exception as error:  # noqa: BLE001 - every failure is reported as JSON
        print(json.dumps({"ok": False, "error": f"{type(error).__name__}: {error}"}))
        return 1
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
