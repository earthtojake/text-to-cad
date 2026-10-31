"""Document ids: one formula for every document, and the one canonical spelling of a path.

An id is a lower-case canonical UUID string, made by one formula (``derived_id``)::

    uuid5(NAMESPACE, canonical(scope) + "::" + name)

``scope`` is a path and ``name`` a name in it: a model's script and its function's name
(``model_id``), an opened file's path and no name (``file_id``: inside the engine only -- a file's
public name stays its path), a shape handed over (``model(shape, name=...)``) the calling script, or
the working folder where there is none, and the name it is given. Any process that knows the scope
and the name knows the id without asking the engine. An explicit ``name=`` uses the script's
folder as its scope instead: a name within that namespace, independent of the declaring file. Whether a text is an id is ``is_id``; what an id names is the
engine's to say, never the uuid's version.

``canonical`` is the one spelling of a path the engine and the viewer key by: ``realpath``,
then, on macOS, each name as the file system spells it (``getattrlist``, which opens nothing), so
a symlink, a ``..`` and a case variant of one file are one key. On Windows ``realpath`` resolves
the final path, except through a link whose target does not exist yet: that comes back as the
target the link names, its folders unresolved (a short ``RUNNER~1`` name, a ``..``), so it is
asked again until the answer stands -- a canonical path is its own canonical spelling. A part of
the path that does not exist keeps the spelling it was given below the deepest part that does.
Ids hash the canonical path exactly, with no case folding.

Nothing here reads, builds or persists a document, and nothing imports the kernel.
"""
from __future__ import annotations

import os
import re
import sys
import uuid
from typing import Any

__all__ = ["NAMESPACE", "canonical", "check_name", "derived_id", "file_id", "is_id", "model_id"]

# cadgen's namespace for derived ids: written once, never changed.
NAMESPACE = uuid.UUID("ad198b15-841c-4d1f-81be-6aa78d2737c0")

WINDOWS = sys.platform == "win32"

_ID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z")


_GETATTRLIST: Any = None


def _getattrlist() -> Any:
    """macOS's ``getattrlist(2)``, bound once; False where it cannot be."""
    global _GETATTRLIST
    if _GETATTRLIST is None:
        try:
            import ctypes

            class AttrList(ctypes.Structure):
                _fields_ = [("bitmapcount", ctypes.c_ushort), ("reserved", ctypes.c_uint16),
                            ("commonattr", ctypes.c_uint32), ("volattr", ctypes.c_uint32),
                            ("dirattr", ctypes.c_uint32), ("fileattr", ctypes.c_uint32),
                            ("forkattr", ctypes.c_uint32)]

            call = ctypes.CDLL("/usr/lib/libSystem.B.dylib", use_errno=True).getattrlist
            call.argtypes = [ctypes.c_char_p, ctypes.POINTER(AttrList), ctypes.c_void_p, ctypes.c_size_t,
                             ctypes.c_ulong]
            call.restype = ctypes.c_int
            _GETATTRLIST = (call, AttrList, ctypes)
        except (OSError, AttributeError):
            _GETATTRLIST = False
    return _GETATTRLIST


def _spelled(path: str) -> str | None:
    """The name of ``path``'s last part as the file system spells it (macOS: ``getattrlist``'s
    ``ATTR_CMN_NAME``, which opens nothing, so a model body's file reads never hear it); None for
    a path that does not exist, or where it cannot be asked."""
    bound = _getattrlist()
    if not bound:
        return None
    call, AttrList, ctypes = bound
    wanted = AttrList(5, 0, 0x00000001, 0, 0, 0, 0)  # ATTR_BIT_MAP_COUNT, ATTR_CMN_NAME
    answer = ctypes.create_string_buffer(12 + 1024)
    if call(os.fsencode(path), ctypes.byref(wanted), answer, len(answer), 1) != 0:  # FSOPT_NOFOLLOW
        return None
    raw = answer.raw
    offset = int.from_bytes(raw[4:8], sys.byteorder, signed=True)
    length = int.from_bytes(raw[8:12], sys.byteorder)
    return os.fsdecode(raw[4 + offset:4 + offset + length].split(b"\0", 1)[0])


def canonical(path: str | os.PathLike) -> str:
    """The one spelling of ``path`` every document key is made from (the module docstring)."""
    real = os.path.realpath(os.fspath(path))
    if WINDOWS:
        for _ in range(8):  # a link to a missing target: the target as the link names it (the docstring)
            again = os.path.realpath(real)
            if again == real:
                break
            real = again
        return real
    if sys.platform != "darwin":
        return real
    parts = real.split("/")[1:]
    spelled = ""
    for at, part in enumerate(parts):
        found = _spelled(f"{spelled}/{part}") if part else None
        if found is None:
            return "/".join([spelled, *parts[at:]])
        # The case alone is the file system's to say; any other difference (a hard link) is not.
        spelled = f"{spelled}/{found if found.casefold() == part.casefold() else part}"
    return spelled or "/"


def derived_id(scope: str | os.PathLike, name: str = "") -> str:
    """The one formula: uuid5 of ``scope``'s canonical path and ``name`` (the module docstring)."""
    return str(uuid.uuid5(NAMESPACE, canonical(scope) + "::" + name))


def file_id(path: str | os.PathLike) -> str:
    """An opened file's document id: its canonical path, with no name."""
    return derived_id(path)


def model_id(script: str | os.PathLike, function: str, name: str | None = None) -> str:
    """A model's id: script/function by default, folder/explicit name when given."""
    return derived_id(os.path.dirname(canonical(script)), check_name(name)) if name is not None else derived_id(script, function)


def check_name(name: object, what: str = "name") -> str:
    """A document's name as a declaration gives it: readable -- a
    non-empty string with no surrounding space and no control character -- and with no ``::``, the
    formula's separator, so that no scope and name spell another's; else refused by name."""
    if not isinstance(name, str) or not name or name != name.strip() or any(ord(c) < 32 for c in name):
        raise ValueError(f"{what} is a readable name (no surrounding space, no control character), not {name!r}")
    if "::" in name:
        raise ValueError(f"{what} {name!r} holds '::', which separates a scope from a name in an id: drop it")
    return name


def is_id(text: object) -> bool:
    """Whether ``text`` is a document id: a lower-case canonical UUID string."""
    return isinstance(text, str) and _ID.fullmatch(text) is not None
