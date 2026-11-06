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

Only ``stat`` and ``realpath`` touch the file system; nothing is read or written. Pure standard library.
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
# A footprint's (model "<name>" ...) as the board's text writes it.
_MODEL = re.compile(r'\(model\s+"((?:[^"\\]|\\.)*)"')


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
    """Every model a board's text names (its footprints' ``(model "...")``), once each, as first written."""
    seen: dict[str, None] = {}
    for match in _MODEL.finditer(text):
        seen.setdefault(match.group(1).replace('\\"', '"').replace("\\\\", "\\"), None)
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
    for root in roots:
        try:
            if os.path.commonpath([path, root]) == root:
                return True
        except ValueError:  # another drive on Windows
            continue
    return False


def _candidates(name: str, folder: str, libraries: Sequence[str], variables: Mapping[str, str]) -> Iterable[str]:
    """Every place a name may be, in KiCad's order: its variables expanded (a library's against each
    library), else the board's folder and then each library for a relative name."""
    name = name.strip().replace("\\", "/")
    library_named = [match.group(1) or match.group(2) for match in _VARIABLE.finditer(name)]
    if any(_LIBRARY_VARIABLE.match(variable or "") for variable in library_named):
        for library in libraries:
            yield _VARIABLE.sub(lambda match: library if _LIBRARY_VARIABLE.match(match.group(1) or match.group(2) or "")
                                else _value(match, folder, variables), name)
        return
    expanded = _VARIABLE.sub(lambda match: _value(match, folder, variables), name)
    if "\0" in expanded:
        return
    if os.path.isabs(expanded) or re.match(r"^[A-Za-z]:/", expanded):
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
        stem = os.path.splitext(os.path.normpath(candidate))[0]
        tries = [stem + ending for ending in _STEP + tuple(ending.upper() for ending in _STEP)] if suffix in _VRML \
            else [os.path.normpath(candidate)]
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
