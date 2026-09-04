#!/usr/bin/env python
"""Golden-image harness for the surface-rendering migration
(design/surface-rendering.md R0).

capture: screenshot the viewer canvas for fixtures x themes into an output
directory. compare: perceptual-diff two capture directories and report.

Usage:
  golden.py capture --url-base http://127.0.0.1:PORT --out DIR [--themes a,b]
  golden.py compare GOLDEN_DIR CANDIDATE_DIR [--threshold 0.02]

The viewer must already be serving the worktree's models/ directory.
Deterministic by construction: fixed viewport, auto-fit default camera,
fixed settle delay, canvas-only crop (UI chrome excluded).
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

FIXTURES = {
    "planetary": "assemblies/STEP/planetary_gear_assembly/planetary_gear_assembly.step",
    "turbofan": "assemblies/STEP/cutaway_turbofan_engine/cutaway_turbofan_engine.step",
    # A render project's artifacts live in its own format folder, and are NOT
    # committed — build it first: `python models/moonwatch/src/moonwatch.py`.
    "moonwatch": "moonwatch/STEP/moonwatch.step",
}
THEMES = ["workbench-light", "workbench-dark", "cinematic", "vibrant",
          "blue", "pink", "clay-sunrise", "terminal"]


def capture(url_base: str, out_dir: Path, themes: list[str]) -> int:
    from playwright.sync_api import sync_playwright

    out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--enable-unsafe-webgpu", "--use-angle=metal", "--enable-gpu"])
        for fixture, rel in FIXTURES.items():
            for theme in themes:
                name = f"{fixture}--{theme}"
                url = f"{url_base}/?file={rel}"
                # Fresh page per shot: init scripts accumulate per page, and
                # the theme is viewer-persisted state, not a URL param
                # (persistence.js THEME_STORAGE_KEY, version 12).
                page = browser.new_page(
                    viewport={"width": 1200, "height": 900},
                    device_scale_factor=1)
                page.add_init_script(
                    "localStorage.setItem('cad-viewer:theme',"
                    f" JSON.stringify({{version: 12, themeId: {theme!r}}}))")
                try:
                    page.goto(url, timeout=60000)
                    page.wait_for_selector("canvas", timeout=60000)
                    # Settle detection: big assemblies tessellate client-side
                    # for many seconds; capture once two consecutive frames
                    # (2s apart) are identical, with a hard cap.
                    canvas = page.query_selector("canvas")
                    previous = None
                    deadline = time.monotonic() + 90
                    while time.monotonic() < deadline:
                        time.sleep(2)
                        current = canvas.screenshot()
                        if previous is not None and current == previous:
                            break
                        previous = current
                    canvas.screenshot(path=str(out_dir / f"{name}.png"))
                    print(f"captured {name}", flush=True)
                except Exception as exc:
                    failures += 1
                    print(f"FAILED {name}: {exc}", flush=True)
                finally:
                    page.close()
        browser.close()
    return failures


def _diff_fraction(a, b) -> float:
    from PIL import ImageChops

    histogram = ImageChops.difference(a, b).convert("L").histogram()
    total = sum(histogram)
    # a pixel "differs" when its max channel delta exceeds 12/255
    return sum(histogram[13:]) / max(total, 1)


def compare(golden: Path, candidate: Path, threshold: float) -> int:
    from PIL import Image

    failures = 0
    goldens = sorted(golden.glob("*.png"))
    if not goldens:
        print(f"no goldens in {golden}")
        return 1
    for gold_path in goldens:
        cand_path = candidate / gold_path.name
        if not cand_path.is_file():
            print(f"MISSING {gold_path.name}")
            failures += 1
            continue
        a = Image.open(gold_path).convert("RGB")
        b = Image.open(cand_path).convert("RGB")
        if a.size != b.size:
            b = b.resize(a.size)
        # Shift-tolerant: camera auto-fit reacts to honest sub-pixel bbox
        # differences between renderers, shifting the whole model 1-2px and
        # moireing on striped geometry. Take the min over small offsets —
        # content changes still diff at every offset.
        best = 1.0
        for dx in (0, -1, 1, -2, 2):
            for dy in (0, -1, 1, -2, 2):
                if dx or dy:
                    from PIL import ImageChops

                    shifted = ImageChops.offset(b, dx, dy)
                else:
                    shifted = b
                best = min(best, _diff_fraction(a, shifted))
                if best <= threshold / 4:
                    break
            if best <= threshold / 4:
                break
        status = "OK " if best <= threshold else "DIFF"
        if best > threshold:
            failures += 1
        print(f"{status} {gold_path.name}: {best*100:.2f}% pixels differ (best shift)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    cap = sub.add_parser("capture")
    cap.add_argument("--url-base", required=True)
    cap.add_argument("--out", required=True)
    cap.add_argument("--themes", default=",".join(THEMES))
    cmp_p = sub.add_parser("compare")
    cmp_p.add_argument("golden")
    cmp_p.add_argument("candidate")
    cmp_p.add_argument("--threshold", type=float, default=0.02)
    args = parser.parse_args()
    if args.cmd == "capture":
        return capture(args.url_base, Path(args.out),
                       [t for t in args.themes.split(",") if t])
    return compare(Path(args.golden), Path(args.candidate), args.threshold)


if __name__ == "__main__":
    sys.exit(main())
