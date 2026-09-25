"""Local PNG clipboard delivery for the viewer's explicit snapshot action."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

MAX_PNG_BYTES = 20 * 1024 * 1024


def copy_png(data: bytes) -> None:
    if len(data) > MAX_PNG_BYTES or not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError("Expected a PNG image of at most 20 MiB")
    if sys.platform == "darwin":
        # Only the generated temporary path is passed as data, never script text.
        with tempfile.TemporaryDirectory(prefix="cadgen-clipboard-") as directory:
            image = Path(directory) / "snapshot.png"
            image.write_bytes(data)
            subprocess.run(["/usr/bin/osascript", "-e", 'on run argv\nset the clipboard to (read POSIX file (item 1 of argv) as «class PNGf»)\nend run', str(image)], check=True, capture_output=True, timeout=10)
    elif shutil.which("wl-copy"):
        subprocess.run(["wl-copy", "--type", "image/png"], input=data, check=True, timeout=10)
    elif shutil.which("xclip"):
        subprocess.run(["xclip", "-selection", "clipboard", "-t", "image/png"], input=data, check=True, timeout=10)
    else:
        raise RuntimeError("PNG clipboard is unavailable on this viewer host")
