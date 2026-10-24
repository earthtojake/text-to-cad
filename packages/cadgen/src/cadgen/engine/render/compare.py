"""PROTOTYPE harness: two pictures of one scene laid side by side -- a picture the CAD Viewer
drew (its page, or any picture of it) beside the picture OCCT drew -- and what tells them apart:
how alike they frame the model (``framing``) and where one colour's ink lies (``ink``). The
pictures are made elsewhere (``scripts/bench/occt_parity.py`` draws the viewer's side); this module
draws nothing.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def sheet(rows: list[tuple[str, Path | None, Path | None, str]], out: Path, *, cell: tuple[int, int] = (800, 600),
          title: str = "", columns: tuple[str, str] = ("Viewer (before)", "OCCT")) -> None:
    """A contact sheet: one row per flag, the viewer's picture left, OCCT's right, the flag and a
    note beside; ``columns`` heads the two."""
    from PIL import Image, ImageDraw, ImageFont

    label_width, head = 300, 60
    width, height = label_width + 2 * cell[0], head + len(rows) * cell[1]
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        small = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except OSError:
        font = small = ImageFont.load_default()
    draw.text((10, 18), title, fill="black", font=font)
    for column, heading in enumerate(columns):
        draw.text((label_width + column * cell[0] + cell[0] // 2 - 80, 18), heading, fill="black", font=font)
    for row, (name, left, right, note) in enumerate(rows):
        y = head + row * cell[1]
        draw.line([(0, y), (width, y)], fill="#999999")
        draw.text((10, y + 12), name, fill="black", font=font)
        words, line, at = note.split(), "", y + 48
        for word in words:
            if len(line) + len(word) > 30:
                draw.text((10, at), line, fill="#333333", font=small)
                line, at = "", at + 20
            line = f"{line} {word}".strip()
        if line:
            draw.text((10, at), line, fill="#333333", font=small)
        for column, path in enumerate((left, right)):
            x = label_width + column * cell[0]
            if path is not None and Path(path).is_file():
                picture = Image.open(path).convert("RGB")
                picture.thumbnail(cell)
                image.paste(picture, (x, y))
            else:
                draw.rectangle([x + 4, y + 4, x + cell[0] - 4, y + cell[1] - 4], outline="#cccccc")
                draw.text((x + 20, y + cell[1] // 2), "(no counterpart)", fill="#999999", font=font)
    image.save(out)


def silhouette(path: Path, background: tuple[int, int, int], tolerance: int = 6) -> Any:
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(path).convert("RGB")).astype(int)
    return np.abs(pixels - np.array(background)).max(-1) > tolerance


def framing(left: Path, right: Path, background: tuple[int, int, int] = (240, 244, 249)) -> dict[str, float]:
    """How alike two pictures frame the model: the intersection over union of what is not
    backdrop, and the offset of its box's corners in pixels."""
    import numpy as np

    a, b = silhouette(left, background), silhouette(right, background)
    union = np.logical_or(a, b).sum()
    found = {"iou": float(np.logical_and(a, b).sum() / union) if union else 0.0}
    boxes = []
    for mask in (a, b):
        ys, xs = np.nonzero(mask)
        boxes.append((xs.min(), ys.min(), xs.max(), ys.max()) if len(xs) else (0, 0, 0, 0))
    found["box_offset_px"] = float(max(abs(p - q) for p, q in zip(*boxes)))
    return found


def ink(path: Path, color: tuple[int, int, int], tolerance: int = 60) -> Any:
    """The pixels of one colour: their coordinates (x, y)."""
    import numpy as np
    from PIL import Image

    pixels = np.asarray(Image.open(path).convert("RGB")).astype(int)
    ys, xs = np.nonzero(np.abs(pixels - np.array(color)).max(-1) < tolerance)
    return np.stack([xs, ys], -1)
