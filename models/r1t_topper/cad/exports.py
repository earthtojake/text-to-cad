"""Regenerate the Checkpoint 1 STEP and stable review images."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = PROJECT_ROOT.parents[1]
STEP_PATH = PROJECT_ROOT / "outputs/step/R1T_TOPPER_ASSEMBLY.step"
RENDER_DIR = PROJECT_ROOT / "outputs/renders"

VIEWS = {
    # Viewer presets are mapped to the vehicle coordinate convention.
    "front": "left",
    "rear": "right",
    "driver_side": "front",
    "passenger_side": "back",
    "top": "top",
    "three_quarter_rear": "iso",
}


def run() -> None:
    STEP_PATH.parent.mkdir(parents=True, exist_ok=True)
    RENDER_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "skills/cad/scripts/step"),
            f"cad/assembly.py={STEP_PATH.relative_to(PROJECT_ROOT)}",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    with tempfile.TemporaryDirectory(prefix="r1t-topper-cp1-") as temp:
        temp_dir = Path(temp)
        job = {
            "input": str(STEP_PATH),
            "mode": "view",
            "outputs": [
                {"path": str(temp_dir / f"{name}.png"), "camera": camera}
                for name, camera in VIEWS.items()
            ],
            "display": {"mode": "solid", "projection": "orthographic"},
            "render": {
                "viewLabels": False,
                "padding": 0.08,
                "sizeProfile": "assembly",
            },
        }
        subprocess.run(
            [
                sys.executable,
                str(REPO_ROOT / "skills/cad/scripts/snapshot"),
                "--job",
                "-",
            ],
            cwd=PROJECT_ROOT,
            input=json.dumps(job),
            text=True,
            check=True,
        )
        for name in VIEWS:
            generated = sorted(temp_dir.glob(f"{name}_*.png"))
            if not generated:
                raise RuntimeError(f"snapshot missing for {name}")
            shutil.copy2(generated[-1], RENDER_DIR / f"{name}.png")


if __name__ == "__main__":
    run()
