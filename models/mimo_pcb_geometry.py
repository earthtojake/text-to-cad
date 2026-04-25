import json
from pathlib import Path

from build123d import Box, Compound, Cylinder

from mimo_case_geometry import (
    PCB_CASE_CENTER_X,
    PCB_CASE_CENTER_Y,
    PCB_CASE_CENTER_Z,
    PCB_MOUNT_HOLES,
    PCB_THICKNESS,
    PCB_WIDTH,
    PCB_HEIGHT,
    pcb_case_position,
    viewer_aligned,
)

BOARD_JSON = Path(__file__).resolve().parents[1] / "mimo-board" / "dist" / "index" / "circuit.json"


def load_board_metadata():
    with BOARD_JSON.open() as file:
        return json.load(file)


def board_item(data, item_type: str):
    for item in data:
        if item.get("type") == item_type:
            return item
    raise ValueError(f"Missing {item_type} in {BOARD_JSON}")


def source_component_names(data):
    return {
        item["source_component_id"]: item.get("name", item["source_component_id"])
        for item in data
        if item.get("type") == "source_component"
    }


def component_height(ref: str) -> float:
    if ref == "J1":
        return 3.2
    if ref == "J2":
        return 2.8
    if ref == "PIR1":
        return 5.2
    if ref in {"U1", "U2"}:
        return 3.0
    if ref.startswith("SW"):
        return 2.2
    if ref.startswith("Y"):
        return 1.0
    if ref.startswith(("R", "C", "L", "LED", "F")):
        return 0.65
    return 1.2


def pcb_components(data):
    names = source_component_names(data)
    components = []
    for item in data:
        if item.get("type") != "pcb_component":
            continue
        ref = names.get(item.get("source_component_id"), item.get("pcb_component_id", "component"))
        width = float(item.get("width") or 1.0)
        height = float(item.get("height") or 1.0)
        if width <= 0 or height <= 0:
            continue
        components.append(
            {
                "ref": ref,
                "x": float(item["center"]["x"]),
                "y": float(item["center"]["y"]),
                "width": width,
                "height": height,
                "z_height": component_height(ref),
            }
        )
    return components


def pcb_holes(data):
    holes = []
    for item in data:
        if item.get("type") == "pcb_hole":
            holes.append((float(item["x"]), float(item["y"]), float(item["hole_diameter"])))
        elif item.get("type") == "pcb_plated_hole":
            holes.append((float(item["x"]), float(item["y"]), float(item["hole_diameter"])))
    return holes


def pcb_board_raw():
    data = load_board_metadata()
    board = board_item(data, "pcb_board")
    width = float(board.get("width", PCB_WIDTH))
    height = float(board.get("height", PCB_HEIGHT))
    thickness = float(board.get("thickness", PCB_THICKNESS))
    body = Box(width, height, thickness)

    for hole_x, hole_y, hole_diameter in pcb_holes(data):
        hole = Cylinder(hole_diameter / 2.0, thickness + 0.4).translate((hole_x, hole_y, 0))
        body = body - hole

    return body


def pcb_component_solids_raw():
    data = load_board_metadata()
    solids = []
    for item in pcb_components(data):
        z_height = item["z_height"]
        solid = Box(item["width"], item["height"], z_height).translate(
            (
                item["x"],
                item["y"],
                (PCB_THICKNESS / 2.0) + (z_height / 2.0),
            )
        )
        solid.label = item["ref"]
        solids.append(solid)
    return Compound(solids)


def pcb_usb_c_opening_center() -> tuple[float, float, float]:
    data = load_board_metadata()
    names = source_component_names(data)
    for item in data:
        if item.get("type") != "pcb_component":
            continue
        if names.get(item.get("source_component_id")) == "J1":
            cable_center = item.get("cable_insertion_center") or item.get("center")
            return (float(cable_center["x"]), float(cable_center["y"]), PCB_THICKNESS / 2.0 + 1.6)
    raise ValueError("Could not find J1 USB-C component in PCB metadata")


# Refdes of components that need front-face optical/RF visibility, mapped from
# `mimo-board/subcircuits/*.tsx`:
#   U2   → IWR6843AOP 60 GHz mmWave radar (radar.tsx)
#   J2   → FLIR Lepton 3.5 thermal socket (thermal.tsx)
#   PIR1 → Panasonic EKMC PIR (pir.tsx)
#
# The mic (U5) is excluded because it needs only a small acoustic port, not a
# full visibility window — it gets its own pinhole via `MIC_REFDES`.
#
# Other excluded components:
#   U1 ESP32-S3 MCU       — internal, no aperture
#   U3 SHT45 ambient T/RH — needs OPEN-AIR side vent, not a front aperture
#   U4 BMI270 IMU         — fully internal
#   LED1 status LED       — separate light-pipe hole if needed
FRONT_FACE_SENSOR_REFDES = ("U2", "J2", "PIR1")

# Refdes of the MEMS microphone that needs an acoustic pinhole + mesh over its
# bottom-port, not a full front-face window.
MIC_REFDES = "U5"

# Refdes of the ambient T/RH sensor that needs a side-face vent for open-air
# access (not the front sensor window).
AMBIENT_SENSOR_REFDES = "U3"


def pcb_component_by_refdes(refdes: str) -> dict | None:
    data = load_board_metadata()
    names = source_component_names(data)
    for item in data:
        if item.get("type") != "pcb_component":
            continue
        if names.get(item.get("source_component_id")) == refdes:
            return item
    return None


def pcb_component_center(refdes: str) -> tuple[float, float] | None:
    component = pcb_component_by_refdes(refdes)
    if component is None:
        return None
    return (float(component["center"]["x"]), float(component["center"]["y"]))


def pcb_component_size(refdes: str) -> tuple[float, float] | None:
    component = pcb_component_by_refdes(refdes)
    if component is None:
        return None
    return (float(component.get("width") or 0), float(component.get("height") or 0))


def pcb_front_sensor_cluster_bbox(margin: float = 4.0) -> tuple[float, float, float, float]:
    """Return (x_min, x_max, y_min, y_max) bounding all front-facing sensors in PCB frame.

    Computed from every tagged sensor in `FRONT_FACE_SENSOR_REFDES` plus the
    requested margin. All coordinates are in PCB-local frame; convert to case
    frame via `pcb_case_position()` if needed.
    """
    xs: list[float] = []
    ys: list[float] = []
    data = load_board_metadata()
    names = source_component_names(data)
    for item in data:
        if item.get("type") != "pcb_component":
            continue
        if names.get(item.get("source_component_id")) not in FRONT_FACE_SENSOR_REFDES:
            continue
        cx = float(item["center"]["x"])
        cy = float(item["center"]["y"])
        w = float(item.get("width") or 0) / 2.0
        h = float(item.get("height") or 0) / 2.0
        xs.extend([cx - w, cx + w])
        ys.extend([cy - h, cy + h])
    if not xs:
        raise ValueError(
            "No front-face sensors found on the PCB. Check that "
            f"{FRONT_FACE_SENSOR_REFDES!r} are placed in mimo-board."
        )
    return (min(xs) - margin, max(xs) + margin, min(ys) - margin, max(ys) + margin)


def pcb_shape_raw():
    return Compound([pcb_board_raw(), pcb_component_solids_raw()])


def pcb_shape():
    return pcb_shape_raw()


def pcb_in_case_raw():
    return pcb_shape_raw().translate((PCB_CASE_CENTER_X, PCB_CASE_CENTER_Y, PCB_CASE_CENTER_Z))


def pcb_in_case_viewer_shape():
    return viewer_aligned(pcb_in_case_raw())


def validate_pcb_mount_holes() -> None:
    holes = {(round(x, 3), round(y, 3), round(d, 3)) for x, y, d in pcb_holes(load_board_metadata())}
    for hole_x, hole_y in PCB_MOUNT_HOLES:
        if (round(hole_x, 3), round(hole_y, 3), 2.2) not in holes:
            raise ValueError(f"Expected PCB mounting hole not found at {(hole_x, hole_y)}")


def validate_usb_alignment() -> None:
    # USB-C cable insertion lands at PCB-frame coordinates from the schematic.
    # Verify the case-frame position is consistent with PCB metadata + case offsets,
    # not against frozen magic numbers. If the PCB design moves the connector,
    # the case auto-adapts.
    from mimo_case_geometry import BOTTOM_Y, CASE_HEIGHT
    usb_x, usb_y, _ = pcb_usb_c_opening_center()
    case_usb_x, case_usb_y, _ = pcb_case_position(usb_x, usb_y)
    # Derived expectation: connector should sit just inside the BOTTOM_Y face so
    # the case cutout reaches it without going through the back wall.
    if not (BOTTOM_Y < case_usb_y < BOTTOM_Y + (CASE_HEIGHT * 0.25)):
        raise ValueError(
            f"USB-C case Y={case_usb_y:.3f} should sit just inside BOTTOM_Y={BOTTOM_Y:.3f} "
            f"(within the bottom 25% of the case). "
            f"Check PCB_CASE_CENTER_Y and the J1 placement on the board."
        )
    if abs(case_usb_x) > (CASE_HEIGHT * 0.30):
        raise ValueError(
            f"USB-C case X={case_usb_x:.3f} is far from center (>30% of case width). "
            f"That's allowed by geometry but unusual; double-check the PCB layout."
        )
