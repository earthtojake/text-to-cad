"""Compare the descriptions text-to-cad made from each maker's STEP with the hand-made references.

    python src/compare.py              # every robot
    python src/compare.py so101        # one: (a) our MuJoCo file vs Menagerie's, (b) our URDF vs the maker's
    python src/compare.py so101 --ours menagerie/robotstudio_so101/so101.xml \\
        --theirs upstream/so101/Simulation/SO101/so101_new_calib.urdf   # any two files

"Ours" is (a) ``out/<robot>/<robot>.xml``, the file the robot's MuJoCo function saves
(``src/<robot>_mujoco.py``: the model with a simulation's choices, as Menagerie's file is), and (b)
``out/<robot>/export/<robot>.urdf``, the model's plain export (``src/<robot>.py``).

Writes ``reports/<robot>.md`` (to read) and ``reports/<robot>.json`` (every number); a pair named
with --ours/--theirs writes ``reports/<robot>.<ours>-vs-<theirs>.md/.json``. Prints a line per
comparison.

The two sides come from different CAD exports, so their world frames and joint zeros differ: nothing
is compared by joint value or body frame. The root links' shapes are registered with ICP; then,
parent first, each of THEIR joints is turned (or slid) until their child link lies on ours, which
gives the calibration offset and axis sign per joint. Axes, ranges, mass properties and gravity
torques are all compared at that matched pose. See lib/compare_core.py for the method and
lib/compare_selftest.py for the check that it recovers a known transform and known offsets.

Needs mujoco, numpy, scipy and trimesh (the repository's .venv has them).
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
import time
from pathlib import Path

import numpy as np

from lib.compare_core import compare
from lib.compare_model import LoadError, describe
from lib.compare_report import render, summary
from sources import OUT, REPORTS, ROBOTS, ROOT


def packages() -> dict[str, Path]:
    """``package://`` names the URDFs use, mapped to where fetch.py put them."""
    return {"trossen_arm_description": ROBOTS["wxai"].folder / "vendor"}


def resolve(p: str) -> Path:
    q = Path(p)
    if q.is_absolute() or q.exists():
        return q.resolve()
    return (ROOT / q).resolve()


def rel(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ROOT))
    except ValueError:
        return str(p)


def tag(p: Path) -> str:
    """A file's name in a report's name: its stem, after the top folder it is in (menagerie, upstream, out)."""
    top = rel(p).split("/")[0]
    return p.stem if top == p.name else f"{top}_{p.stem}"


def _json(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))


def run_pair(label: str, ours: Path, theirs: Path, configs: int) -> dict:
    o = describe("ours", ours, packages())
    t = describe("theirs", theirs, packages())
    return compare(o, t, configs=configs)


def run_robot(name: str, configs: int, ours: Path | None = None, theirs: Path | None = None) -> bool:
    robot = ROBOTS[name]
    if ours is not None:
        pairs = [(f"{rel(ours)} vs {rel(theirs)}", ours, theirs, name)]
        stem = f"{name}.{tag(ours)}-vs-{tag(theirs)}"
        command = f"python src/compare.py {name} --ours {rel(ours)} --theirs {rel(theirs)}"
    else:
        out = OUT / name
        pairs = [("(a) MuJoCo function vs Menagerie", out / f"{name}.xml", robot.menagerie_path, f"{name}_mujoco"),
                 ("(b) URDF vs the maker's", out / "export" / f"{name}.urdf", robot.vendor_urdf_file, name)]
        stem = name
        command = f"python src/compare.py {name}"
    results, missing = [], []
    for label, a, b, script in pairs:
        if not a.is_file():
            msg = (f"{label}: {rel(a)} not found; make it with `python src/{script}.py`" if ours is None
                   else f"{label}: {a} not found")
            print(f"{name}: {msg}", file=sys.stderr)
            missing.append(msg)
            continue
        if not b.is_file():
            msg = f"{label}: reference {rel(b)} not found; fetch it with `python3 src/fetch.py {name}`"
            print(f"{name}: {msg}", file=sys.stderr)
            missing.append(msg)
            continue
        t0 = time.time()
        try:
            r = run_pair(label, a, b, configs)
        except LoadError as e:
            msg = f"{label}: {e}"
            print(f"{name}: {msg}", file=sys.stderr)
            missing.append(msg)
            continue
        r["label"] = label
        results.append((label, r))
        print(f"{summary(name, label, r)}  [{time.time() - t0:.0f} s]")
    if not results:
        return False
    REPORTS.mkdir(parents=True, exist_ok=True)
    md = REPORTS / f"{stem}.md"
    md.write_text(render(name, robot.title, results, missing, ROOT, command))
    payload = {"robot": name, "title": robot.title, "command": command,
               "generated": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
               "missing": missing, "comparisons": [r for _, r in results]}
    (REPORTS / f"{stem}.json").write_text(json.dumps(payload, indent=1, default=_json))
    print(f"  -> {rel(md)}, {rel(REPORTS / f'{stem}.json')}")
    return True


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("robots", nargs="*", metavar="robot",
                    help=f"one or more of {', '.join(ROBOTS)} (default: all)")
    ap.add_argument("--ours", help="compare this file (MJCF or URDF) ...")
    ap.add_argument("--theirs", help="... with this one, instead of the default pairs")
    ap.add_argument("--configs", type=int, default=20, help="configurations for the gravity-torque check")
    a = ap.parse_args(argv)
    unknown = [r for r in a.robots if r not in ROBOTS]
    if unknown:
        ap.error(f"unknown robot {', '.join(unknown)}: one of {', '.join(ROBOTS)}")
    if (a.ours is None) != (a.theirs is None):
        ap.error("--ours and --theirs go together")
    if a.ours is not None:
        if len(a.robots) != 1:
            ap.error("--ours/--theirs need exactly one robot (it names the report)")
        ok = run_robot(a.robots[0], a.configs, resolve(a.ours), resolve(a.theirs))
        return 0 if ok else 1
    ok = [run_robot(n, a.configs) for n in (a.robots or list(ROBOTS))]
    return 0 if all(ok) else 1


if __name__ == "__main__":
    sys.exit(main())
