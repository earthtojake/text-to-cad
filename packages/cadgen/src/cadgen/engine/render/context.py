"""A headless OCCT view: an OpenGL context on a window nobody sees, drawn into off-screen frame
buffers by ``V3d_View.ToPixMap`` at the exact pixel size asked, and encoded as a PNG in memory.

Each canvas has an OpenGL driver of its own (``driver``): a context its window owns, made and
let go of with it, as a long-lived process makes and drops canvases (a driver shared by them
holds the first window's context, and draws through a window that is gone once that canvas is
dropped). The window it draws through is the platform's:

- **macOS**: a Cocoa window never ordered front (``Cocoa_Window``), on the process's
  ``NSApplication``. A canvas is made and drawn inside an autorelease pool of its own, so a
  process that makes canvases for its life keeps nothing AppKit autoreleases for each.
- **Linux**: OCP's Linux build draws through GLX, which needs an X server: an X display's window,
  virtual (never mapped: ``Xw_Window`` with ``SetVirtual``), on ``$DISPLAY`` -- Xvfb on a machine
  with no screen. An OCCT built with EGL and no Xlib makes its context on ``EGL_DEFAULT_DISPLAY``,
  no X server at all, and a neutral virtual window stands in for the X window. With neither, a
  canvas is refused by name (``Unavailable``), and the refusal names Xvfb.
- **Windows**: a popup window never shown (``CreateWindowExW`` of the ``STATIC`` class) handed to
  ``WNT_Window``.

A picture leaves OCCT as sRGB bytes (``frame``: height x width x 3, for whatever paints over it)
and is encoded as a PNG in memory (``png``); ``tile`` draws one rectangle of the frame alone, with
the whole frame's projection.

``available()`` says whether a canvas can be made here, and why not when it cannot: what a test
skips on (and, on CI with an X display, fails on). Only the macOS path is proven; ``test_render.py`` says what the first Linux and Windows
runs must show.
"""

from __future__ import annotations

import contextlib
import io
import os
import struct
import sys
import threading
import time
import zlib
from typing import Any, Callable, Iterator

import numpy as np

__all__ = ["Canvas", "Unavailable", "available", "driver", "platform", "pool"]


class Unavailable(RuntimeError):
    """No OpenGL context can be made in this process, and why."""


def platform() -> str:
    """``darwin``, ``linux`` or ``windows``: which window a canvas draws through."""
    if sys.platform == "darwin":
        return "darwin"
    if os.name == "nt":
        return "windows"
    return "linux"


# --- macOS ---------------------------------------------------------------------------------

_APP = None
_OBJC = None


def _objc() -> Any:
    global _OBJC
    if _OBJC is None:
        import ctypes
        import ctypes.util

        objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library("objc"))
        objc.objc_getClass.restype = ctypes.c_void_p
        objc.sel_registerName.restype = ctypes.c_void_p
        objc.objc_msgSend.restype = ctypes.c_void_p
        objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        objc.objc_autoreleasePoolPush.restype = ctypes.c_void_p
        objc.objc_autoreleasePoolPop.argtypes = [ctypes.c_void_p]
        _OBJC = objc
    return _OBJC


def _cocoa_application() -> None:
    """``NSApplication.sharedApplication`` once: a Cocoa window needs an application object."""
    global _APP
    if _APP is not None:
        return
    import ctypes

    objc = _objc()
    ctypes.cdll.LoadLibrary("/System/Library/Frameworks/AppKit.framework/AppKit")
    _APP = objc.objc_msgSend(objc.objc_getClass(b"NSApplication"), objc.sel_registerName(b"sharedApplication"))


@contextlib.contextmanager
def pool() -> Iterator[None]:
    """An autorelease pool around AppKit's work (macOS; elsewhere nothing): what Cocoa
    autoreleases while a window is made or drawn is freed when it ends."""
    if platform() != "darwin":
        yield
        return
    objc = _objc()
    token = objc.objc_autoreleasePoolPush()
    try:
        yield
    finally:
        objc.objc_autoreleasePoolPop(token)


def _darwin_window(width: int, height: int) -> Any:
    from OCP.Cocoa import Cocoa_Window  # pyrefly: ignore[missing-import] - macOS's OCP alone

    _cocoa_application()
    return Cocoa_Window("cadgen", 0, 0, width, height)


# --- Linux ---------------------------------------------------------------------------------


def _has_xlib() -> bool:
    try:
        import OCP.Xw  # noqa: F401  # pyrefly: ignore[missing-import] - an OCP built with Xlib alone
    except ImportError:
        return False
    return True


def _linux_window(connection: Any, width: int, height: int) -> Any:
    if not _has_xlib():  # an OCCT built with EGL and no Xlib: no X window to make
        from OCP.Aspect import Aspect_NeutralWindow

        window = Aspect_NeutralWindow()
        window.SetSize(width, height)
        window.SetVirtual(True)
        return window
    from OCP.Xw import Xw_Window  # pyrefly: ignore[missing-import] - an OCP built with Xlib alone

    window = Xw_Window(connection, "cadgen", 0, 0, width, height)
    window.SetVirtual(True)  # never mapped: nothing appears on the display
    return window


# --- Windows -------------------------------------------------------------------------------


def _windows_window(width: int, height: int) -> Any:
    import ctypes
    from ctypes import wintypes

    from OCP.WNT import WNT_Window  # pyrefly: ignore[missing-import] - Windows's OCP alone

    user32 = ctypes.windll.user32
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.CreateWindowExW.argtypes = [wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.HWND,
                                       wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID]
    popup = 0x80000000  # WS_POPUP and not WS_VISIBLE: never shown
    handle = user32.CreateWindowExW(0, "STATIC", "cadgen", popup, 0, 0, width, height, None, None, None, None)
    if not handle:
        raise Unavailable(f"Windows made no window for OpenGL (error {ctypes.GetLastError()})")
    capsule = ctypes.pythonapi.PyCapsule_New
    capsule.restype, capsule.argtypes = ctypes.py_object, [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    window = WNT_Window(capsule(handle, None, None))
    window.SetVirtual(True)
    return window


# --- the driver and the canvas ---------------------------------------------------------------

_CONNECTION = threading.local()


def _connection() -> Any:
    """The thread's one connection to the display, made at its first canvas and kept: a canvas per
    connection would hold as many X clients as the process holds scenes, and an X server refuses
    clients past its limit (Xvfb's 256, shared by every process drawing on it). A connection
    refused is not kept, so the next canvas asks again."""
    from OCP.Aspect import Aspect_DisplayConnection

    made = getattr(_CONNECTION, "made", None)
    if made is None:
        made = _CONNECTION.made = Aspect_DisplayConnection()
    return made


def driver() -> Any:
    """An OpenGL driver: a core profile (PBR and the path tracer need one), drawing into frame
    buffers, never swapping a window's. Raises ``Unavailable``, by name. A refusal is asked again
    at the next canvas, never remembered: an X server that refused one connection (Xvfb busy,
    say) is no reason to draw nothing for the rest of the process."""
    try:
        if platform() == "linux" and _has_xlib() and not os.environ.get("DISPLAY"):
            raise Unavailable("no X display for OpenGL: OCP's Linux build draws through GLX on an X server. Run "
                              "under Xvfb (xvfb-run -a ..., or Xvfb :99 & export DISPLAY=:99), or set DISPLAY")
        from OCP.OpenGl import OpenGl_GraphicDriver

        if platform() == "darwin":
            _cocoa_application()
        made = OpenGl_GraphicDriver(_connection(), False)
        options = made.ChangeOptions()
        options.buffersNoSwap = True
        options.contextCompatible = False
        if not made.InitContext():
            raise Unavailable(f"OCCT could not make an OpenGL context on {platform()}"
                              + (" (does the X server have GLX? Xvfb +extension GLX)" if platform() == "linux" else ""))
    except Unavailable:
        raise
    except Exception as error:  # noqa: BLE001 - OCCT raises its own failures; each is this refusal
        raise Unavailable(f"OCCT could not make an OpenGL context on {platform()}: {type(error).__name__}: "
                          f"{error}") from None
    return made


_DRAWS: list[str | None] = []


def available() -> str | None:
    """None when a canvas can be made in this process and draws a picture that leaves it; else why
    not (asked once, remembered). A context that is made but draws nothing -- Windows' GDI Generic
    OpenGL 1.1, on a machine with no GPU driver -- is no canvas either."""
    try:
        canvas = Canvas(16, 16)
    except Unavailable as error:
        return str(error)
    try:
        if not _DRAWS:
            try:
                pixels(canvas.pixmap())
                _DRAWS.append(None)
            except RuntimeError as error:
                _DRAWS.append(f"OpenGL on {platform()} draws no picture here ({error}): a software 1.1 context, "
                              "no GPU driver")
        return _DRAWS[0]
    finally:
        canvas.close()


class Canvas:
    """A viewer, a view and an interactive context on a hidden window of ``width`` x ``height``.
    ``width`` and ``height`` are the size a picture is drawn at, and may be set before each one:
    the view draws into a frame buffer of that size, whatever the window's."""

    def __init__(self, width: int, height: int) -> None:
        started = time.perf_counter()
        from OCP.AIS import AIS_InteractiveContext
        from OCP.V3d import V3d_Viewer

        self.width, self.height = width, height
        self.driver = driver()
        with pool():
            if platform() == "darwin":
                self.window = _darwin_window(width, height)
            elif platform() == "windows":
                self.window = _windows_window(width, height)
            else:
                self.window = _linux_window(self.driver.GetDisplayConnection(), width, height)
            self.viewer = V3d_Viewer(self.driver)
            self.view = self.viewer.CreateView()
            self.view.SetWindow(self.window)
            self.context = AIS_InteractiveContext(self.viewer)
        self.seconds = time.perf_counter() - started

    def pixmap(self) -> Any:
        from OCP.Image import Image_AlienPixMap

        image = Image_AlienPixMap()
        with pool():
            if not self.view.ToPixMap(image, self.width, self.height):
                raise RuntimeError("OCCT drew nothing")
        return image

    def frame(self) -> np.ndarray:
        """The view drawn, as sRGB bytes (height, width, 3)."""
        return pixels(self.pixmap())

    def tile(self, left: int, top: int, width: int, height: int) -> np.ndarray:
        """The view's pixels in one rectangle of the frame (``left``, ``top`` from its top-left),
        drawn alone: a camera tile keeps the whole frame's projection, so the pixels are the
        frame's there (to a level at an edge's multisample) at the cost of the rectangle."""
        from OCP.Graphic3d import Graphic3d_BufferType, Graphic3d_CameraTile
        from OCP.collections import Vec2_int
        from OCP.Image import Image_AlienPixMap

        camera = self.view.Camera()
        tile = Graphic3d_CameraTile()
        tile.TotalSize = Vec2_int(self.width, self.height)
        tile.TileSize = Vec2_int(width, height)
        tile.Offset = Vec2_int(left, self.height - top - height)  # counted from the lower left
        camera.SetTile(tile)
        try:
            image = Image_AlienPixMap()
            with pool():
                if not self.view.ToPixMap(image, width, height, Graphic3d_BufferType.Graphic3d_BT_RGB, False):
                    raise RuntimeError("OCCT drew nothing")
        finally:
            camera.SetTile(Graphic3d_CameraTile())
        return pixels(image)

    def png(self, paint: Callable[[np.ndarray], None] | None = None) -> bytes:
        """The view drawn now as PNG bytes, encoded in memory; ``paint`` paints over the frame
        first (sRGB bytes, in place)."""
        frame = self.frame()
        if paint is not None:
            paint(frame)
        return encode(frame)

    def save(self, path: str, paint: Callable[[np.ndarray], None] | None = None) -> float:
        """Draw the view, let ``paint`` paint over the frame, and write it as a PNG; the seconds the
        frame, the painting and the encoding took."""
        started = time.perf_counter()
        data = self.png(paint)
        with open(path, "wb") as handle:
            handle.write(data)
        return time.perf_counter() - started

    def close(self) -> None:
        """Let go of what is shown, the view, its window and its context."""
        with pool():
            if getattr(self, "context", None) is not None:
                self.context.RemoveAll(False)
            if getattr(self, "view", None) is not None:
                self.view.Remove()
        self.context = self.view = self.viewer = self.window = self.driver = None


# --- a picture's bytes ---------------------------------------------------------------------------


def pixels(image: Any) -> np.ndarray:
    """An OCCT picture (``Image_PixMap``) as sRGB bytes (height, width, 3), top row first. OCP hands
    no pointer to a picture's buffer, so the picture is handed over as an uncompressed TGA in memory
    (a few milliseconds) and read with numpy: its 18-byte header, then its BGR(A) rows."""
    from OCP.TCollection import TCollection_AsciiString

    stream = io.BytesIO()
    if not image.Save(stream, TCollection_AsciiString("tga")):
        raise RuntimeError("OCCT could not hand its picture over")
    data = stream.getvalue()
    kind = data[2]
    width, height, depth, descriptor = struct.unpack_from("<HHBB", data, 12)
    if kind != 2 or depth not in (24, 32):
        raise RuntimeError(f"OCCT handed over a TGA of type {kind} at {depth} bits a pixel")
    found = np.frombuffer(data, np.uint8, width * height * (depth // 8), 18 + data[0])
    found = found.reshape(height, width, depth // 8)[:, :, [2, 1, 0]]
    return np.ascontiguousarray(found if descriptor & 0x20 else found[::-1])  # bit 5: the top row first


def encode(frame: np.ndarray) -> bytes:
    """sRGB bytes (height, width, 3), or with alpha (4), as a PNG: eight-bit RGB or RGBA, rows
    unfiltered, deflated by zlib (faster than OCCT's encoder on a frame of flat backdrop, and the
    smaller file)."""
    height, width, channels = frame.shape
    rows = np.empty((height, 1 + width * channels), np.uint8)
    rows[:, 0] = 0  # each row's filter: none
    rows[:, 1:] = np.ascontiguousarray(frame, np.uint8).reshape(height, width * channels)

    def chunk(kind: bytes, body: bytes) -> bytes:
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)

    colour = 6 if channels == 4 else 2  # RGBA, else RGB
    return b"".join([b"\x89PNG\r\n\x1a\n", chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, colour, 0, 0, 0)),
                     chunk(b"IDAT", zlib.compress(rows.tobytes(), 6)), chunk(b"IEND", b"")])
