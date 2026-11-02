"""Text on a board, as stroke polylines in a permissive font.

KiCad draws text with its own stroke font (newstroke), which is GPL, so the
viewer's picture of a board draws text with Hershey Simplex instead: the same
positions, sizes, rotations, mirroring and justification, different glyphs.

Hershey Simplex is one of the Hershey fonts, created by Dr. A. V. Hershey while
working at the U.S. National Bureau of Standards, and distributed since 1986 in
the format James Hurt (Cognition, Inc.) devised: freely usable for any purpose,
provided those two acknowledgements travel with the data and the data is not
sold in its original form. ``GLYPHS`` below is the Simplex Roman set for ASCII
32 to 126 in that format, as OpenCV ships it (``hershey_fonts.cpp``): each glyph
is two characters for its left and right bearings, then pairs of characters for
the points of its strokes, each coordinate the character's code minus ``R``,
y down, a space between strokes. Capitals stand 21 units tall, from y = -12 to
the baseline at y = 9; descenders reach y = 16.

:func:`text_strokes` lays a string out as KiCad lays its text out: each
character advanced by its own bearings, the whole string placed by its
justification about the anchor, scaled to KiCad's text size (``size`` is the
height of a capital, and the width scales the glyphs horizontally), mirrored for
text seen from the other side of the board, and turned by its angle. A
character the font has no glyph for is drawn as a box the size of an ``X``.
"""

from __future__ import annotations

import math
from typing import Sequence

__all__ = ["GLYPHS", "glyph_strokes", "text_strokes"]

#: ASCII 32 (space) to 126 (``~``), in the Hershey distribution's encoding (module doc).
GLYPHS: tuple[str, ...] = (
    'JZ', 'MWRFRT RYQZR[SZRY', 'JZNFNM VFVM',
    'G]OFOb UFUb JQZQ JWZW', 'H\\PBP_ TBT_ YIWGTFPFMGKIKKLMMNOOUQWRXSYUYXWZT[P[MZKX', 'F^[FYGVHSHPGNFLFJGIIIKKMMMOLPJPHNF [FI[ YTWTUUTWTYV[X[ZZ[X[VYT',
    'E_\\O\\N[MZMYNXPVUTXRZP[L[JZIYHWHUISJRQNRMSKSIRGPFNGMIMKNNPQUXWZY[[[\\Z\\Y', 'NVRFRM', 'KYVBTDRGPKOPOTPYR]T`Vb',
    'KYNBPDRGTKUPUTTYR]P`Nb', 'JZRLRX MOWU WOMU', 'E_RIR[ IR[R',
    'MWSZR[QZRYSZS\\R^Q_', 'E_IR[R', 'MWRYQZR[SZRY',
    'G][BIb', 'H\\QFNGLJKOKRLWNZQ[S[VZXWYRYOXJVGSFQF', 'H\\NJPISFS[',
    'H\\LKLJMHNGPFTFVGWHXJXLWNUQK[Y[', 'H\\MFXFRNUNWOXPYSYUXXVZS[P[MZLYKW', 'H\\UFKTZT UFU[',
    'H\\WFMFLOMNPMSMVNXPYSYUXXVZS[P[MZLYKW', 'H\\XIWGTFRFOGMJLOLTMXOZR[S[VZXXYUYTXQVOSNRNOOMQLT', 'H\\YFO[ KFYF',
    'H\\PFMGLILKMMONSOVPXRYTYWXYWZT[P[MZLYKWKTLRNPQOUNWMXKXIWGTFPF', 'H\\XMWPURRSQSNRLPKMKLLINGQFRFUGWIXMXRWWUZR[P[MZLX', 'MWRMQNROSNRM RYQZR[SZRY',
    'MWRMQNROSNRM SZR[QZRYSZS\\R^Q_', 'F^ZIJRZ[', 'E_IO[O IU[U',
    'F^JIZRJ[', 'I[LKLJMHNGPFTFVGWHXJXLWNVORQRT RYQZR[SZRY', 'DaWNVLTKQKOLNMMOMRNTOUQVTVVUWS WKWSXUYV[V\\U]S]O\\L[JYHWGTFQFNGLHJJILHOHRIUJWLYNZQ[T[WZYY',
    'I[RFJ[ RFZ[ MTWT', 'G\\KFK[ KFTFWGXHYJYLXNWOTP KPTPWQXRYTYWXYWZT[K[', 'H]ZKYIWGUFQFOGMILKKNKSLVMXOZQ[U[WZYXZV',
    'G\\KFK[ KFRFUGWIXKYNYSXVWXUZR[K[', 'H[LFL[ LFYF LPTP L[Y[', 'HZLFL[ LFYF LPTP',
    'H]ZKYIWGUFQFOGMILKKNKSLVMXOZQ[U[WZYXZVZS USZS', 'G]KFK[ YFY[ KPYP', 'NVRFR[',
    'JZVFVVUYTZR[P[NZMYLVLT', 'G\\KFK[ YFKT POY[', 'HYLFL[ L[X[',
    'F^JFJ[ JFR[ ZFR[ ZFZ[', 'G]KFK[ KFY[ YFY[', 'G]PFNGLIKKJNJSKVLXNZP[T[VZXXYVZSZNYKXIVGTFPF',
    'G\\KFK[ KFTFWGXHYJYMXOWPTQKQ', 'G]PFNGLIKKJNJSKVLXNZP[T[VZXXYVZSZNYKXIVGTFPF SWY]', 'G\\KFK[ KFTFWGXHYJYLXNWOTPKP RPY[',
    'H\\YIWGTFPFMGKIKKLMMNOOUQWRXSYUYXWZT[P[MZKX', 'JZRFR[ KFYF', 'G]KFKULXNZQ[S[VZXXYUYF',
    'I[JFR[ ZFR[', 'F^HFM[ RFM[ RFW[ \\FW[', 'H\\KFY[ YFK[',
    'I[JFRPR[ ZFRP', 'H\\YFK[ KFYF K[Y[', 'KYOBOb OBVB ObVb',
    'G]IL[b', 'KYUBUb NBUB NbUb', 'G]JTROZT JTRPZT',
    'I[J[Z[', 'LXPFUL PFOGUL', 'I\\XMX[ XPVNTMQMONMPLSLUMXOZQ[T[VZXX',
    'H[LFL[ LPNNPMSMUNWPXSXUWXUZS[P[NZLX', 'I[XPVNTMQMONMPLSLUMXOZQ[T[VZXX', 'I\\XFX[ XPVNTMQMONMPLSLUMXOZQ[T[VZXX',
    'I[LSXSXQWOVNTMQMONMPLSLUMXOZQ[T[VZXX', 'MYWFUFSGRJR[ OMVM', 'I\\XMX]W`VaTbQbOa XPVNTMQMONMPLSLUMXOZQ[T[VZXX',
    'I\\MFM[ MQPNRMUMWNXQX[', 'NVQFRGSFREQF RMR[', 'MWRFSGTFSERF SMS^RaPbNb',
    'IZMFM[ WMMW QSX[', 'NVRFR[', 'CaGMG[ GQJNLMOMQNRQR[ RQUNWMZM\\N]Q][',
    'I\\MMM[ MQPNRMUMWNXQX[', 'I\\QMONMPLSLUMXOZQ[T[VZXXYUYSXPVNTMQM', 'H[LMLb LPNNPMSMUNWPXSXUWXUZS[P[NZLX',
    'I\\XMXb XPVNTMQMONMPLSLUMXOZQ[T[VZXX', 'KXOMO[ OSPPRNTMWM', 'J[XPWNTMQMNNMPNRPSUTWUXWXXWZT[Q[NZMX',
    'MYRFRWSZU[W[ OMVM', 'I\\MMMWNZP[S[UZXW XMX[', 'JZLMR[ XMR[',
    'G]JMN[ RMN[ RMV[ ZMV[', 'J[MMX[ XMM[', 'JZLMR[ XMR[P_NaLbKb',
    'J[XMM[ MMXM M[X[', 'KYTBQEPHPJQMSOSPORSTSUQWPZP\\Q_Tb', 'NVRBRb',
    'KYPBSETHTJSMQOQPURQTQUSWTZT\\S_Pb', 'F^IUISJPLONOPPTSVTXTZS[Q ISJQLPNPPQTTVUXUZT[Q[O',
)

_CAP_TOP = -12.0
_BASELINE = 9.0
_CAP_HEIGHT = _BASELINE - _CAP_TOP
# KiCad's own stroke font puts the gap between two lines of text at about 1.6 times the size.
_LINE_SPACING = 1.62


def _decode(glyph: str) -> tuple[float, float, list[list[tuple[float, float]]]]:
    """A glyph's left and right bearings and its strokes, in the font's 21-unit grid."""
    left, right = ord(glyph[0]) - 82, ord(glyph[1]) - 82
    strokes: list[list[tuple[float, float]]] = []
    stroke: list[tuple[float, float]] = []
    index = 2
    while index < len(glyph):
        if glyph[index] == " ":
            if stroke:
                strokes.append(stroke)
                stroke = []
            index += 1
            continue
        stroke.append((float(ord(glyph[index]) - 82), float(ord(glyph[index + 1]) - 82)))
        index += 2
    if stroke:
        strokes.append(stroke)
    return float(left), float(right), strokes


_DECODED = [_decode(glyph) for glyph in GLYPHS]


def glyph_strokes(character: str) -> tuple[float, float, list[list[tuple[float, float]]]]:
    """``(left, right, strokes)`` of one character in the font's grid: its bearings (the pen
    starts at ``left`` and leaves at ``right``) and its strokes, y down, baseline at 9. A
    character outside ASCII is a box the width of an ``X``."""
    code = ord(character)
    if 32 <= code <= 126:
        return _DECODED[code - 32]
    left, right, _strokes = _DECODED[ord("X") - 32]
    box = [(left + 1, _CAP_TOP), (right - 1, _CAP_TOP), (right - 1, _BASELINE), (left + 1, _BASELINE), (left + 1, _CAP_TOP)]
    return left, right, [box]


def _line_strokes(line: str, scale_x: float, scale_y: float) -> tuple[float, list[list[tuple[float, float]]]]:
    """One line's strokes, the pen starting at x = 0 on the baseline, and the line's width."""
    strokes: list[list[tuple[float, float]]] = []
    pen = 0.0
    for character in line:
        left, right, glyph = glyph_strokes(character)
        for stroke in glyph:
            strokes.append([((pen + x - left) * scale_x, y * scale_y) for x, y in stroke])
        pen += right - left
    return pen * scale_x, strokes


def text_strokes(
    text: str,
    *,
    size: tuple[float, float],
    at: tuple[float, float] = (0.0, 0.0),
    angle: float = 0.0,
    justify: Sequence[str] = (),
    mirror: bool = False,
) -> list[list[tuple[float, float]]]:
    """``text`` as stroke polylines in millimetres, y down, placed as KiCad places text.

    ``size`` is KiCad's ``(size HEIGHT WIDTH)``: a capital stands ``HEIGHT`` tall, and the
    glyphs are ``WIDTH / HEIGHT`` as wide as the font draws them. ``at`` is the anchor the
    text is justified about: the centre of the capitals' box unless ``justify`` names
    ``left``, ``right``, ``top`` or ``bottom``. ``mirror`` flips the text about its anchor's
    vertical, as KiCad mirrors text seen from the far side of the board. ``angle`` is degrees
    counter-clockwise as seen on the board (KiCad's), applied last. A text of several lines
    stacks them downwards, each justified on its own.
    """
    height, width = float(size[0]), float(size[1])
    if height <= 0:
        return []
    scale_y = height / _CAP_HEIGHT
    scale_x = (width if width > 0 else height) / _CAP_HEIGHT
    lines = str(text).split("\n")
    laid = [_line_strokes(line, scale_x, scale_y) for line in lines]
    line_height = height * _LINE_SPACING
    block_height = height + line_height * (len(lines) - 1)
    # Where the first line's capitals' centre lands against the anchor: on it, or half the
    # block away so the anchor is the block's top or bottom edge.
    first_centre = 0.0
    if "top" in justify:
        first_centre = height / 2
    elif "bottom" in justify:
        first_centre = height / 2 - block_height
    centre_offset = -(_CAP_TOP + _BASELINE) / 2 * scale_y  # the capitals' box centred on y = 0
    radians = math.radians(angle)
    cos, sin = math.cos(radians), math.sin(radians)
    out: list[list[tuple[float, float]]] = []
    for number, (line_width, strokes) in enumerate(laid):
        shift_x = 0.0 if "left" in justify else -line_width if "right" in justify else -line_width / 2
        shift_y = centre_offset + first_centre + number * line_height
        for stroke in strokes:
            placed = []
            for x, y in stroke:
                lx, ly = x + shift_x, y + shift_y
                if mirror:
                    lx = -lx
                # KiCad's rotation in its y-down frame: counter-clockwise on screen.
                placed.append((at[0] + lx * cos + ly * sin, at[1] - lx * sin + ly * cos))
            out.append(placed)
    return out
