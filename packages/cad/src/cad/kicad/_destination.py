"""Where a KiCad board's or schematic's export goes (``cad export FILE DST [--as KIND]``, ``cad.export(file, dst,
as_=...)``): the destination named -- a file, a folder (a path that ends in a separator, or a folder that is there)
or a ``.zip`` -- says what is written, and ``--as`` names it only where the destination cannot: a board's folder or
``.zip`` (its Gerbers, drill files, ODB++ or PDF drawings) and a board's ``.csv`` (its placement or its BOM). No
name is made up: a one-file output is written at the file named, and a folder or a ``.zip`` holds the files KiCad
names.

``resolve`` checks a destination before KiCad runs, so a refused export writes nothing (``ArgumentRefused``, the
caller's mistake, naming what fits it); ``place`` then puts what KiCad wrote into a folder of its own where the
destination says (``Plan``): its one file at the file named, its files into the folder (made when missing), or
zipped into the ``.zip``. Each file is made beside its place first and renamed over it, as the engine writes one
(``cad.engine.atomic_replace``): a failed write leaves the file there as it was, and the files of a folder are all
made before the first is moved into place. An ODB++ into a ``.zip`` is KiCad's own compressed ODB++, into a folder
its uncompressed tree. A board's PDF is two files, a drawing of each side: kicad-cli draws one side a run (the back
mirrored), and its pages of one file are a layer each, so it goes into a folder or a ``.zip``.
"""

from __future__ import annotations

import functools
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused

__all__ = ["BOARD_FILES", "BOARD_FOLDERS", "Plan", "SCHEMATIC_FILES", "SCHEMATIC_FOLDERS", "place", "resolve"]

#: A board's outputs that are one file, by the suffix of the file named: its 3D, its outline, its IPC-2581, and its
#: placement or BOM, the two a ``.csv`` holds.
BOARD_FILES: dict[str, tuple[str, ...]] = {".step": ("step",), ".stp": ("step",), ".glb": ("glb",), ".dxf": ("dxf",),
                                          ".xml": ("ipc2581",), ".csv": ("pos", "bom")}
#: A board's outputs that are several files, written into a folder or zipped into a ``.zip`` (an ODB++ into a
#: ``.zip`` is KiCad's own zip of it).
BOARD_FOLDERS = ("gerbers", "drill", "odb", "pdf")
#: A schematic's, by suffix: every sheet's PDF, the netlist a board imports, its BOM; and its one output of several
#: files, an SVG a sheet.
SCHEMATIC_FILES: dict[str, tuple[str, ...]] = {".pdf": ("pdf",), ".net": ("netlist",), ".csv": ("bom",)}
SCHEMATIC_FOLDERS = ("svg",)
# Each kind in a sentence, and the suffix a file of it is named with.
_WORDS = {"gerbers": "Gerbers", "drill": "drill files", "pos": "placement", "bom": "BOM", "step": "STEP",
          "glb": "GLB", "odb": "ODB++", "ipc2581": "IPC-2581", "pdf": "PDF", "dxf": "outline DXF", "svg": "SVGs",
          "netlist": "netlist"}
_SUFFIXES = {"step": ".step", "glb": ".glb", "dxf": ".dxf", "ipc2581": ".xml", "pos": ".csv", "bom": ".csv",
             "pdf": ".pdf", "netlist": ".net"}
# Every entry of a zip written here is dated alike: a zip is a function of what it holds, never of the clock.
_ZIP_DATE = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class Plan:
    """What an export writes and where: KiCad's ``kind``, the destination ``dst`` and its ``form`` (``file``,
    ``folder`` or ``zip``), and what KiCad's own export is told beyond the kind (``options``: an ODB++ into a folder
    is its uncompressed tree)."""

    kind: str
    dst: Path
    form: str
    options: dict[str, Any] = field(default_factory=dict)


def _or(words: list[str]) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} or {words[-1]}"


def _folder(text: str) -> bool:
    """Whether a destination names a folder: a path that ends in a separator, or a folder that is there."""
    return text.endswith(("/", os.sep)) or os.path.isdir(os.path.expanduser(text))


def resolve(document_type: str, source: Any, dst: Any, as_: str | None = None, *, flag: str = "--as ") -> Plan:
    """What an export of the KiCad file ``source`` (``document_type``: ``kicad_pcb`` or ``kicad_sch``) to ``dst``
    writes, ``as_`` naming the kind where ``dst`` cannot (``flag``: how a refusal spells a kind named, the command's
    ``--as KIND`` or the library's ``as_=KIND``). ``ArgumentRefused`` for a kind no export of the file is, a
    destination that fits none, a folder, a ``.zip`` or a ``.csv`` that fits several and no kind named, a kind the
    destination does not agree with, and a destination that is the file itself: each said by name, before anything
    is written."""
    from cad.kicad._export import EXPORTS as BOARD
    from cad.kicad._schematic import EXPORTS as SCHEMATIC

    board = document_type == "kicad_pcb"
    noun, kinds = ("board", BOARD) if board else ("schematic", SCHEMATIC)
    files, folders = (BOARD_FILES, BOARD_FOLDERS) if board else (SCHEMATIC_FILES, SCHEMATIC_FOLDERS)
    text = os.fspath(dst)
    if not text:
        raise ArgumentRefused(f"a {noun}'s export names its destination: a file, a folder or a .zip")
    if as_ is not None and as_ not in kinds:
        raise ArgumentRefused(f"{flag}{as_}: a {noun}'s export is one of {', '.join(kinds)}")
    path = Path(os.path.abspath(os.path.expanduser(text)))
    if path.resolve() == Path(os.fspath(source)).expanduser().resolve():
        raise ArgumentRefused(f"{text} is the {noun} itself: an export never writes over its source")
    suffix = path.suffix.lower()
    if _folder(text) or suffix == ".zip":
        form = "folder" if _folder(text) else "zip"
        where = "a folder" if form == "folder" else "a .zip"
        if as_ is None:
            if len(folders) > 1:
                raise ArgumentRefused(f"{text} is {where}, which takes a {noun}'s "
                                      f"{_or([_WORDS[kind] for kind in folders])}: name which, "
                                      f"{_or([flag + kind for kind in folders])}")
            as_ = folders[0]
        elif as_ not in folders:  # the file it names, said as the destination was
            named = (os.path.join(text, f"{Path(os.fspath(source)).stem}{_SUFFIXES[as_]}") if form == "folder" else
                     f"{os.path.splitext(text)[0]}{_SUFFIXES[as_]}")
            raise ArgumentRefused(f"{text} is {where}, and a {noun}'s {_WORDS[as_]} is one file: name the file "
                                  f"({named})")
        return Plan(as_, path, form, {"compressed": False} if as_ == "odb" and form == "folder" else {})
    fit = files.get(suffix)
    if fit is None:
        if board and suffix == ".pdf":
            raise ArgumentRefused(f"{text}: a board's PDF is two files, a drawing of each side: name a folder or a "
                                  f".zip, with {flag}pdf")
        raise ArgumentRefused(f"{text}: a {noun}'s export is a {_or(list(files))} file, a folder or a .zip")
    if as_ is None:
        if len(fit) > 1:
            raise ArgumentRefused(f"{text} is a {suffix}, which takes a {noun}'s "
                                  f"{_or([_WORDS[kind] for kind in fit])}: name which, {_or([flag + kind for kind in fit])}")
        as_ = fit[0]
    elif as_ not in fit:
        if as_ in folders:
            raise ArgumentRefused(f"{flag}{as_} writes several files: name a folder (ending in /) or a .zip, not "
                                  f"{text}")
        raise ArgumentRefused(f"{text} is a {noun}'s {_or([_WORDS[kind] for kind in fit])}, and {flag}{as_} names its "
                              f"{_WORDS[as_]}: they must agree")
    return Plan(as_, path, "file")


def scratch() -> tempfile.TemporaryDirectory:
    """A folder of its own for KiCad to write into, removed with what is left in it once the files are placed."""
    return tempfile.TemporaryDirectory(prefix="cad-export-")


def place(plan: Plan, written: Any, folder: Path | str) -> list[Path]:
    """The files KiCad wrote into ``folder`` (``written``) put where ``plan`` says, and the files that are there now:
    the one file of a one-file output at the file named (its folder made when missing); each file into the folder
    named, by its path inside ``folder``; or the files zipped into the ``.zip`` named (KiCad's own zip of an ODB++
    put there as it is). Where a file cannot be made, ``RuntimeError`` naming the destination, every file there as it
    was."""
    folder = Path(folder).resolve()
    files = sorted(Path(path).resolve() for path in written)
    if not files:
        raise RuntimeError(f"KiCad wrote no {_WORDS[plan.kind]}")
    if plan.form == "file" or (plan.form == "zip" and plan.kind == "odb"):  # one file, KiCad's own
        if len(files) != 1:
            raise RuntimeError(f"KiCad wrote {len(files)} files of the {_WORDS[plan.kind]}, which is one")
    try:
        return _placed(plan, files, folder)
    except OSError as error:
        raise RuntimeError(f"cannot write the {_WORDS[plan.kind]} to {plan.dst}: {error.strerror or error}") from None


def _placed(plan: Plan, files: list[Path], folder: Path) -> list[Path]:
    from cad.engine.atomic_replace import put, replace_atomic, staging

    dst = plan.dst
    if plan.form == "folder":
        targets = [dst / path.relative_to(folder) for path in files]
        dst.mkdir(parents=True, exist_ok=True)
        # Every file is made in a folder of this export's beside them first, then each renamed into place.
        with staging(dst / "export") as staged:
            made = [staged.parent / path.relative_to(folder) for path in files]
            for path, copy in zip(files, made):
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, copy)
            for copy, target in zip(made, targets):
                target.parent.mkdir(parents=True, exist_ok=True)
                replace_atomic(copy, target)
        return targets
    dst.parent.mkdir(parents=True, exist_ok=True)
    if plan.form == "file" or plan.kind == "odb":
        put(dst, functools.partial(shutil.copyfile, files[0]), compare=False)
    else:
        put(dst, functools.partial(_zip, files, folder), compare=False)
    return [dst]


def _zip(files: list[Path], folder: Path, path: Path) -> None:
    """``files`` zipped into ``path``, each by its path inside ``folder``, every entry dated alike."""
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file in files:
            entry = zipfile.ZipInfo(file.relative_to(folder).as_posix(), date_time=_ZIP_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o644 << 16
            archive.writestr(entry, file.read_bytes())
