"""Material palette for the hypercar.

IMPORTANT -- colour space.  The render pipeline treats build123d ``Color``
channels as **linear** RGB and converts them to sRGB for display
(``packages/cadjs/src/lib/assembly/meshData.js`` ``linearChannelToSrgbByte``).
So ``Color(0.5, 0.5, 0.5)`` shows up as roughly ``#BCBCBC``, not ``#808080``.

Every colour here is therefore authored as the sRGB hex you actually want to
see and converted with :func:`srgb`.  Never hand-write raw float triples.

Also: a colour set on a *group* compound is ignored by the render package --
only leaf occurrences carry colour.  Use :func:`style` on every leaf.
"""

from __future__ import annotations

from build123d import Color


def _to_linear(channel_8bit):
    c = channel_8bit / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb(hex_string, alpha=1.0):
    """Build a Color from the sRGB hex you want to SEE on screen."""
    h = hex_string.lstrip("#")
    if len(h) == 3:
        h = "".join(ch * 2 for ch in h)
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return Color(_to_linear(r), _to_linear(g), _to_linear(b), alpha)


# ---------------------------------------------------------------------------
# the car's identity: deep red body, raw carbon aero, bronze jewellery, smoked
# glass.  Carbon is kept a cool neutral grey so it reads as a separate material
# against the red rather than as a darker shade of the paint.
# ---------------------------------------------------------------------------

BODY = "#C0121E"            # main painted panels -- deep saturated red
BODY_DARK = "#6B0A11"       # shadowed body areas, inner arch returns
CARBON = "#1C2024"          # exposed carbon.  Against the dark-blue body this
                            # was lifted to #2C3137 so it would not read as a
                            # hole; against red it has to go back to true
                            # carbon or the splitter and diffuser read as bare
                            # primer rather than a second material.
CARBON_GLOSS = "#24292E"    # carbon with a lighter weave read
BRONZE = "#B08D57"          # accent jewellery: hinges, badges, caliper
BRONZE_DARK = "#7C6238"
ALUMINIUM = "#9AA1A8"       # machined structure, uprights, links
ALUMINIUM_DARK = "#565C63"
TITANIUM = "#7E8288"        # exhaust, fasteners
STEEL_DARK = "#4A4F55"

GLASS = "#38414D"           # windscreen / side glass, smoked
GLASS_DARK = "#242A32"      # rear screen, darker tint
LENS_CLEAR = "#38434F"      # headlight lens -- smoked, the internals supply the sparkle
LENS_RED = "#5E0F19"        # taillight lens -- deep smoked red
LAMP_HOT = "#DDE9F5"        # DRL / lit internals
LAMP_RED_HOT = "#D9313E"

TYRE = "#17191C"
TYRE_WALL = "#1D2023"
RIM = "#8D949B"
RIM_DARK = "#3C4147"
DISC = "#6B7076"
DISC_FACE = "#8A9096"
CALIPER = "#A8763A"

MONOCOQUE = "#1A1D21"       # carbon tub
SUBFRAME = "#5C6268"
ENGINE = "#3E434A"
ENGINE_HOT = "#5A4A3E"
PLENUM = "#8A9198"
EXHAUST = "#736C64"

SEAT = "#22262B"
SEAT_STITCH = "#8A6A3A"
DASH = "#1E2126"
TRIM = "#2A2E34"
ALCANTARA = "#33373D"

# transparency for glazing (alpha rides on the occurrence colour)
GLASS_ALPHA = 0.42
LENS_ALPHA = 0.30


def style(shape, label, hex_string, alpha=1.0):
    """Label + colour a LEAF shape.  Returns the shape so it can be inlined."""
    shape.label = label
    shape.color = srgb(hex_string, alpha)
    return shape
