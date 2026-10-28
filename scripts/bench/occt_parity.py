#!/usr/bin/env python3
"""How alike the CAD Viewer and the OCCT prototype draw the regular display modes.

A manual measurement, never run in CI; what it writes goes under an ignored folder
(``tmp/bench/occt-parity`` by default). Each document is drawn in every mode and camera
asked for, twice: by OCCT's raster (``python -m cadgen.engine.render.occt``'s ``Scene``, the
reference: ``engine/render/look.py`` is its look) and by the snapshot page the viewer's
code draws (the snapshot page, the xbf family of ``headlessScene.js``, built and driven here), both from
the engine daemon's meshes, at one size. Per picture pair it reports:

- ``iou``: the silhouettes' intersection over union (a pixel is the model's where it is not the
  backdrop);
- ``de_median``, ``de_p95``: CIE76 colour difference (sRGB to Lab, D65) over the pixels both
  pictures give the model;
- ``line_diff``: the share of the pixels either picture inks (not backdrop) where the two differ
  by more than a just-visible ΔE of 10 -- the line modes' measure.

And the top-face hue check: on the up-facing faces (normal within 25 degrees of +Z) of every
saturated metal (a material with metallic >= 0.5 whose colour's CIELab chroma is at least 10),
points the camera sees (no triangle in front of them), sampled in Solid and Shaded at iso: each
point's hue against its material's colour (CIELab hue angle, degrees) and its chroma over the
colour's, per renderer -- a metal washed out to cream or white keeps neither.

The bench's ``--preview`` adds its internal photographic comparison at each camera
(``preview-iso``, ...): OCCT's ``render/service.py`` ``Held`` rig, the page's with the job's
``"preview": true``. Its studio is no flat backdrop, so the model's pixels are those where OCCT's
picture differs from its own studio drawn without the model (``preview-<camera>-studio.png``), and
ΔE is measured there alone: a difference of studio or shadow is not the model's, and IoU is n/a.

It writes each picture, ``metrics.json`` (``hue`` beside the rows) and a contact sheet per document
(Chromium, OCCT and the ΔE map side by side, at most 1800 px wide), and prints both tables.

    PYTHONPATH=packages/cadgen/src .venv/bin/python scripts/bench/occt_parity.py \\
        --doc fixture=path/to/bench.xbf --doc motorbike=models/motorbike/XBF/motorbike.xbf \\
        --out tmp/bench/occt-parity/after

``--only chromium`` keeps the OCCT pictures already in ``--out`` (the reference does not move
while the viewer is tuned); ``--modes`` and ``--cameras`` narrow the set. The daemon serves and
meshes each document (``CADGEN_ENGINE_DIR`` chooses which daemon); macOS only, as the
prototype's GL context is.
"""

from __future__ import annotations

import argparse
import base64
import json
import math
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

MODES = ("solid", "shaded", "parts", "xray", "hidden-line", "wireframe")
CAMERAS = ("iso", "front")
LINE_MODES = ("hidden-line", "wireframe")
SILHOUETTE_TOLERANCE = 6  # a pixel is the model's when a channel is this far from the backdrop
VISIBLE_DE = 10.0


# --- measures (pure: numpy arrays in, numbers out) ---------------------------------------------


def srgb_to_lab(pixels: np.ndarray) -> np.ndarray:
    """8-bit sRGB (..., 3) to CIE Lab under D65."""
    c = np.asarray(pixels, float) / 255.0
    linear = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750],
                             [0.0193339, 0.1191920, 0.9503041]]).T
    xyz = xyz / np.array([0.95047, 1.0, 1.08883])
    delta = 6 / 29
    f = np.where(xyz > delta ** 3, np.cbrt(xyz), xyz / (3 * delta ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def silhouette(pixels: np.ndarray, backdrop: Any) -> np.ndarray:
    """Where ``pixels`` are the model's: off the backdrop, a colour or a picture of it alone."""
    return np.abs(np.asarray(pixels, int) - np.asarray(backdrop, int)).max(-1) > SILHOUETTE_TOLERANCE


def compare(left: np.ndarray, right: np.ndarray, backdrop: Any, *, mask: np.ndarray | None = None) -> dict[str, float]:
    """The measures of one picture pair (two HxWx3 uint8 arrays of one size) over ``backdrop``.
    ``mask``: the model's pixels given (Preview's, OCCT's own), measured there alone, IoU n/a."""
    de = np.linalg.norm(srgb_to_lab(left) - srgb_to_lab(right), axis=-1)
    if mask is not None:
        return {"iou": float("nan"),
                "de_median": float(np.median(de[mask])) if mask.any() else float("nan"),
                "de_p95": float(np.percentile(de[mask], 95)) if mask.any() else float("nan"),
                "line_diff": float((de[mask] > VISIBLE_DE).mean()) if mask.any() else 0.0}
    a, b = silhouette(left, backdrop), silhouette(right, backdrop)
    union, both = np.logical_or(a, b), np.logical_and(a, b)
    found = {"iou": float(both.sum() / union.sum()) if union.any() else 1.0,
             "de_median": float(np.median(de[both])) if both.any() else float("nan"),
             "de_p95": float(np.percentile(de[both], 95)) if both.any() else float("nan"),
             "line_diff": float((de[union] > VISIBLE_DE).mean()) if union.any() else 0.0}
    return found


def iou(found: dict[str, float]) -> str:
    return "n/a" if math.isnan(found["iou"]) else f"{found['iou']:.3f}"


def linear_to_srgb(values: np.ndarray) -> np.ndarray:
    values = np.clip(np.asarray(values, float), 0, 1)
    return np.where(values <= 0.0031308, values * 12.92, 1.055 * values ** (1 / 2.4) - 0.055) * 255


def hue_chroma(lab: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return np.degrees(np.arctan2(lab[..., 2], lab[..., 1])), np.hypot(lab[..., 1], lab[..., 2])


def hue_check(samples: list[dict], picture: np.ndarray) -> dict[str, float]:
    """``samples`` (pixel ``x``, ``y`` and the material's linear ``colour``) read in ``picture``: the
    median absolute hue difference (degrees) and the median chroma ratio, over 3 x 3 medians."""
    if not samples:
        return {"samples": 0, "hue_median": float("nan"), "hue_max": float("nan"), "chroma_ratio": float("nan")}
    height, width = picture.shape[:2]
    differences, ratios = [], []
    for sample in samples:
        x, y = int(round(sample["x"])), int(round(sample["y"]))
        window = picture[max(y - 1, 0):min(y + 2, height), max(x - 1, 0):min(x + 2, width)].reshape(-1, 3)
        seen = srgb_to_lab(np.median(window, 0))
        wanted = srgb_to_lab(linear_to_srgb(sample["colour"]))
        (hue, chroma), (want_hue, want_chroma) = hue_chroma(seen), hue_chroma(wanted)
        differences.append(abs((float(hue - want_hue) + 180) % 360 - 180))
        ratios.append(float(chroma / want_chroma))
    return {"samples": len(samples), "hue_median": float(np.median(differences)), "hue_max": float(np.max(differences)),
            "chroma_ratio": float(np.median(ratios))}


def metal_tops(structure: dict, buffers: dict, scene, limit: int = 48) -> list[dict]:
    """Points the framed camera sees on the up-facing faces of saturated metals, as ``hue_check``
    reads them: each the centroid of a face's largest up-facing triangle, placed and projected
    through ``scene`` (the OCCT prototype's, framed), visible when no placed triangle covers it
    nearer the camera."""
    from cadgen.engine.mesh import Mesh

    prototypes, camera = structure["prototypes"], scene.camera
    toward, right, up = (np.asarray(camera[key], float) for key in ("direction", "right", "up"))
    meshes = {key: Mesh.from_bytes(buffers[key]) for key in {p["key"] for p in prototypes}}
    placed, candidates = [], []
    for index, instance in enumerate(structure["instances"]):
        prototype = prototypes[instance["prototype"]]
        mesh, matrix = meshes[prototype["key"]], scene.placement(index)
        world = mesh.positions.astype(float) @ matrix[:3, :3].T + matrix[:3, 3]
        triangles = world[np.asarray(mesh.indices, np.int64).reshape(-1, 3)]
        placed.append(triangles)
        material = prototype.get("material") or {}
        colour = (material.get("color") or prototype.get("color") or [0, 0, 0])[:3]
        if float(material.get("metallic") or 0) < 0.5 or hue_chroma(srgb_to_lab(linear_to_srgb(colour)))[1] < 10:
            continue
        faces = np.asarray(mesh.faces, np.int64).reshape(-1, 3)
        for _ordinal, first, count in faces:
            if not count:
                continue
            face = triangles[first // 3:(first + count) // 3]
            normals = np.cross(face[:, 1] - face[:, 0], face[:, 2] - face[:, 0])
            areas = np.linalg.norm(normals, axis=1)
            best = int(np.argmax(areas))
            if areas[best] <= 0 or normals[best, 2] / areas[best] < math.cos(math.radians(25)):
                continue
            candidates.append((areas[best], face[best].mean(0), [float(c) for c in colour]))
    triangles = np.concatenate(placed)
    screen = np.stack([triangles @ right, triangles @ up], -1)
    low, high = screen.min(1), screen.max(1)
    samples = []
    for _area, point, colour in sorted(candidates, key=lambda found: -found[0]):
        at = np.array([point @ right, point @ up])
        near = np.flatnonzero((low[:, 0] <= at[0]) & (high[:, 0] >= at[0]) & (low[:, 1] <= at[1]) & (high[:, 1] >= at[1]))
        v0, v1, v2 = (triangles[near, k] for k in range(3))
        e1, e2 = v1 - v0, v2 - v0
        p = np.cross(toward, e2)
        det = (e1 * p).sum(1)
        ok = np.abs(det) > 1e-12
        inv = np.where(ok, 1 / np.where(ok, det, 1), 0)
        t0 = point - v0
        u = (t0 * p).sum(1) * inv
        q = np.cross(t0, e1)
        v = (q @ toward) * inv
        t = (e2 * q).sum(1) * inv
        size = float(np.linalg.norm(e1, axis=1).max()) if len(near) else 1.0
        if np.any(ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 1e-4 * max(size, 1.0))):
            continue
        x, y = scene.project(point[None])[0]
        samples.append({"x": float(x), "y": float(y), "colour": colour})
        if len(samples) >= limit:
            break
    return samples


def delta_map(left: np.ndarray, right: np.ndarray, scale: float = 20.0) -> np.ndarray:
    """The ΔE of each pixel as a picture: white 0, through yellow to red at ``scale``."""
    de = np.clip(np.linalg.norm(srgb_to_lab(left) - srgb_to_lab(right), axis=-1) / scale, 0, 1)
    out = np.empty(de.shape + (3,), np.uint8)
    out[..., 0] = 255
    out[..., 1] = (255 * (1 - np.clip(de * 2 - 1, 0, 1)) * 1).astype(np.uint8)
    out[..., 2] = (255 * (1 - np.clip(de * 2, 0, 1))).astype(np.uint8)
    return out


# --- drawing ----------------------------------------------------------------------------------


def draw_occt(doc: Path, folder: Path, modes: list[str], cameras: list[str], size: tuple[int, int],
              preview: bool = False) -> None:
    from cadgen.engine.render.meshes import from_daemon
    from cadgen.engine.render.occt import Scene

    structure, buffers, _ = from_daemon(doc)
    scene = Scene(doc, buffers, size=size, structure=structure)
    for mode in modes:
        scene.show({"mode": mode})
        for camera in cameras:
            scene.frame(camera, "orthographic")
            scene.save(folder / f"{mode}-{camera}-occt.png")
    scene.show({"mode": "solid"})  # framed as Solid is (Wireframe frames the box's corners)
    scene.frame("iso", "orthographic")
    (folder / "metal-tops.json").write_text(json.dumps(metal_tops(structure, buffers, scene)))
    if not preview:
        return
    from PIL import Image

    from cadgen.engine.render.service import Held
    from cadgen.engine.snapshot import Still

    held = Held(doc)
    try:
        held.hold(structure, buffers)
        for camera in cameras:
            data, _report = held.draw(Still({"mode": "solid"}, camera, False, True, tuple(size)))
            (folder / f"preview-{camera}-occt.png").write_bytes(data)
            shown = held.scenes[True]
            for presentation in shown.shown:  # the next picture shows the model again
                shown.canvas.context.Erase(presentation, False)
            Image.fromarray(shown.canvas.frame()).save(folder / f"preview-{camera}-studio.png")
    finally:
        held.close()


# --- the viewer's side: its snapshot page, in a headless Chromium -------------------------------------
# The page (render.html, snapshot-render.js) is built by scripts/bundle/lib/snapshot_runtime.sh into
# the ignored tmp/bench/snapshot-page, once per run, so it is always the checkout's own scene code;
# it is read as files and routed to the page's origin, and it reads the document from the engine
# daemon that serves it: those requests are fetched for the page with the user's token, which the
# page has no way to send, and answered with the page's origin allowed (the engine sends no CORS). ``cadgen snapshot`` drew mesh files this way before OCCT drew every kind;
# nothing cadgen ships carries the page now, and this bench builds it for the viewer's side alone.

PAGE_ORIGIN = "http://localhost"
_PAGE: list[Path] = []


def _runtime() -> Path:
    import subprocess

    if _PAGE:
        return _PAGE[0]
    root = Path(__file__).resolve().parents[2]
    folder = root / "tmp" / "bench" / "snapshot-page"
    subprocess.run([str(root / "scripts/bundle/lib/snapshot_runtime.sh"), str(folder)], check=True)
    missing = [name for name in ("render.html", "snapshot-render.js") if not (folder / name).is_file()]
    if missing:
        raise RuntimeError(f"scripts/bundle/lib/snapshot_runtime.sh left {folder} without {', '.join(missing)}")
    _PAGE.append(folder)
    return folder


def _served(doc: Path) -> tuple[str, str]:
    """The document's API URL on the engine daemon, which serves and meshes it, and the token its
    requests carry."""
    from urllib.parse import urlparse
    from urllib.request import Request, urlopen

    from cadgen.engine.client import request

    answer = request({"op": "serve", "path": str(doc)})
    if not answer or "failed" in answer:
        raise RuntimeError(f"the engine would not serve {doc.name}: {(answer or {}).get('failed', 'no daemon')}")
    parsed = urlparse(answer["url"])
    url = f"{parsed.scheme}://{parsed.netloc}/api/doc/{answer['doc']}"
    headers = {"Authorization": f"Bearer {answer['token']}", "x-cadgen-viewer": "1"}
    with urlopen(Request(f"{url}/mesh", data=b"", method="POST", headers=headers), timeout=900) as done:  # noqa: S310 - the engine, on loopback
        done.read()
    return url, answer["token"]


def _page(job: dict[str, Any], size: tuple[int, int], token: str) -> dict[str, Any]:
    """The snapshot page's answer to ``job`` (its PNGs as data URLs), in a headless Chromium."""
    from urllib.parse import urlparse

    from playwright.sync_api import sync_playwright

    runtime = _runtime()
    files = {"/render.html": runtime / "render.html", "/snapshot-render.js": runtime / "snapshot-render.js"}

    def route(handle: Any) -> None:
        found = files.get(urlparse(handle.request.url).path)
        if found is None:
            handle.fulfill(status=404, content_type="text/plain", body="not found")
            return
        kind = "text/html" if found.suffix == ".html" else "text/javascript"
        handle.fulfill(status=200, content_type=kind, body=found.read_bytes(), headers={"cache-control": "no-store"})

    def engine(handle: Any) -> None:
        answer = handle.fetch(headers={**handle.request.headers, "authorization": f"Bearer {token}"})
        handle.fulfill(response=answer, headers={**answer.headers, "access-control-allow-origin": PAGE_ORIGIN})

    args = ["--disable-features=BlockInsecurePrivateNetworkRequests,PrivateNetworkAccessSendPreflights,"
            "PrivateNetworkAccessRespectPreflightResults,PrivateNetworkAccessChecks,LocalNetworkAccessChecks",
            *(["--use-angle=metal"] if sys.platform == "darwin" else [])]
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=args)
        try:
            page = browser.new_context(viewport={"width": size[0], "height": size[1]}, device_scale_factor=1).new_page()
            page.route(f"{PAGE_ORIGIN}/**", route)
            engine_origin = urlparse(str(job["resolved"]["url"]))
            page.route(f"{engine_origin.scheme}://{engine_origin.netloc}/**", engine)
            page.goto(f"{PAGE_ORIGIN}/render.html", wait_until="load", timeout=300_000)
            page.wait_for_function("typeof window.__snapshotRender === 'function'", timeout=300_000)
            result = page.evaluate("(job) => window.__snapshotRender(job)", job)
        finally:
            browser.close()
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(str((result or {}).get("error") or "the snapshot page drew nothing"))
    return result


def draw_chromium(doc: Path, folder: Path, modes: list[str], cameras: list[str], size: tuple[int, int],
                  preview: bool = False) -> None:
    url, token = _served(doc.resolve())
    for mode in [*modes, *(["preview"] if preview else [])]:
        outputs = [{"path": str(folder / f"{mode}-{camera}-chromium.png"), "width": size[0], "height": size[1],
                    "camera": camera} for camera in cameras]
        job = {"kind": "xbf", "mode": "view", "display": {"mode": "solid" if mode == "preview" else mode},
               "outputs": outputs, "resolved": {"kind": "xbf", "url": url, "inputPath": str(doc)},
               **({"preview": True} if mode == "preview" else {})}
        result = _page(job, size, token)
        for output, drawn in zip(outputs, result["outputs"]):
            Path(output["path"]).write_bytes(base64.b64decode(str(drawn["dataUrl"]).partition(",")[2]))


def sheet(folder: Path, name: str, rows: list[tuple[str, dict[str, float]]], out: Path) -> None:
    """Chromium, OCCT and the ΔE map per row, the measures beside; 1800 px wide."""
    from PIL import Image, ImageDraw, ImageFont

    label, cell, head = 240, (520, 390), 44
    image = Image.new("RGB", (label + 3 * cell[0], head + len(rows) * cell[1]), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except OSError:
        font = small = ImageFont.load_default()
    draw.text((10, 12), name, fill="black", font=font)
    for column, title in enumerate(("Viewer (three.js)", "OCCT (reference)", "ΔE (white 0, red 20+)")):
        draw.text((label + column * cell[0] + 12, 12), title, fill="black", font=font)
    for at, (row, found) in enumerate(rows):
        y = head + at * cell[1]
        draw.line([(0, y), (image.width, y)], fill="#999999")
        draw.text((10, y + 10), row, fill="black", font=font)
        lines = [f"IoU {iou(found)}", f"ΔE median {found['de_median']:.2f}", f"ΔE p95 {found['de_p95']:.2f}",
                 f"line diff {found['line_diff']:.3f}"]
        for n, text in enumerate(lines):
            draw.text((10, y + 44 + n * 22), text, fill="#333333", font=small)
        left = np.asarray(Image.open(folder / f"{row}-chromium.png").convert("RGB"))
        right = np.asarray(Image.open(folder / f"{row}-occt.png").convert("RGB"))
        for column, picture in enumerate((left, right, delta_map(left, right))):
            tile = Image.fromarray(picture)
            tile.thumbnail(cell)
            image.paste(tile, (label + column * cell[0], y))
    image.save(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--doc", action="append", required=True, help="NAME=PATH of an .xbf, repeated")
    parser.add_argument("--out", default="tmp/bench/occt-parity")
    parser.add_argument("--modes", default=",".join(MODES))
    parser.add_argument("--cameras", default=",".join(CAMERAS))
    parser.add_argument("--size", default="1200x900")
    parser.add_argument("--only", choices=("occt", "chromium"), help="draw one side; keep the other's pictures")
    parser.add_argument("--preview", action="store_true", help="Preview at each camera too")
    args = parser.parse_args(argv)
    try:
        from cadgen.engine.render.look import LOOK

        backdrop = tuple(int(LOOK.backdrop[i:i + 2], 16) for i in (1, 3, 5))
    except ImportError:  # a cadgen from before the look (a before-and-after measurement)
        backdrop = (240, 244, 249)
    modes, cameras = args.modes.split(","), args.cameras.split(",")
    size = tuple(int(v) for v in args.size.split("x"))
    out = Path(args.out)
    table, hues = {}, {}
    for entry in args.doc:
        name, _sep, path = entry.partition("=")
        doc = Path(path).resolve()
        folder = out / name
        folder.mkdir(parents=True, exist_ok=True)
        started = time.perf_counter()
        if args.only != "chromium":
            draw_occt(doc, folder, modes, cameras, size, args.preview)
        if args.only != "occt":
            draw_chromium(doc, folder, modes, cameras, size, args.preview)
        from PIL import Image

        rows = []
        for mode in [*modes, *(["preview"] if args.preview else [])]:
            for camera in cameras:
                row = f"{mode}-{camera}"
                left = np.asarray(Image.open(folder / f"{row}-chromium.png").convert("RGB"))
                right = np.asarray(Image.open(folder / f"{row}-occt.png").convert("RGB"))
                if mode == "preview":  # the model is where OCCT's picture leaves its own bare studio
                    studio = np.asarray(Image.open(folder / f"{row}-studio.png").convert("RGB"))
                    rows.append((row, compare(left, right, backdrop, mask=silhouette(right, studio))))
                else:
                    rows.append((row, compare(left, right, backdrop)))
        table[name] = dict(rows)
        tops = json.loads((folder / "metal-tops.json").read_text()) if (folder / "metal-tops.json").is_file() else []
        hues[name] = {f"{mode}-{side}": hue_check(tops, np.asarray(Image.open(folder / f"{mode}-iso-{side}.png").convert("RGB")))
                      for mode in ("solid", "shaded") if mode in modes and "iso" in cameras for side in ("chromium", "occt")}
        (folder / "metrics.json").write_text(json.dumps({**table[name], "hue": hues[name]}, indent=1))
        sheet(folder, name, rows, out / f"sheet-{name}.png")
        print(f"{name}: {time.perf_counter() - started:.1f}s", file=sys.stderr)
    print("| document | row | IoU | ΔE median | ΔE p95 | line diff |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, rows in table.items():
        for row, found in rows.items():
            print(f"| {name} | {row} | {iou(found)} | {found['de_median']:.2f} | {found['de_p95']:.2f} | "
                  f"{found['line_diff']:.3f} |")
    print("\n| document | picture | metal tops | hue off (median, max, degrees) | chroma kept (median) |")
    print("| --- | --- | --- | --- | --- |")
    for name, pictures in hues.items():
        for picture, found in pictures.items():
            print(f"| {name} | {picture} | {found['samples']} | {found['hue_median']:.1f}, {found['hue_max']:.1f} | "
                  f"{found['chroma_ratio']:.2f} |")
    (out / "table.json").write_text(json.dumps({"rows": table, "hue": hues}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
