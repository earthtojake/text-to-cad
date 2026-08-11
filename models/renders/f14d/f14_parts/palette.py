"""Material palette for the F-14D.

COLOUR SPACE.  The render pipeline treats build123d ``Color`` channels as
LINEAR RGB and converts to sRGB for display, so ``Color(0.5,0.5,0.5)`` shows as
about ``#BCBCBC``.  Every colour here is authored as the sRGB hex you want to
SEE and converted by :func:`srgb`.  Never hand-write float triples.

COLOUR ON A GROUP IS IGNORED.  Only leaf occurrences carry colour into the
render package.  Use :func:`style` on every leaf.

Scheme: mid-1990s Tactical Paint Scheme (TPS) low-vis greys.  Chosen over
high-vis because the F-14's whole shape argument is made by its surface --
a two-tone grey with a hard demarcation lets the eye read the blend from glove
to nacelle to pancake, where 1970s gloss white bellies and coloured tails
would fight it.  The greys are the real FS numbers.
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


# --- airframe: Tactical Paint Scheme ---------------------------------------
# FS 36320 dark ghost grey over FS 36375 light ghost grey, with FS 35237 on the
# radome.  Values are the paint chips, lifted a little so they do not go muddy
# under the presentation lighting.
GREY_DARK = "#7E858C"       # FS 36320 dark ghost grey -- upper surfaces
GREY_LIGHT = "#A9B0B6"      # FS 36375 light ghost grey -- lower surfaces, fins
GREY_MID = "#939AA1"        # transition panels
RADOME = "#767F8B"          # FS 35237 blue-grey radome
DIELECTRIC = "#8A9199"      # antenna and aerial dielectric panels

# walkway / anti-skid and the darker service panels
WALKWAY = "#5E656B"
PANEL_DARK = "#6B7278"
PANEL_LIGHT = "#B6BDC3"

# --- hot / metallic ---------------------------------------------------------
TITANIUM = "#8A8F94"        # nozzle shroud, aft fairings
STEEL_BURN = "#6E6A66"      # heat-tinted steel around the nozzles
NOZZLE_PETAL = "#7A7671"    # external petals, soot-shadowed
NOZZLE_INNER = "#4A4642"    # inner petals seen down the nozzle
ENGINE_HOT = "#3A3734"      # engine internals through the nozzle
COMPRESSOR = "#9EA3A8"      # fan face blades
EXHAUST_SOOT = "#4E4B48"

# --- structure and mechanism ------------------------------------------------
GEAR_WHITE = "#C6CBCF"      # gloss white gear legs and bay interiors
BAY_GREEN = "#8E9A72"       # zinc chromate primer in the bays
OLEO_CHROME = "#C9CED3"     # polished oleo piston
ALUMINIUM = "#9AA1A8"
ALUM_DARK = "#6A7077"
STEEL_DARK = "#4A4F55"
BRASS = "#9C8A5E"
HYDRAULIC = "#5C6268"       # plumbing runs
WIRE_LOOM = "#3A3E43"
RUBBER = "#26292C"
TYRE = "#1D2023"
TYRE_WALL = "#242729"

# --- transparencies ---------------------------------------------------------
CANOPY_GLASS = "#96A6B4"    # the F-14 canopy is faintly gold-tinted acrylic
CANOPY_ALPHA = 0.30
CANOPY_FRAME = "#5A6167"
HUD_GLASS = "#8FB6A8"
HUD_ALPHA = 0.35

# --- cockpit ----------------------------------------------------------------
COCKPIT_BLACK = "#2A2D31"   # instrument panels and consoles
SEAT_BODY = "#40454A"       # GRU-7A structure
SEAT_CUSHION = "#3A4038"    # olive cushions
HARNESS = "#5B5F52"
HANDLE_YELLOW = "#C9B04E"   # ejection handles
HANDLE_BLACK = "#242629"

# --- lights and markings ----------------------------------------------------
LIGHT_RED = "#B23A3A"
LIGHT_GREEN = "#3E9E63"
LIGHT_WHITE = "#DDE4EA"
FORMATION = "#9BB7C6"       # electroluminescent formation strips
BEACON_RED = "#A83232"
INSIGNIA_BLUE = "#2E3E5C"   # low-vis national insignia
INSIGNIA_GREY = "#6E757B"
STENCIL = "#5A6167"
DEICE_BLACK = "#33363A"

# alpha helpers
GLASS_ALPHA = 0.30


def style(shape, label, hex_string, alpha=1.0):
    """Label + colour a LEAF shape.  Returns the shape so it can be inlined."""
    shape.label = label
    shape.color = srgb(hex_string, alpha)
    return shape
