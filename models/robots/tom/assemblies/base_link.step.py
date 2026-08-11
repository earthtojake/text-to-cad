from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ASSEMBLIES_DIR = Path(__file__).resolve().parent
V2_DIR = ASSEMBLIES_DIR.parent
if str(V2_DIR) not in sys.path:
    sys.path.insert(0, str(V2_DIR))

# Resolve robot_common while V2_DIR is on sys.path (the cad CLI restores sys.path
# after module load, so a deferred import would fail in a fresh CLI process).
from robot_common.link_assembly import link_assembly_from_instances


SOURCE_REF = "@cad[STEP/robot_arm#o1.19]"

# The base servo seat: the sts3250 mounting-tab plane (local y=-27.4) seats flush on
# the old base-plate top face at y=-29.8, with the plate bottom grounded. This pose is
# preserved verbatim — the base servo output horn still points +Y to drive shoulder_yaw
# — so the arm kinematics above the base are identical to the flat-plate base. Only the
# base hardware below the servo changes (flat plate -> desk clamp + bus + standoffs).
BASE_PLATE_TOP_Y_MM = -29.8002
BASE_PLATE_THICKNESS_MM = 25.4 * 0.080
BASE_PLATE_BOTTOM_Y_MM = BASE_PLATE_TOP_Y_MM - BASE_PLATE_THICKNESS_MM
BASE_LINK_FLOOR_Y_OFFSET_MM = -BASE_PLATE_BOTTOM_Y_MM
STS3250_BASE_PLATE_FACE_LOCAL_Y_MM = -27.4
STS3250_BASE_PLATE_FLUSH_Y_OFFSET_MM = BASE_PLATE_TOP_Y_MM - STS3250_BASE_PLATE_FACE_LOCAL_Y_MM
_SERVO_Y_MM = BASE_LINK_FLOOR_Y_OFFSET_MM + STS3250_BASE_PLATE_FLUSH_Y_OFFSET_MM

# Base servo pose in base_link's local frame (identity rotation, output horn +Y).
BASE_SERVO_TRANSFORM = [
    1.0, 0.0, 0.0, 0.0,
    0.0, 1.0, 0.0, _SERVO_Y_MM,
    0.0, 0.0, 1.0, 0.0,
    0.0, 0.0, 0.0, 1.0,
]


def _matmul(a: list[float], b: list[float]) -> list[float]:
    return [
        sum(a[row * 4 + k] * b[k * 4 + col] for k in range(4))
        for row in range(4)
        for col in range(4)
    ]


def _invert_rigid(t: list[float]) -> list[float]:
    r = [[t[row * 4 + col] for col in range(3)] for row in range(3)]
    trans = [t[row * 4 + 3] for row in range(3)]
    rt = [[r[col][row] for col in range(3)] for row in range(3)]
    it = [-sum(rt[row][k] * trans[k] for k in range(3)) for row in range(3)]
    return [
        rt[0][0], rt[0][1], rt[0][2], it[0],
        rt[1][0], rt[1][1], rt[1][2], it[1],
        rt[2][0], rt[2][1], rt[2][2], it[2],
        0.0, 0.0, 0.0, 1.0,
    ]


# The base_clamp_assembly sub-assembly (servo + clamp bracket + M2/M2.5 standoffs +
# Waveshare bus) is authored in its own Z-up floor frame. Align it so its servo
# coincides with the base servo pose: M maps the clamp's servo placement onto
# BASE_SERVO_TRANSFORM, carrying the rest of the clamp rigidly with it. The base
# servo therefore lands exactly where the flat-plate base servo was (arm unchanged),
# and the clamp body hangs below it as the new mounting hardware.
_BASE_CLAMP_ASSEMBLY_PATH = ASSEMBLIES_DIR / "base_clamp_assembly" / "base_clamp_assembly.step.py"


def _load_base_clamp_assembly():
    spec = importlib.util.spec_from_file_location(
        "_tom_base_link_base_clamp_assembly", _BASE_CLAMP_ASSEMBLY_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load {_BASE_CLAMP_ASSEMBLY_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_BASE_CLAMP_ASSEMBLY = _load_base_clamp_assembly()
_CLAMP_TO_BASE_SERVO = _matmul(
    BASE_SERVO_TRANSFORM,
    _invert_rigid([float(v) for v in _BASE_CLAMP_ASSEMBLY.STS3250_FLOOR_TRANSFORM]),
)


def assembly_instances() -> dict[str, object]:
    # Flat instance list consumed by tom's composition. The base servo is renamed to
    # sts3250_3 (tom's expected base-servo name) and every clamp part is aligned by
    # _CLAMP_TO_BASE_SERVO and re-pathed relative to the assemblies dir. gen_step()
    # returns the shape; this is the internal placement data.
    instances: list[dict[str, object]] = []
    for source in _BASE_CLAMP_ASSEMBLY.assembly_instances()["instances"]:
        name = "sts3250_3" if str(source["name"]) == "sts3250" else str(source["name"])
        instances.append(
            {
                "path": f"base_clamp_assembly/{source['path']}",
                "name": name,
                "transform": _matmul(
                    _CLAMP_TO_BASE_SERVO, [float(v) for v in source["transform"]]
                ),
                "use_source_colors": bool(source.get("use_source_colors", True)),
            }
        )
    return {"instances": instances}


def build():
    return link_assembly_from_instances(
        "base_link",
        assembly_instances()["instances"],
        base_dir=ASSEMBLIES_DIR,
    )


def gen_step() -> dict[str, object]:
    return {"shape": build()}
