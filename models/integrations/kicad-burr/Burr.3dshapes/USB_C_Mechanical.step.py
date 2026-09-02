from build123d import Align, Box, BuildPart, Color, Location, Locations


BOARD_TOP_Z = 1.51
CONNECTOR_WIDTH = 9.0
CONNECTOR_DEPTH = 8.0
CONNECTOR_HEIGHT = 3.5


def gen_step():
    """Return a closed USB-C mechanical envelope in the KiCad footprint frame."""
    with BuildPart() as connector:
        with Locations(Location((0.0, 0.0, BOARD_TOP_Z))):
            Box(
                CONNECTOR_WIDTH,
                CONNECTOR_DEPTH,
                CONNECTOR_HEIGHT,
                align=(Align.CENTER, Align.CENTER, Align.MIN),
            )

    part = connector.part
    part.label = "USB_C_mechanical_envelope"
    part.color = Color(0.72, 0.74, 0.76, 1.0)
    return {"shape": part}
