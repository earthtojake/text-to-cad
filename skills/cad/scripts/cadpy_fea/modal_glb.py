"""Hand-rolled glTF 2.0 (GLB) writer for animated modal mode shapes.

Produces a *dedicated* tessellated model (separate from the display GLB) whose
base mesh is the undeformed FE surface and which carries one **morph target per
mode** (the per-vertex modal displacement). One glTF **animation clip per mode**
is baked in, oscillating that mode's morph weight as a sine over one loop, so the
GLB self-plays in any glTF viewer (three.js AnimationMixer, Blender, gltf-viewer)
and a host UI can simply pick the clip for a given frequency.

No external glTF dependency — this matches cadpy's hand-rolled GLB writer and
keeps the modal FEA path dependency-light (stdlib + numpy only). Coordinates are
converted to the same Y-up / metre convention as cadpy's native GLB export
(`(x, y, z) -> (x, z, -y)`), so the modal model drops into the viewer's scene
space aligned with the display model.
"""
from __future__ import annotations

import json
import struct
from array import array
from pathlib import Path
from typing import Sequence

import numpy as np

# glTF component types
_FLOAT = 5126
_UINT32 = 5125

# Target (morph) channel path
_DEFAULT_LOOP_SECONDS = 1.2   # visible playback period (NOT the physical period)
_DEFAULT_KEYFRAMES = 33       # samples of one sine loop


def _y_up(points: np.ndarray) -> np.ndarray:
    """CAD Z-up metres -> glTF Y-up: (x, y, z) -> (x, z, -y). Linear, so it also
    applies to displacement *deltas*."""
    out = np.empty_like(points)
    out[:, 0] = points[:, 0]
    out[:, 1] = points[:, 2]
    out[:, 2] = -points[:, 1]
    return out


def _pad(buf: bytearray, alignment: int = 4, fill: int = 0) -> None:
    while len(buf) % alignment:
        buf.append(fill)


def build_modal_glb(
    path: str | Path,
    vertices: np.ndarray,
    triangles: np.ndarray,
    modes: Sequence[dict],
    *,
    loop_seconds: float = _DEFAULT_LOOP_SECONDS,
    keyframes: int = _DEFAULT_KEYFRAMES,
    damping_ratio: float = 0.01,
    material: str | None = None,
) -> Path:
    """Write an animated modal GLB.

    vertices   (N,3) float, undeformed surface in CAD metres (Z-up).
    triangles  (M,3) int, vertex indices.
    modes      list of {"index", "frequencyHz", "label", "displacement": (N,3)}.
               Displacements are in the same units/space as vertices and should
               already be scaled to a visible amplitude (weight=1 => full
               deflection); the baked animation oscillates the weight in [-1, 1].
    """
    path = Path(path)
    vertices = np.asarray(vertices, dtype=np.float64)
    triangles = np.asarray(triangles, dtype=np.uint32)
    if vertices.ndim != 2 or vertices.shape[1] != 3:
        raise ValueError("vertices must be (N,3)")
    if triangles.ndim != 2 or triangles.shape[1] != 3:
        raise ValueError("triangles must be (M,3)")
    if not modes:
        raise ValueError("need at least one mode")

    base = _y_up(vertices).astype(np.float32)

    bin_blob = bytearray()
    buffer_views: list[dict] = []
    accessors: list[dict] = []

    def add_view(data: bytes, target: int | None = None) -> int:
        _pad(bin_blob)
        offset = len(bin_blob)
        bin_blob.extend(data)
        view = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if target is not None:
            view["target"] = target
        buffer_views.append(view)
        return len(buffer_views) - 1

    def add_accessor(view: int, ctype: int, count: int, atype: str,
                     mn=None, mx=None) -> int:
        acc = {"bufferView": view, "componentType": ctype, "count": count, "type": atype}
        if mn is not None:
            acc["min"] = list(mn)
            acc["max"] = list(mx)
        accessors.append(acc)
        return len(accessors) - 1

    # Indices
    idx_view = add_view(triangles.reshape(-1).astype("<u4").tobytes(), target=34963)
    idx_acc = add_accessor(idx_view, _UINT32, int(triangles.size), "SCALAR")

    # Base POSITION (min/max required by spec)
    pos_view = add_view(base.reshape(-1).astype("<f4").tobytes(), target=34962)
    pos_acc = add_accessor(
        pos_view, _FLOAT, int(base.shape[0]), "VEC3",
        mn=base.min(axis=0).tolist(), mx=base.max(axis=0).tolist(),
    )

    # Morph targets: one POSITION-delta accessor per mode
    target_accessors: list[int] = []
    for mode in modes:
        disp = _y_up(np.asarray(mode["displacement"], dtype=np.float64)).astype(np.float32)
        if disp.shape != base.shape:
            raise ValueError("each mode displacement must match vertex count")
        v = add_view(disp.reshape(-1).astype("<f4").tobytes(), target=34962)
        a = add_accessor(
            v, _FLOAT, int(disp.shape[0]), "VEC3",
            mn=disp.min(axis=0).tolist(), mx=disp.max(axis=0).tolist(),
        )
        target_accessors.append(a)

    n_modes = len(modes)

    # Animation time samples (shared input): one sine loop.
    keyframes = max(int(keyframes), 3)
    times = np.linspace(0.0, float(loop_seconds), keyframes).astype(np.float32)
    time_view = add_view(times.astype("<f4").tobytes())
    time_acc = add_accessor(time_view, _FLOAT, keyframes, "SCALAR",
                            mn=[float(times[0])], mx=[float(times[-1])])

    # One animation per mode: weight[i] = sin(2*pi*t/loop), others 0.
    sine = np.sin(2.0 * np.pi * np.linspace(0.0, 1.0, keyframes)).astype(np.float32)
    animations = []
    for mi in range(n_modes):
        weights = np.zeros((keyframes, n_modes), dtype=np.float32)
        weights[:, mi] = sine
        w_view = add_view(weights.reshape(-1).astype("<f4").tobytes())
        w_acc = add_accessor(w_view, _FLOAT, keyframes * n_modes, "SCALAR")
        mode = modes[mi]
        freq = mode.get("frequencyHz")
        label = mode.get("label", "")
        name = f"mode {mode.get('index', mi + 1)}"
        if freq is not None:
            name += f" - {freq:g} Hz"
        if label:
            name += f" ({label})"
        animations.append({
            "name": name,
            "samplers": [{"input": time_acc, "output": w_acc, "interpolation": "LINEAR"}],
            "channels": [{"sampler": 0, "target": {"node": 0, "path": "weights"}}],
        })

    mode_meta = [
        {
            "index": int(m.get("index", i + 1)),
            "frequencyHz": m.get("frequencyHz"),
            "label": m.get("label", ""),
        }
        for i, m in enumerate(modes)
    ]

    gltf = {
        "asset": {"version": "2.0", "generator": "cadpy_fea modal"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0, "name": "modal"}],
        "meshes": [{
            "name": "modal",
            "primitives": [{
                "attributes": {"POSITION": pos_acc},
                "indices": idx_acc,
                "targets": [{"POSITION": a} for a in target_accessors],
            }],
            "weights": [0.0] * n_modes,
            "extras": {
                "modes": mode_meta,
                "loopSeconds": float(loop_seconds),
                "dampingRatio": float(damping_ratio),
                "material": material,
            },
        }],
        "animations": animations,
        "buffers": [{"byteLength": len(bin_blob)}],
        "bufferViews": buffer_views,
        "accessors": accessors,
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")
    json_pad = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad
    bin_pad = (4 - len(bin_blob) % 4) % 4
    bin_blob.extend(b"\x00" * bin_pad)

    total = 12 + 8 + len(json_bytes) + 8 + len(bin_blob)
    out = bytearray()
    out += struct.pack("<III", 0x46546C67, 2, total)            # "glTF", version 2
    out += struct.pack("<II", len(json_bytes), 0x4E4F534A)      # JSON chunk
    out += json_bytes
    out += struct.pack("<II", len(bin_blob), 0x004E4942)        # BIN chunk
    out += bin_blob

    path.write_bytes(out)
    return path
