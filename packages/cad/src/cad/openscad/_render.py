"""One render of an OpenSCAD program to a binary STL, headless, and what is read of the program for its key.

``render(source, out)`` runs ``openscad -o <private>/render.stl --export-format binstl -d <private>/render.d
SOURCE`` (``--backend=manifold`` where the program takes it) in a private folder with the headless environment
(``_program``), then moves the STL to ``out`` atomically: a failure leaves no file this run wrote, and an
earlier ``out`` stays byte for byte (law 17). It fails in OpenSCAD's own words -- its stderr, Qt's noise
dropped -- and refuses a 2D program in one line: OpenSCAD renders a 2D object to a DXF or an SVG, which the
``scad`` type does not take yet. The dependency file OpenSCAD writes (Make's format, spaces escaped) names
every file it read: the ``include``s, ``use``s and ``import``s beside the program, which the server keeps a
rendered mesh by (``key``: the program's bytes, each of theirs, OpenSCAD's version and this code's), so an
edit to a library file renders the program again as an edit to the program does.

Nothing of the program is interpreted here: no variable is set (``-D``), no parameter file given. A verb's
option is about the picture or the path, never the model (the library's law 22): a variant of a program is
a program.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from cad._internal.atomic_replace import replace_atomic, temp_suffix

from . import _program

__all__ = ["CODE_VERSION", "RenderError", "Rendered", "TwoDimensional", "dependencies", "key", "render"]

#: The render's arguments as a number: a change to them is a new key for every kept mesh.
CODE_VERSION = 1
_TIMEOUT_SECONDS = 900
_NOT_3D = "not a 3D object"
# A dependency line's end, as Make writes a continued one.
_CONTINUED = re.compile(r"\s*\\\s*$")


class RenderError(RuntimeError):
    """OpenSCAD could not render the program; the message carries what it said."""


class TwoDimensional(RenderError):
    """The program's top-level object is 2D: OpenSCAD renders it to a DXF or an SVG, not a mesh."""


@dataclass(frozen=True)
class Rendered:
    """One render: the program (resolved), the binary STL written, every other file OpenSCAD read (resolved,
    sorted), the OpenSCAD that rendered it, and what it said (its ``echo`` lines among them)."""

    source: Path
    mesh: Path
    includes: tuple[Path, ...]
    version: str
    said: str


def _split(line: str) -> list[str]:
    """A dependency line's paths: split on unescaped whitespace, a ``\\ `` an escaped space."""
    found: list[str] = []
    current = ""
    chars = iter(line)
    for char in chars:
        if char == "\\":
            following = next(chars, "")
            current += following if following in (" ", "\\") else char + following
        elif char.isspace():
            if current:
                found.append(current)
                current = ""
        else:
            current += char
    if current:
        found.append(current)
    return found


def dependencies(text: str, *, source: Path, folder: Path) -> tuple[Path, ...]:
    """The files a dependency file (``-d``) names beside the program: each path resolved against ``folder``
    (OpenSCAD's working folder for the run), the program itself and the target left out, sorted, each once."""
    tokens: list[str] = []
    for line in text.splitlines():
        tokens += _split(_CONTINUED.sub("", line))
    program = Path(source).resolve()
    found: set[Path] = set()
    for at, token in enumerate(tokens):
        if at == 0 or token.endswith(":"):  # the target (``out.stl:``), the first token or one ending in a colon
            continue
        path = Path(token)
        if not path.is_absolute():
            path = Path(folder) / path
        try:
            resolved = path.resolve()
        except OSError:
            continue
        if resolved != program and resolved.is_file():
            found.add(resolved)
    return tuple(sorted(found))


def key(source: str | os.PathLike, includes: Iterable[str | os.PathLike], version: str) -> str:
    """The key of what is rendered of ``source`` with ``includes`` (the files OpenSCAD read beside it) by
    OpenSCAD ``version``: their bytes, each by its path, with this code's version. A changed program or
    library, or another OpenSCAD, is a new key."""
    digest = hashlib.sha256()
    digest.update(f"openscad-render/{CODE_VERSION}/{version}\0".encode())
    for path in (Path(os.fspath(source)), *sorted(Path(os.fspath(item)) for item in includes)):
        digest.update(os.fsencode(str(path)) + b"\0")
        try:
            digest.update(path.read_bytes())
        except OSError:
            digest.update(b"\0none")
        digest.update(b"\0")
    return digest.hexdigest()


def render(source: str | os.PathLike, out: str | os.PathLike, *, timeout: float = _TIMEOUT_SECONDS) -> Rendered:
    """Render the program at ``source`` to a binary STL at ``out`` (see the module). ``FileNotFoundError``
    for a program that is not there, ``OpenscadMissing`` (``_program``) for no OpenSCAD, ``TwoDimensional`` for
    a 2D program and ``RenderError`` in OpenSCAD's words for anything it refused."""
    program = Path(os.fspath(source)).expanduser()
    if not program.is_file():
        raise FileNotFoundError(f"no such file: {program}")
    program = program.resolve()
    target = Path(os.fspath(out)).expanduser()
    executable, found_version = _program.ready()
    with _program.private_run("cad-openscad-render-") as (folder, env):
        rendered, deps = folder / "render.stl", folder / "render.d"
        argv = [str(executable), "-o", str(rendered), "--export-format", "binstl", "-d", str(deps)]
        if _program.has_backend(executable):
            argv.append("--backend=manifold")
        argv.append(str(program))
        try:
            done = subprocess.run(argv, cwd=str(program.parent), env=env, stdin=subprocess.DEVNULL,
                                  capture_output=True, text=True, encoding="utf-8", errors="replace",
                                  timeout=timeout, check=False)
        except subprocess.TimeoutExpired:
            raise RenderError(f"OpenSCAD did not finish rendering {program.name} in {timeout:g} s") from None
        except OSError as error:
            raise RenderError(f"cannot run {executable}: {error.strerror or error}") from None
        said = _program.quiet(f"{done.stderr}\n{done.stdout}")
        if done.returncode != 0 or not rendered.is_file():
            if _NOT_3D in said:
                raise TwoDimensional(f"{program.name} is a 2D program: OpenSCAD renders its object to a DXF or an SVG, "
                                     "not a mesh, and cad's scad type takes a 3D object alone; give it a "
                                     "linear_extrude to render it as a mesh")
            lines = said.splitlines()
            words = [line for line in lines if line.startswith(("ERROR", "WARNING", "Can't", "Current"))
                     or "error" in line.lower()] or lines[-3:]
            raise RenderError(f"OpenSCAD could not render {program.name} (exit {done.returncode}): "
                              + "; ".join(line.strip() for line in words))
        try:
            text = deps.read_text(encoding="utf-8", errors="replace")
        except OSError:
            text = ""
        includes = dependencies(text, source=program, folder=program.parent)
        target.parent.mkdir(parents=True, exist_ok=True)
        staged = target.with_name(target.name + temp_suffix())
        try:
            shutil.copyfile(rendered, staged)
            replace_atomic(staged, target)
        finally:
            try:
                staged.unlink(missing_ok=True)
            except OSError:
                pass
    return Rendered(program, target, includes, found_version, said)
