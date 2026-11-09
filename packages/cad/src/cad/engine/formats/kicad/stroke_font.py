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
text seen from the other side of the board, slanted for italic text as KiCad slants
its own (an eighth of a glyph's height above the baseline), and turned by its angle. A
character the font has no glyph for is drawn as a box the size of an ``X``.

With ``markup`` (every text KiCad draws: a schematic's, its drawing sheet's, and a board's -- its
silkscreen, fab and copper text, its footprints' fields, its pads' and tracks' net names), KiCad's text
markup is drawn as KiCad draws it rather than letter for letter: ``~{...}`` its content with a bar over
it, ``_{...}`` a subscript and ``^{...}`` a superscript (``SUPER_SUB_SIZE`` the size, shifted down or up
by a share of it), the markers themselves never drawn and the width, so the justification, measured on
what is drawn. :func:`parse_markup` reads it as KiCad's ``markup_parser.h`` does: markup nests; a marker
whose brace never closes, a stray brace, an escape sequence (``{slash}``) and a URL stay literal. The
viewer's twin (``@cad/core``'s ``plot2d/strokeFont.js``) reads and draws the same, held to the same cases
(its ``strokeFont.parity.json``).
"""

from __future__ import annotations

import math
import re
from typing import Sequence

__all__ = ["GLYPHS", "glyph_strokes", "parse_markup", "text_strokes"]

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
# KiCad's italic: a point moves right by this share of its height above the baseline (ITALIC_TILT).
_ITALIC_TILT = 1 / 8
#: KiCad's sub- and superscript: this share of the text's size (font.h's SUPER_SUB_SIZE_MULTIPLIER), a
#: subscript's baseline that share of its own size below, a superscript's above (SUB_ and SUPER_HEIGHT_OFFSET).
SUPER_SUB_SIZE = 0.8
_SUB_OFFSET = 0.15
_SUPER_OFFSET = 0.35
# KiCad's overbar: this many times the size above the baseline (as kicad-cli plots it), each end trimmed by
# a share of the size.
_OVERBAR_HEIGHT = 1.26
_OVERBAR_TRIM = 0.1


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


def _line_strokes(line: str, scale_x: float, scale_y: float, tilt: float = 0.0) -> tuple[float, list[list[tuple[float, float]]]]:
    """One line's strokes, the pen starting at x = 0 on the baseline, and the line's width."""
    strokes: list[list[tuple[float, float]]] = []
    pen = 0.0
    for character in line:
        left, right, glyph = glyph_strokes(character)
        for stroke in glyph:
            strokes.append([((pen + x - left) * scale_x - (y - _BASELINE) * scale_y * tilt, y * scale_y) for x, y in stroke])
        pen += right - left
    return pen * scale_x, strokes


_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def _escape_end(text: str, index: int) -> int:
    """Where an escape sequence (``{slash}``: a brace, an identifier, a brace) at ``index`` ends, or -1."""
    if not text.startswith("{", index):
        return -1
    found = _IDENTIFIER.match(text, index + 1)
    return found.end() + 1 if found and text.startswith("}", found.end()) else -1


def _url_end(text: str, index: int) -> int:
    """Where a URL at ``index`` (``http://`` or ``https://``, then at least one character, to the next space) ends, or -1."""
    for scheme in ("http://", "https://"):
        after = index + len(scheme)
        if text.startswith(scheme, index) and after < len(text) and text[after] != " ":
            space = text.find(" ", after)
            return len(text) if space < 0 else space
    return -1


def parse_markup(text: str) -> list:
    """``text`` as KiCad's markup parser reads it (``markup_parser.h``): runs, each a plain string or
    ``(marker, runs)`` for an overbar (``~``), a subscript (``_``) or a superscript (``^``). Markup
    nests. A marker whose brace never closes, a lone ``~``, ``_`` or ``^``, a stray brace, an escape
    sequence inside markup (``{slash}``, whose brace closes nothing) and a URL (``http://`` or
    ``https://`` to the next space) are text, as written.

    One pass with a stack of the markers open; a marker still open at the end is KiCad's failed match,
    text, and the text is read again with it so (whether a marker closes depends on nothing but where it is)."""
    failed: set[int] = set()
    while True:
        top: list = []
        stack: list[tuple[int, str, list]] = []  # (where, marker, runs) of each marker open

        def put(piece) -> None:
            runs = stack[-1][2] if stack else top
            if isinstance(piece, str) and runs and isinstance(runs[-1], str):
                runs[-1] += piece
            else:
                runs.append(piece)

        at = 0
        while at < len(text):
            character = text[at]
            if stack and character == "}":
                _where, marker, runs = stack.pop()
                put((marker, runs))
                at += 1
            elif character in "~_^" and text.startswith("{", at + 1) and at not in failed:
                stack.append((at, character, []))
                at += 2
            elif stack and (escape := _escape_end(text, at)) > 0:
                put(text[at:escape])
                at = escape
            elif not stack and (url := _url_end(text, at)) > 0:
                put(text[at:url])
                at = url
            else:
                put(character)
                at += 1
        if not stack:
            return top
        failed.update(where for where, _marker, _runs in stack)


def _markup_strokes(line: str, scale_x: float, scale_y: float, tilt: float) -> tuple[float, list[list[tuple[float, float]]]]:
    """One line's strokes with its markup drawn (the module doc), the pen from x = 0 on the baseline."""
    strokes: list[list[tuple[float, float]]] = []
    baseline = _BASELINE * scale_y

    def lay(runs: list, pen: float, scale: float, lift: float) -> float:
        # ``scale`` the run's size against the text's, ``lift`` its baseline above the text's (mm, up).
        for run in runs:
            if isinstance(run, str):
                for character in run:
                    left, right, glyph = glyph_strokes(character)
                    for stroke in glyph:
                        placed = []
                        for x, y in stroke:
                            up = -(y - _BASELINE) * scale_y * scale + lift
                            placed.append((pen + (x - left) * scale_x * scale + up * tilt, baseline - up))
                        strokes.append(placed)
                    pen += (right - left) * scale_x * scale
                continue
            marker, inner = run
            if marker == "~":
                start = pen
                pen = lay(inner, pen, scale, lift)
                height = _CAP_HEIGHT * scale_y * scale
                trim = _CAP_HEIGHT * scale_x * scale * _OVERBAR_TRIM
                bar = lift + height * _OVERBAR_HEIGHT
                if pen - start > 2 * trim:
                    strokes.append([(start + trim + bar * tilt, baseline - bar), (pen - trim + bar * tilt, baseline - bar)])
                continue
            small = scale * SUPER_SUB_SIZE
            size = _CAP_HEIGHT * scale_y * small
            pen = lay(inner, pen, small, lift - size * _SUB_OFFSET if marker == "_" else lift + size * _SUPER_OFFSET)
        return pen

    return lay(parse_markup(line), 0.0, 1.0, 0.0), strokes


def text_strokes(
    text: str,
    *,
    size: tuple[float, float],
    at: tuple[float, float] = (0.0, 0.0),
    angle: float = 0.0,
    justify: Sequence[str] = (),
    mirror: bool = False,
    italic: bool = False,
    markup: bool = False,
) -> list[list[tuple[float, float]]]:
    """``text`` as stroke polylines in millimetres, y down, placed as KiCad places text.

    ``size`` is KiCad's ``(size HEIGHT WIDTH)``: a capital stands ``HEIGHT`` tall, and the
    glyphs are ``WIDTH / HEIGHT`` as wide as the font draws them. ``at`` is the anchor the
    text is justified about: the centre of the capitals' box unless ``justify`` names
    ``left``, ``right``, ``top`` or ``bottom``. ``mirror`` flips the text about its anchor's
    vertical, as KiCad mirrors text seen from the far side of the board. ``angle`` is degrees
    counter-clockwise as seen on the board (KiCad's), applied last. A text of several lines
    stacks them downwards, each justified on its own. ``italic`` slants it as KiCad does. ``markup``
    draws KiCad's ``~{overbar}``, ``_{subscript}`` and ``^{superscript}`` as KiCad does (the module doc).
    """
    height, width = float(size[0]), float(size[1])
    if height <= 0:
        return []
    scale_y = height / _CAP_HEIGHT
    scale_x = (width if width > 0 else height) / _CAP_HEIGHT
    lines = str(text).split("\n")
    tilt = _ITALIC_TILT if italic else 0.0
    laid = [_markup_strokes(line, scale_x, scale_y, tilt) if markup and any(isinstance(run, tuple) for run in parse_markup(line))
            else _line_strokes(line, scale_x, scale_y, tilt) for line in lines]
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
