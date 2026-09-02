from pathlib import Path

from build123d import Align, Box, BuildPart, Color, Compound, Location, Locations, Mode, import_step


# Units: millimeters.
# Coordinate frame: inherited from KiCad's STEP export.
#   X: board width, 0..40.
#   Y: board depth, -25..0, with the USB-C connector protruding through +Y.
#   Z: board bottom at 0, populated side in +Z.

BOARD_STEP = Path(__file__).with_name("controller.step")

BOARD_WIDTH = 40.0
BOARD_DEPTH = 25.0
ENCLOSURE_HEIGHT = 8.0
WALL_THICKNESS = 2.0
BASE_THICKNESS = 2.0
BOARD_CLEARANCE = 0.25

USB_CUTOUT_MIN_X = 14.5
USB_CUTOUT_WIDTH = 11.0
USB_CUTOUT_BOTTOM_Z = 0.25
USB_CUTOUT_HEIGHT = 7.0

ENCLOSURE_COLOR = Color(0.12, 0.32, 0.52, 1.0)


def _box_at(
    x: float,
    y: float,
    z: float,
    length: float,
    width: float,
    height: float,
    *,
    mode: Mode = Mode.ADD,
) -> None:
    with Locations(Location((x, y, z))):
        Box(
            length,
            width,
            height,
            align=(Align.MIN, Align.MIN, Align.MIN),
            mode=mode,
        )


def _make_enclosure(*, with_usb_cutout: bool):
    outer_min_x = -WALL_THICKNESS - BOARD_CLEARANCE
    outer_min_y = -BOARD_DEPTH - WALL_THICKNESS - BOARD_CLEARANCE
    outer_length = BOARD_WIDTH + 2.0 * (WALL_THICKNESS + BOARD_CLEARANCE)
    outer_width = BOARD_DEPTH + 2.0 * (WALL_THICKNESS + BOARD_CLEARANCE)

    with BuildPart() as enclosure:
        _box_at(
            outer_min_x,
            outer_min_y,
            -BASE_THICKNESS - BOARD_CLEARANCE,
            outer_length,
            outer_width,
            BASE_THICKNESS,
        )
        _box_at(
            outer_min_x,
            outer_min_y,
            0.0,
            WALL_THICKNESS,
            outer_width,
            ENCLOSURE_HEIGHT,
        )
        _box_at(
            BOARD_WIDTH + BOARD_CLEARANCE,
            outer_min_y,
            0.0,
            WALL_THICKNESS,
            outer_width,
            ENCLOSURE_HEIGHT,
        )
        _box_at(
            0.0,
            outer_min_y,
            0.0,
            BOARD_WIDTH,
            WALL_THICKNESS,
            ENCLOSURE_HEIGHT,
        )
        _box_at(
            0.0,
            BOARD_CLEARANCE,
            0.0,
            BOARD_WIDTH,
            WALL_THICKNESS,
            ENCLOSURE_HEIGHT,
        )

        if with_usb_cutout:
            _box_at(
                USB_CUTOUT_MIN_X,
                0.0,
                USB_CUTOUT_BOTTOM_Z,
                USB_CUTOUT_WIDTH,
                WALL_THICKNESS + 0.5,
                USB_CUTOUT_HEIGHT,
                mode=Mode.SUBTRACT,
            )

    part = enclosure.part
    part.label = "enclosure_with_usb_c_cutout" if with_usb_cutout else "enclosure_blocking_usb_c"
    part.color = ENCLOSURE_COLOR
    return part


def build_assembly(*, with_usb_cutout: bool):
    if not BOARD_STEP.is_file():
        raise FileNotFoundError(
            f"Missing KiCad STEP export: {BOARD_STEP}. Export controller.kicad_pcb before building the assembly."
        )

    imported_controller = import_step(BOARD_STEP)
    controller = Compound(
        obj=list(imported_controller.solids()),
        label="controller_board_from_kicad",
    )
    enclosure = _make_enclosure(with_usb_cutout=with_usb_cutout)
    state = "pass" if with_usb_cutout else "fail"

    return Compound(
        obj=[controller, enclosure],
        children=[controller, enclosure],
        label=f"kicad_burr_handoff_{state}",
    )
