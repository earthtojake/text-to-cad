"""What a person's terminal gets on top of the plain lines (``Screen`` decides): the CAD logo built at the start
(``play_logo``: sketched, extruded, as the site's animated logo is), a live line under the printed ones saying which
app is being set up and the command it is running (``Live``), and a mark on each app's line. Anywhere else (a pipe or
a file, a run a server began, CI, NO_COLOR, TERM=dumb) the output is the plain lines alone.

The standard library alone.
"""

from __future__ import annotations

import math
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple

from .computer import Here

# The logo's letters, C, A and D, as models/branding/src/profiles.json draws them (its points on a straight run
# dropped): loops in its units, y down, each letter 3 wide and 4 high, one ADVANCE after the last.
LOGO_LETTERS = (
    (((0, 0), (3, 0), (3, 1.5), (1.5, 1.5), (1.5, 2.5), (3, 2.5), (3, 4), (0, 4)),),
    (((0, 0.5), (0.5, 0), (2.5, 0), (3, 0.5), (3, 4), (2, 4), (2, 3.5), (1, 3.5), (1, 4), (0, 4)),
     ((1, 1.5), (1, 2.5), (2, 2.5), (2, 1.5))),
    (((0, 0), (2.5, 0), (3, 0.5), (3, 3.5), (2.5, 4), (0, 4)),
     ((1, 1.5), (1, 2.5), (2, 2.5), (2, 1.5))),
)
LOGO_ADVANCE = 3.5  # profiles.json's width and gap
LOGO_DEPTH = 2.0    # its depth
LOGO_SLANT = 0.42   # the logo's oblique view: the depth of 2 shows 0.84 right and 0.84 up
# The logo's colours (apps/docs/public/brand/logo-cad.svg): its faces' gradients, its edges, and the sketch's grid.
LOGO_FRONT = ((0x39, 0xB0, 0xE9), (0x24, 0x9D, 0xDD), (0x17, 0x85, 0xBF))
LOGO_TOP = ((0x94, 0xD9, 0xFA), (0x51, 0xAD, 0xE1))
LOGO_SIDE = ((0x25, 0x8C, 0xC5), (0x0B, 0x58, 0x87))
LOGO_EDGE = (0x12, 0x3E, 0x59)
LOGO_GRID = (0x3B, 0x6E, 0x8C)
# Where a terminal has xterm's 256 colours alone (macOS Terminal), one of them for each face, the nearest to the logo's
# by eye: front, top, right side, a chamfer, edges.
LOGO_FLAT = ((0x00, 0x87, 0xD7), (0x87, 0xD7, 0xFF), (0x00, 0x5F, 0xAF), (0x00, 0x87, 0xAF), (0x00, 0x00, 0x5F))
LOGO_FPS = 30
TAGLINE = "Design physical products with AI."

Colour = Tuple[int, int, int]
Pixels = List[List[Optional[Colour]]]


def _mix(one: Colour, other: Colour, amount: float) -> Colour:
    amount = min(1.0, max(0.0, amount))
    return (round(one[0] + (other[0] - one[0]) * amount), round(one[1] + (other[1] - one[1]) * amount),
            round(one[2] + (other[2] - one[2]) * amount))


def _ramp(stops: Sequence[Colour], at: float) -> Colour:
    at = min(1.0, max(0.0, at)) * (len(stops) - 1)
    index = min(int(at), len(stops) - 2)
    return _mix(stops[index], stops[index + 1], at - index)


def _ease(at: float) -> float:
    return 1 - (1 - min(1.0, max(0.0, at))) ** 3


def _edges(loop: Sequence[Tuple[float, float]]) -> List[Tuple[Tuple[float, float], Tuple[float, float]]]:
    return list(zip(loop, [*loop[1:], loop[0]]))


def _inside(loops: Sequence[Sequence[Tuple[float, float]]], x: float, y: float) -> bool:
    hit = False
    for loop in loops:
        for (ax, ay), (bx, by) in _edges(loop):
            if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
                hit = not hit
    return hit


class Logo:
    """The CAD block logo in pixels, ``scale`` to a unit: what each pixel's ray meets, worked out once (the front
    face, or the first side face and how deep it is), so a frame at any depth of the extrusion is a lookup."""

    def __init__(self, scale: int, flat: bool = False) -> None:
        self.scale = scale
        self.flat = flat  # each face one colour: xterm's 256 would band the gradients
        self.lift = LOGO_DEPTH * LOGO_SLANT  # the top face rises above y = 0
        self.width = math.ceil((LOGO_ADVANCE * (len(LOGO_LETTERS) - 1) + 3 + self.lift) * scale) + 1
        self.height = math.ceil((4 + self.lift) * scale) + 1
        self.hits = [[self._hit((px + 0.5) / scale, (py + 0.5) / scale - self.lift) for px in range(self.width)]
                     for py in range(self.height)]

    def _hit(self, u: float, v: float) -> Optional[Tuple[float, int, Optional[Tuple[float, float]], float, float]]:
        """(depth, letter, the face's normal or None for the front, x, y where it is met), or None."""
        best = None
        for index, loops in enumerate(LOGO_LETTERS):
            x = u - index * LOGO_ADVANCE
            if not -0.1 < x < 3 + self.lift + 0.1:
                continue
            if _inside(loops, x, v):
                return (0.0, index, None, x, v)
            # Deeper is (x, v) + z * (-SLANT, SLANT): the first edge that line crosses is the face it meets.
            for loop in loops:
                for (ax, ay), (bx, by) in _edges(loop):
                    ex, ey = bx - ax, by - ay
                    det = LOGO_SLANT * ey + LOGO_SLANT * ex
                    if abs(det) < 1e-12:
                        continue  # a face seen edge on
                    rx, ry = ax - x, ay - v
                    z = (ex * ry - ey * rx) / det
                    along = (-LOGO_SLANT * ry - LOGO_SLANT * rx) / det
                    if z > 0 and 0 <= along <= 1 and (best is None or z < best[0]):
                        length = math.hypot(ex, ey)
                        nx, ny = ey / length, -ex / length
                        if nx - ny < 0:  # the face's side the view sees
                            nx, ny = -nx, -ny
                        best = (z, index, (nx, ny), x - LOGO_SLANT * z, v + LOGO_SLANT * z)
        return best

    def solid(self, depth: float = LOGO_DEPTH, filled: float = 1.0, glint: Optional[float] = None) -> Pixels:
        """The letters extruded ``depth`` deep, their front faces ``filled`` (0-1) from the sketch's blue to their
        own, a light band at x = ``glint`` across them, and the model's edges drawn dark."""
        colours: Pixels = []
        faces: List[List[Optional[Tuple[float, ...]]]] = []
        for row in self.hits:
            colour_row: List[Optional[Colour]] = []
            face_row: List[Optional[Tuple[float, ...]]] = []
            for hit in row:
                if hit is None or hit[0] > depth + 1e-9:
                    colour_row.append(None)
                    face_row.append(None)
                    continue
                z, index, normal, x, y = hit
                shade = (x / 3 + y / 4) / 2
                if normal is None:
                    colour = LOGO_FLAT[0] if self.flat else _mix(LOGO_FRONT[1], _ramp(LOGO_FRONT, shade), filled)
                    face: Tuple[float, ...] = (index, 2.0, 2.0)
                else:
                    up, right = max(0.0, -normal[1]), max(0.0, normal[0])
                    if self.flat:
                        colour = LOGO_FLAT[1] if not right else LOGO_FLAT[2] if not up else LOGO_FLAT[3]
                    else:
                        colour = _mix(_ramp(LOGO_SIDE, shade), _ramp(LOGO_TOP, shade), up / (up + right))
                    face = (index, round(normal[0], 2), round(normal[1], 2))
                if glint is not None:
                    band = abs(x + index * LOGO_ADVANCE + y * 0.6 - glint)
                    if band < 0.6:
                        colour = _mix(colour, (255, 255, 255), 0.55 * (1 - band / 0.6))
                colour_row.append(colour)
                face_row.append(face)
            colours.append(colour_row)
            faces.append(face_row)
        drawn = [list(row) for row in colours]
        for py, face_row in enumerate(faces):
            for px, face in enumerate(face_row):
                if face is None:
                    continue
                for qx, qy in ((px + 1, py), (px, py + 1), (px - 1, py), (px, py - 1)):
                    other = faces[qy][qx] if 0 <= qy < self.height and 0 <= qx < self.width else None
                    if other is None or (other != face and other < face):  # one pixel per edge, on one side
                        drawn[py][px] = LOGO_FLAT[4] if self.flat else LOGO_EDGE
                        break
        return drawn

    def sketch(self, done: float) -> Pixels:
        """The profiles' outlines on the front plane, each traced ``done`` (0-1) of the way round."""
        drawn: Pixels = [[None] * self.width for _ in range(self.height)]
        step = 0.5 / self.scale
        for index, loops in enumerate(LOGO_LETTERS):
            for loop in loops:
                edges = _edges(loop)
                left = done * sum(math.hypot(bx - ax, by - ay) for (ax, ay), (bx, by) in edges)
                for (ax, ay), (bx, by) in edges:
                    length = math.hypot(bx - ax, by - ay)
                    travelled = 0.0
                    while travelled <= min(length, left):
                        at = travelled / length
                        px = int((ax + (bx - ax) * at + index * LOGO_ADVANCE) * self.scale)
                        py = int((ay + (by - ay) * at + self.lift) * self.scale)
                        if 0 <= px < self.width and 0 <= py < self.height:
                            drawn[py][px] = LOGO_FLAT[0] if self.flat else LOGO_FRONT[0]
                        travelled += step
                    left -= length
                    if left <= 0:
                        break
        return drawn

    def frames(self) -> List[Tuple[Pixels, float]]:
        """The build, about 1.6 s: sketched on a grid, filled, extruded, and a glint across it. Each frame's
        pixels and how strongly the grid shows."""
        def steps(seconds: float) -> List[float]:
            count = max(2, int(seconds * LOGO_FPS))
            return [index / (count - 1) for index in range(count)]

        built: List[Tuple[Pixels, float]] = []
        built += [(self.sketch(_ease(at)), min(1.0, at * 3)) for at in steps(0.45)]
        built += [(self.solid(depth=0, filled=at), 1.0) for at in steps(0.15)]
        built += [(self.solid(depth=LOGO_DEPTH * _ease(at)), 1 - at) for at in steps(0.55)]
        built += [(self.solid(glint=-2 + 16 * at), 0.0) for at in steps(0.45)]
        built.append((self.solid(), 0.0))
        return built


def _xterm(colour: Colour) -> int:
    """The nearest of the 256 colours of xterm's palette, for a terminal without 24-bit colour."""
    def level(value: int) -> int:
        return 0 if value < 48 else 1 if value < 115 else (value - 35) // 40

    r, g, b = (level(value) for value in colour)
    steps = (0, 95, 135, 175, 215, 255)
    grey = min(23, max(0, round((sum(colour) / 3 - 8) / 10)))

    def distance(other: Sequence[int]) -> int:
        return sum((one - two) ** 2 for one, two in zip(colour, other))

    if distance((8 + 10 * grey,) * 3) < distance((steps[r], steps[g], steps[b])):
        return 232 + grey
    return 16 + 36 * r + 6 * g + b


def half_blocks(pixels: Pixels, truecolor: bool, grid: float = 0.0, scale: int = 6) -> List[str]:
    """Terminal lines of ``pixels``, two to a character cell (``▀``: the upper one the foreground, the lower the
    background); an empty cell on a grid point gets a dot as strong as ``grid`` (0-1)."""
    def paint(layer: int, colour: Colour) -> str:
        if truecolor:
            return f"{layer};2;{colour[0]};{colour[1]};{colour[2]}"
        return f"{layer};5;{_xterm(colour)}"

    lines = []
    for py in range(0, len(pixels), 2):
        upper = pixels[py]
        lower = pixels[py + 1] if py + 1 < len(pixels) else [None] * len(upper)
        cells = []
        for px, (top, bottom) in enumerate(zip(upper, lower)):
            if top is None and bottom is None:
                dot = grid > 0 and px % scale == 0 and (py // 2) % max(1, scale // 2) == 0
                cells.append(f"\x1b[{paint(38, _mix((0, 0, 0), LOGO_GRID, grid))}m·\x1b[0m" if dot else " ")
            elif bottom is None:
                cells.append(f"\x1b[{paint(38, top)}m▀\x1b[0m")  # type: ignore[arg-type]
            elif top is None:
                cells.append(f"\x1b[{paint(38, bottom)}m▄\x1b[0m")
            elif top == bottom:
                cells.append(f"\x1b[{paint(38, top)}m█\x1b[0m")
            else:
                cells.append(f"\x1b[{paint(38, top)};{paint(48, bottom)}m▀\x1b[0m")
        lines.append("".join(cells).rstrip())
    return lines


def _windows_vt(stream: Any) -> bool:
    """Whether a Windows console takes the terminal's escape sequences: turned on for this process where it can be."""
    try:
        import ctypes
        import msvcrt

        kernel = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = msvcrt.get_osfhandle(stream.fileno())
        mode = ctypes.c_uint32()
        if not kernel.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        return bool(mode.value & 0x0004 or kernel.SetConsoleMode(handle, mode.value | 0x0004))
    except Exception:  # noqa: BLE001 - no console, or one too old: the plain lines
        return False


class Screen:
    """What the terminal this prints to can show: ``live``, whether it is a person's terminal at all (else only the
    plain lines are printed), ``truecolor`` (else xterm's 256 colours) and ``unicode`` (else ASCII marks, a Windows
    console outside Windows Terminal)."""

    def __init__(self, here: Here, stream: Any) -> None:
        environ = here.environ
        try:
            terminal = stream.isatty()
        except (AttributeError, OSError, ValueError):
            terminal = False
        self.live = (terminal and environ.get("TERM") != "dumb" and "NO_COLOR" not in environ
                     and not environ.get("CI") and (not here.windows or _windows_vt(stream)))
        self.truecolor = (environ.get("COLORTERM", "").lower() in ("truecolor", "24bit") or "WT_SESSION" in environ
                          or environ.get("TERM_PROGRAM") in ("iTerm.app", "WezTerm", "vscode", "ghostty"))
        self.unicode = not here.windows or "WT_SESSION" in environ

    @property
    def colour(self) -> str:
        """The colours this run draws in, in a word: ``24bit``, ``256``, or ``none`` where only the plain lines are
        printed."""
        return "none" if not self.live else "24bit" if self.truecolor else "256"

    @staticmethod
    def size() -> os.terminal_size:
        return shutil.get_terminal_size((80, 24))


# What ``play_logo`` showed: the logo built frame by frame, its last frame alone, or nothing.
PLAYED, STILL, NONE = "played", "still", "none"


def play_logo(screen: Screen, stream: Any) -> str:
    """The logo built in place, its last frame left on the screen with the tagline under it. Skipped where the
    terminal is too narrow; a terminal too short to redraw it in place gets the last frame alone. What it showed:
    ``PLAYED``, ``STILL`` or ``NONE``."""
    columns, rows = screen.size()
    scale = next((scale for scale in (5, 4) if (LOGO_ADVANCE * 2 + 3.9) * scale + 4 <= columns and (scale < 5 or rows >= 24)), 0)
    if not scale:
        return NONE
    logo = Logo(scale, flat=not screen.truecolor)
    height = (logo.height + 1) // 2
    frames = logo.frames() if rows >= height + 4 else [(logo.solid(), 0.0)]
    stream.write("\x1b[?25l\n")
    try:
        for index, (pixels, grid) in enumerate(frames):
            started = time.monotonic()
            lines = half_blocks(pixels, screen.truecolor, grid, scale)
            stream.write(("" if index == 0 else f"\x1b[{height}A")
                         + "".join(f"\r\x1b[2K{line}\n" for line in lines))
            stream.flush()
            if len(frames) > 1:
                time.sleep(max(0.0, 1 / LOGO_FPS - (time.monotonic() - started)))
        stream.write(f"\n\x1b[1mtext-to-cad\x1b[0m  \x1b[2m{TAGLINE}\x1b[0m\n\n")
    finally:
        stream.write("\x1b[?25h")
        stream.flush()
    return PLAYED if len(frames) > 1 else STILL


class Live:
    """The live line under the printed ones: a spinner, what is being set up (``begin``), the command it is running
    (``Here.watch``) and, after a few seconds, for how long. It stands in for the output stream, so a line printed
    anywhere clears it first, and it is drawn again under that line. Drawn only for a step that takes a moment."""

    SPIN = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    SPIN_ASCII = "|/-\\"
    DELAY = 0.15  # a step quicker than this never shows the line

    def __init__(self, screen: Screen, stream: Any, home: str = "") -> None:
        self.screen = screen
        self.stream = stream
        self.home = home
        self.lock = threading.RLock()
        self.label = ""
        self.detail = ""
        self.since = 0.0
        self.drawn = False
        self.at_start = True
        self.done = threading.Event()
        self.thread = threading.Thread(target=self._run, name="install-live", daemon=True)

    # The stream's face, for print() and anything else that writes to sys.stdout.
    def write(self, text: str) -> int:
        with self.lock:
            self._clear()
            written = self.stream.write(text)
            if text:
                self.at_start = text.endswith("\n")
            return written

    def flush(self) -> None:
        with self.lock:
            self.stream.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.stream, name)

    def start(self) -> "Live":
        self.stream.write("\x1b[?25l")
        self.thread.start()
        return self

    def close(self) -> None:
        self.done.set()
        if self.thread.is_alive():
            self.thread.join(1)
        with self.lock:
            self._clear()
            self.stream.write("\x1b[?25h")
            self.stream.flush()

    def begin(self, label: str) -> None:
        with self.lock:
            self.label, self.detail, self.since = label, "", time.monotonic()

    def end(self) -> None:
        with self.lock:
            self.label = ""
            self._clear()
            self.stream.flush()

    def watch(self, argv: Optional[Sequence[Any]]) -> None:
        """What ``Here`` runs: the command shown on the line; None, a command that writes to the terminal itself,
        so the line is gone until the next ``begin``."""
        if argv is None:
            self.end()
            return
        words = [Path(str(argv[0])).name, *(str(word) for word in argv[1:])]
        text = " ".join(words)
        if self.home:
            text = text.replace(self.home, "~")
        with self.lock:
            self.detail = text

    def mark(self, line: str, status: str) -> str:
        """An app's line with a mark for how it went."""
        tick, cross, dot = ("✓", "✗", "·") if self.screen.unicode else ("+", "x", "-")
        if status in ("installed", "updated", "removed"):
            return f"\x1b[32m{tick}\x1b[0m {line}"
        if status == "failed":
            return f"\x1b[31m{cross}\x1b[0m {line}"
        return f"\x1b[2m{dot} {line}\x1b[0m"

    def _clear(self) -> None:
        if self.drawn:
            self.stream.write("\r\x1b[2K")
            self.drawn = False

    def _run(self) -> None:
        spin = self.SPIN if self.screen.unicode else self.SPIN_ASCII
        turn = 0
        while not self.done.wait(0.08):
            turn += 1
            with self.lock:
                taken = time.monotonic() - self.since
                if not self.label or not self.at_start or taken < self.DELAY:
                    continue
                columns = self.screen.size().columns - 1
                head = f"{spin[turn % len(spin)]} {self.label}"
                tail = f"  {int(taken)}s" if taken >= 3 else ""
                room = columns - len(head) - len(tail) - 2
                detail = self.detail if len(self.detail) <= room else self.detail[:max(0, room - 1)] + "…"
                line = f"\x1b[36m{head[0]}\x1b[0m{head[1:]}" + (f"  \x1b[2m{detail}\x1b[0m" if room > 4 and detail
                                                                     else "") + f"\x1b[2m{tail}\x1b[0m"
                self.stream.write("\r\x1b[2K" + line)
                self.stream.flush()
                self.drawn = True
