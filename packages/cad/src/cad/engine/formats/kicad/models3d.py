"""A board's 3D models: which file on this computer each model a footprint names is, or why none is.

A footprint names its model as KiCad writes it (``(model "${KICAD9_3DMODEL_DIR}/Resistor_SMD.3dshapes/R_0603.wrl"
...)``, :class:`~cad.engine.formats.kicad.board_index.Model3d`). :func:`resolve_models` reads those
names against a few folders, and nothing else:

- the board's own folder (KiCad's ``${KIPRJMOD}``, and where a relative name is looked for first);
- KiCad's 3D library where an installation of KiCad keeps it (``standard_libraries``: on macOS
  ``/Applications/KiCad*/KiCad.app/Contents/SharedSupport/3dmodels``; on Linux ``/usr/share/kicad/3dmodels``,
  ``/usr/local/share/kicad/3dmodels`` and the Flatpak's; on Windows ``<Program Files>/KiCad/<version>/share/kicad/3dmodels``),
  which every ``${KICADn_3DMODEL_DIR}`` (any ``n``; ``${KISYS3DMOD}``, KiCad 5's) and a relative name are read in;
- the folders ``CAD_KICAD_3DMODELS`` names (separated as ``PATH`` is), searched as KiCad's library is.

``${...}`` and ``$(...)`` are KiCad's two spellings of a variable; a variable the project's ``.kicad_pro``
defines (``text_variables``) is read too. The person's KiCad settings (their own path variables, their
3D search paths) are never read, nor the process's environment but ``CAD_KICAD_3DMODELS``.

The model must be a STEP: a ``.wrl`` or ``.wrz`` name is read as the ``.step`` or ``.stp`` beside it, as
KiCad's own libraries ship both. A resolved file's REAL path (every symlink followed) must lie inside one
of the folders above, end in ``.step`` or ``.stp`` and be at most ``MAX_BYTES``; a board names at most
``MAX_MODELS`` distinct models. Anything else is missing, with the reason:

========================  ==========================================================
``not-found``             no file of that name in any folder it is looked for in
``vrml-only``             the model is there as VRML alone (shown as a block for now)
``outside``               the file lies outside the board's folder and KiCad's library
``too-large``             over ``MAX_BYTES``
``not-step``              a format other than STEP or VRML (IGES, an unknown suffix)
``embedded``              a model embedded in the board (``kicad-embed://``), not read yet
``too-many``              past the ``MAX_MODELS``-th distinct model
========================  ==========================================================

A place is first read as text: it must lie inside one of the folders above before any file system call is
made for it, and a name that is a network share (``\\\\server\\share``, ``//server/share``), a device
(``\\\\?\\``, ``\\\\.\\``) or drive-relative (``C:model.step``) is ``outside`` on every platform, looked for
nowhere: on Windows, opening a share connects to its server and offers it the person's credentials.

Only ``stat``, ``realpath`` and ``isfile`` touch the file system, inside those folders; nothing is read or
written. Pure standard library.
"""

from __future__ import annotations

import glob
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from cad.engine.formats.kicad import sexpr

__all__ = ["MAX_BYTES", "MAX_MODELS", "REASONS", "Resolved", "library_roots", "model_names", "resolve_models",
           "standard_libraries"]

#: The largest STEP a board's part is drawn from: KiCad's largest library model is a few megabytes.
MAX_BYTES = 64 * 1024 * 1024
#: The most distinct models one board's table names.
MAX_MODELS = 512
#: Why a model is missing, each as its table says it.
REASONS = ("not-found", "vrml-only", "outside", "too-large", "not-step", "embedded", "too-many")

_STEP = (".step", ".stp")
_VRML = (".wrl", ".wrz")
# ${NAME} or $(NAME), KiCad's two spellings.
_VARIABLE = re.compile(r"\$\{([^}]*)\}|\$\(([^)]*)\)")
_LIBRARY_VARIABLE = re.compile(r"^(KICAD\d*_3DMODEL_DIR|KISYS3DMOD)$")
# A drive's letter: C:/... is a drive's root; C:... without the slash, the drive's current folder.
_DRIVE = re.compile(r"^[A-Za-z]:")
_DRIVE_RELATIVE = re.compile(r"^[A-Za-z]:(?!/)")
# A footprint's (model <name> ...) in the board's text: the name a quoted string or, as KiCad 5 wrote it, a
# bare atom, each in sexpr's own token grammar.
_MODEL = re.compile(r'\(\s*model\s+(?:"((?:[^"\\]|\\.)*)"|([^\s()"]+))', re.DOTALL)


@dataclass(frozen=True)
class Resolved:
    """A model name's answer: ``path`` the STEP it is (its real path) and ``stamp`` its ``mtime_ns-size``,
    else ``reason`` (one of :data:`REASONS`). ``file`` is the name's last part, as a person reads it."""

    name: str
    file: str
    path: str | None = None
    stamp: str | None = None
    reason: str | None = None


def standard_libraries(platform: str | None = None, environ: Mapping[str, str] | None = None) -> list[str]:
    """Where an installation of KiCad keeps its 3D library on this platform: the folders that exist."""
    platform = platform or sys.platform
    environ = os.environ if environ is None else environ
    if platform == "darwin":
        patterns = ["/Applications/KiCad*/KiCad.app/Contents/SharedSupport/3dmodels",
                    "/Applications/KiCad*.app/Contents/SharedSupport/3dmodels"]
    elif platform.startswith("win"):
        programs = [environ.get(name) for name in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)")]
        patterns = [os.path.join(folder, "KiCad", "*", "share", "kicad", "3dmodels") for folder in programs if folder]
    else:
        patterns = ["/usr/share/kicad/3dmodels", "/usr/local/share/kicad/3dmodels",
                    "/var/lib/flatpak/app/org.kicad.KiCad/current/active/files/share/kicad/3dmodels",
                    "/app/share/kicad/3dmodels"]
    found: list[str] = []
    for pattern in patterns:
        # The newest installation first: KiCad 10's library before KiCad 9's.
        for folder in sorted(glob.glob(pattern), reverse=True):
            if os.path.isdir(folder) and folder not in found:
                found.append(folder)
    return found


def library_roots(environ: Mapping[str, str] | None = None, platform: str | None = None) -> list[str]:
    """The 3D libraries a board's models are read in: ``CAD_KICAD_3DMODELS``'s folders, then KiCad's own."""
    environ = os.environ if environ is None else environ
    named = [folder for folder in (environ.get("CAD_KICAD_3DMODELS") or "").split(os.pathsep) if folder.strip()]
    roots: list[str] = []
    for folder in [*named, *standard_libraries(platform, environ)]:
        real = os.path.realpath(os.path.expanduser(folder))
        if os.path.isdir(real) and real not in roots:
            roots.append(real)
    return roots


def model_names(text: str) -> list[str]:
    """Every model a board's text names (its footprints' ``(model ...)``), once each, as first written.

    Each name is the one :func:`~cad.engine.formats.kicad.board_index.read_index` reads (a quoted name
    unescaped as :mod:`.sexpr` unescapes it, KiCad 5's bare one as written), so the table it keys matches
    the plot payload's ``models``. A scan, not a parse: the board's text is not parsed on a request."""
    seen: dict[str, None] = {}
    for match in _MODEL.finditer(text):
        quoted, bare = match.groups()
        if bare is not None and sexpr.is_number(bare):
            continue  # the parser reads a number, which names no model
        name = sexpr.unescape(quoted) if quoted is not None else bare
        if name.strip():
            seen.setdefault(name, None)
    return list(seen)


def _project_variables(board: Path) -> dict[str, str]:
    """The project's own text variables (its ``.kicad_pro``'s ``text_variables``)."""
    project = board.with_suffix(".kicad_pro")
    try:
        found = json.loads(project.read_text(encoding="utf-8")).get("text_variables") or {}
    except (OSError, ValueError, AttributeError):
        return {}
    return {str(key): str(value) for key, value in found.items()} if isinstance(found, dict) else {}


def _inside(path: str, roots: Sequence[str]) -> bool:
    """Whether ``path`` lies in one of ``roots``, read as text: their ``commonpath`` (case folded where the
    platform folds it) is the root. A path on another drive, share or device, or a relative one, is in none."""
    path = os.path.normcase(path)
    for root in roots:
        root = os.path.normcase(root)
        try:
            if os.path.commonpath([path, root]) == root:
                return True
        except ValueError:  # another drive, a share, a device or a relative path
            continue
    return False


def _refused(name: str) -> bool:
    r"""Whether a name is one no file system call is made for, on any platform: a share (``\\server\share``,
    ``//server/share``), a device (``\\?\``, ``\\.\``) or a drive-relative name (``C:model.step``).
    Windows opens a share by connecting to its server and offering it the person's credentials."""
    slashed = name.replace("\\", "/")
    return "\0" in name or slashed.startswith("//") or _DRIVE_RELATIVE.match(slashed) is not None


def _local(candidate: str, roots: Sequence[str]) -> str | None:
    """``candidate`` normalised when, read as text, it lies inside one of ``roots``; else None. This runs
    before any file system call; the real path is checked against ``roots`` again once it is known."""
    if "\0" in candidate:
        return None
    path = os.path.normpath(candidate)
    return path if os.path.isabs(path) and _inside(path, roots) else None


def _candidates(name: str, folder: str, libraries: Sequence[str],
                variables: Mapping[str, str]) -> Iterable[str | None]:
    """Every place a name may be, in KiCad's order: its variables expanded (a library's against each
    library), else the board's folder and then each library for a relative name. ``None`` stands for a
    name that is a share, a device or drive-relative (:func:`_refused`): it is looked for nowhere."""
    name = name.strip().replace("\\", "/")
    library_named = [match.group(1) or match.group(2) for match in _VARIABLE.finditer(name)]
    if any(_LIBRARY_VARIABLE.match(variable or "") for variable in library_named):
        for library in libraries:
            yield _VARIABLE.sub(lambda match: library if _LIBRARY_VARIABLE.match(match.group(1) or match.group(2) or "")
                                else _value(match, folder, variables), name)
        return
    expanded = _VARIABLE.sub(lambda match: _value(match, folder, variables), name)
    if _refused(expanded):
        yield None
        return
    if expanded.replace("\\", "/").startswith("/") or _DRIVE.match(expanded):
        yield expanded
        return
    yield os.path.join(folder, expanded)
    for library in libraries:
        yield os.path.join(library, expanded)


def _value(match: re.Match, folder: str, variables: Mapping[str, str]) -> str:
    variable = match.group(1) or match.group(2) or ""
    if variable == "KIPRJMOD":
        return folder
    # A variable nobody defines stays as written, so the name it makes is found nowhere.
    return variables.get(variable, match.group(0))


def _resolve(name: str, folder: str, libraries: Sequence[str], roots: Sequence[str],
             variables: Mapping[str, str]) -> Resolved:
    file = name.replace("\\", "/").rstrip("/").rsplit("/", 1)[-1] or name
    if name.strip().lower().startswith("kicad-embed://"):
        return Resolved(name, file, reason="embedded")
    suffix = os.path.splitext(name.strip())[1].lower()
    if suffix not in _STEP + _VRML:
        return Resolved(name, file, reason="not-step")
    vrml = outside = large = False
    for candidate in _candidates(name, folder, libraries, variables):
        # Inside a root as text first: nothing outside the roots is ever stat-ed, opened or resolved.
        place = None if candidate is None else _local(candidate, roots)
        if place is None:
            outside = True
            continue
        stem = os.path.splitext(place)[0]
        tries = [stem + ending for ending in _STEP + tuple(ending.upper() for ending in _STEP)] if suffix in _VRML \
            else [place]
        for attempt in tries:
            try:
                real = os.path.realpath(attempt)
                info = os.stat(real)
            except (OSError, ValueError):
                continue
            if not os.path.isfile(real) or os.path.splitext(real)[1].lower() not in _STEP:
                continue
            if not _inside(real, roots):
                outside = True
                continue
            if info.st_size > MAX_BYTES:
                large = True
                continue
            return Resolved(name, file, path=real, stamp=f"{info.st_mtime_ns}-{info.st_size}")
        if suffix in _VRML and any(os.path.isfile(stem + ending) for ending in _VRML):
            vrml = True
    reason = "too-large" if large else "outside" if outside else "vrml-only" if vrml else "not-found"
    return Resolved(name, file, reason=reason)


def resolve_models(board: Path | str, names: Iterable[str], *, environ: Mapping[str, str] | None = None,
                   platform: str | None = None, libraries: Sequence[str] | None = None) -> dict[str, Resolved]:
    """Each model name the board at ``board`` writes (``names``, :func:`model_names`), answered: the STEP
    it is, or why it has none (see the module). ``libraries`` stands in for :func:`library_roots`."""
    board = Path(board)
    folder = os.path.realpath(str(board.parent))
    libraries = list(library_roots(environ, platform) if libraries is None else
                     [os.path.realpath(library) for library in libraries])
    roots = [folder, *libraries]
    variables = _project_variables(board)
    answers: dict[str, Resolved] = {}
    for name in names:
        if name in answers:
            continue
        if len(answers) >= MAX_MODELS:
            answers[name] = Resolved(name, name.replace("\\", "/").rsplit("/", 1)[-1], reason="too-many")
            continue
        answers[name] = _resolve(name, folder, libraries, roots, variables)
    return answers
