"""A model's parameters: named numbers a script declares, which a person changes in the code alone.

A script declares a parameter at its module's top level, and uses the number it returns::

    from cad import model

    WALL = model.param("wall", 2.0, min=1, max=5)        # a float; WALL is 2.0
    HOLES = model.param("holes", 6, min=3, max=12)       # an integer; HOLES is 6

``param`` returns its default unchanged, a plain ``int`` or ``float``: nothing of a build -- the memo's
keys, what a body retains, a document's closure -- knows a parameter from any other number of the
script. In the program's own process it checks the declaration and nothing more. In the load of the
script that a build makes (``recording``, ``build._build``) each call is also recorded (``Declared``):
what it declares, the file and line of the call, and, where the default is a plain number in the code
(``2.0``, ``-3``), the bytes of the file that spell it (``span``) with a digest of the bytes the span
was found in. A default that is anything else (a name, an expression) is recorded with no span, and so
is one the engine cannot tell is that call's alone: a call whose name is no string in the code (a loop's, a
comprehension's), two declarations at one literal, a file whose bytes are not UTF-8.

A build writes what a model's script declares into its document (``record``: name, value, kind, min,
max, step, unit -- never a file, a line or a span) and answers the rest in its report (``rows``): where
each is declared and whether it can be written (``reason``: ``shared``, declared in another file than
the model's own; ``expression``, no plain number in the code). The engine holds those rows in memory
while the worker that recorded them lives (``cad_server.engine.models``), and serves them beside the
document's record (``served``).

Changing a value is changing the script (an edit and a run, or the page's Save): the values a Save asks for are
checked against the declarations (``changes``), the file's bytes against what the run recorded
(``standing``), each number is spelled (``spelled``) and put in place of the one there (``splice``), and
the script is built again. A page may first look at values without writing them (a preview, the page's
Parameters tab as a slider moves): the worker loads the script with those values in place of the
defaults its own script declares (``recording``'s ``values``: ``param`` returns the value asked, not the
default), builds the one model on screen and answers its geometry to that page alone; nothing is written,
and the document is not that build (``cad_server.engine.parameters.Previewing``). This module is the
standard library alone: the server, which imports no kernel, imports it, and so does a script run where
only the library is installed.
"""

from __future__ import annotations

import ast
import codecs
import contextlib
import dataclasses
import hashlib
import io
import json
import math
import os
import re
import sys
import tokenize
from dataclasses import dataclass
from typing import Any, Callable, Iterator

__all__ = ["CODES", "KEYS", "REASONS", "UNITS", "Declared", "ParameterRefused", "changes", "digest", "param",
           "previewed", "record", "recording", "rows", "served", "source_of", "spelled", "splice", "standing"]

#: The options a declaration takes beside its name and default.
KEYS = ("min", "max", "step", "unit")
#: The units a parameter may say it is in (display only); None for a bare number.
UNITS = ("mm", "deg")
#: Why a parameter a document lists cannot be written, a closed set: the document is a file, not a model;
#: no live worker recorded where it is declared; another file than the model's own declares it; its default
#: is no plain number the engine can find alone in the code (an expression, a name, a call whose name is no
#: string in the code, a file not in UTF-8).
REASONS = ("file", "no_worker", "shared", "expression")
#: Why a change of parameters is refused, a closed set (``ParameterRefused.code``).
CODES = ("no_worker", "unknown_parameter", "not_writable", "not_a_number", "out_of_range", "script_changed", "busy",
         "build_failed")
#: The decimals a written float keeps.
DECIMALS = 6

_NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
_BOM = b"\xef\xbb\xbf"


class ParameterRefused(ValueError):
    """A change of a model's parameters refused: its words, why by one word of ``CODES`` (``code``), what to
    do (``hint``) and, for ``not_writable``, the parameter's own reason (``reason``, of ``REASONS``)."""

    code: str | None = None
    hint: str | None = None
    reason: str | None = None

    def __init__(self, message: str, code: str | None = None, hint: str | None = None,
                 reason: str | None = None) -> None:
        super().__init__(message)
        self.code, self.hint, self.reason = code, hint, reason


@dataclass(frozen=True)
class Declared:
    """One ``param`` call a load recorded: what it declares, the file and line of the call, and where its
    default is spelled -- ``span``, the first byte of the literal in ``file`` and the one after its last,
    with ``digest``, of the bytes they were found in; both None for a default that is no plain number."""

    name: str
    value: int | float
    kind: str
    min: int | float | None
    max: int | float | None
    step: int | float | None
    unit: str | None
    file: str
    line: int
    span: tuple[int, int] | None = None
    digest: str | None = None


# --- declaring ------------------------------------------------------------------------------------


def _number(value: Any, what: str) -> int | float:
    """``value`` as a declaration's number: a plain ``int`` or ``float`` (never a ``bool``), finite."""
    if type(value) not in (int, float):
        raise TypeError(f"{what} is a number (an int or a float), not {type(value).__name__} {value!r}")
    if not math.isfinite(value):
        raise ValueError(f"{what} is a finite number, not {value!r}")
    return value


def param(name: str, default: int | float, *, min: int | float | None = None, max: int | float | None = None,
          step: int | float | None = None, unit: str | None = None, **unknown: Any) -> int | float:
    """Declare a parameter of this script's models: ``WALL = model.param("wall", 2.0, min=1, max=5)``.

    Returns ``default`` unchanged, the plain number the script goes on with. An ``int`` default declares an
    integer parameter, a ``float`` default a float one; ``min`` and ``max`` bound the values it may be
    given, ``step`` is how far a control moves it, ``unit`` (``"mm"`` or ``"deg"``) what it is shown in.
    ``name`` is a lower-case identifier, one declaration per name in a run. A parameter is declared at a
    module's top level: a body can be replayed without running, and a declaration inside one would be
    lost. A build records each declaration in the model's document, where the CAD Viewer lists them;
    the value changes only in the code: an edit and a run, or the CAD Viewer's Save, which rewrites the
    default where it is a plain number. (The one load that returns another number is a page's preview, in the
    engine's worker: the value a person is trying, which no document and no file keeps.)"""
    if unknown:
        raise TypeError(f"param() takes {', '.join(KEYS)} beside its name and default; not "
                        f"{', '.join(sorted(unknown))}")
    if not isinstance(name, str) or not _NAME.match(name):
        raise ValueError(f"a parameter's name is a lower-case identifier ([a-z][a-z0-9_]*), not {name!r}")
    said = f"parameter {name!r}"
    value = _number(default, f"{said}: its default")
    kind = "int" if type(value) is int else "float"
    bounds = {key: None if given is None else _number(given, f"{said}: {key}")
              for key, given in (("min", min), ("max", max), ("step", step))}
    if kind == "int":
        for key, given in bounds.items():
            if given is not None and given != int(given):
                raise ValueError(f"{said} is an integer (its default is {value!r}): {key} is a whole number, "
                                 f"not {given!r}")
            bounds[key] = None if given is None else int(given)
    low, high, stride = bounds["min"], bounds["max"], bounds["step"]
    if low is not None and high is not None and not low < high:
        raise ValueError(f"{said}: min is below max, not {low!r} and {high!r}")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ValueError(f"{said}: its default {value!r} is outside {_range(low, high)}")
    if stride is not None and not stride > 0:
        raise ValueError(f"{said}: step is above zero, not {stride!r}")
    if unit is not None and unit not in UNITS:
        raise ValueError(f"{said}: unit is one of {', '.join(UNITS)}, or none; not {unit!r}")
    frame = sys._getframe(1)
    if frame.f_code.co_name != "<module>":
        raise RuntimeError(f"{said} is declared inside {frame.f_code.co_name}(): declare it at the module's top "
                           "level (a body can be replayed without running, and its declaration would be lost)")
    held = _RECORDING[0]
    if held is not None:
        # A preview's load (``recording``'s ``values``): the value asked for in place of the default.
        return held.declare(frame, name, value, kind, low, high, stride, unit)
    return default


def _range(low: Any, high: Any) -> str:
    """A declared range in words: ``1 to 5``, ``at least 1``, ``at most 5``."""
    if low is not None and high is not None:
        return f"{low!r} to {high!r}"
    return f"at least {low!r}" if low is not None else f"at most {high!r}"


# --- recording, in a build's load of the script -----------------------------------------------------


class _Recording:
    """The declarations one load of a script makes, in the order made (``declared``): each file they are
    in read and parsed once (``_sources``); ``first_party`` says whether a file is the model's own code,
    whose declarations alone are recorded (a library's module loads once a process, never again). A
    preview's load is given ``values`` (``{name: number}``) and the ``script`` they are of: a declaration
    of that name in that file goes on with the value given, which it records, its span still the default's."""

    def __init__(self, first_party: Callable[[str], bool], values: dict[str, int | float] | None = None,
                 script: str | None = None) -> None:
        self.first_party = first_party
        self.values = values or {}
        self.script = script
        self.declared: list[Declared] = []
        self._sources: dict[str, tuple[bytes, str, dict[tuple, ast.Call], list[int]] | None] = {}

    def declare(self, frame: Any, name: str, value: int | float, kind: str, low: Any, high: Any, stride: Any,
                unit: str | None) -> int | float:
        """Record one declaration; the value the script goes on with: its default, or a preview's value."""
        file, line = frame.f_code.co_filename, int(frame.f_lineno or 0)
        if not self.first_party(file):
            return value
        from cad.engine.ids import canonical

        file = canonical(file)
        other = next((found for found in self.declared if found.name == name), None)
        if other is not None and (other.file, other.line) != (file, line):
            raise ValueError(f"parameter {name!r} is declared at {other.file}:{other.line} and {file}:{line}; "
                             "give one declaration another name")
        span, found = self._literal(frame, file, name, value)
        given = self.values.get(name) if file == self.script else None
        if given is not None:
            value = int(given) if kind == "int" else float(given)
        made = Declared(name, value, kind, low, high, stride, unit, file, line, span, found)
        if other is not None:  # the same line run again (its module loaded twice): the one declaration
            self.declared[self.declared.index(other)] = made
        else:
            self.declared.append(made)
        if span is not None:
            # Two declarations at one literal (one call run for each): neither is that literal's alone, so
            # neither keeps it -- writing one would write the other.
            sharing = [at for at, row in enumerate(self.declared) if row.file == file and row.span == span]
            if len(sharing) > 1:
                for at in sharing:
                    self.declared[at] = dataclasses.replace(self.declared[at], span=None, digest=None)
        return value

    def _source(self, file: str) -> tuple[bytes, str, dict[tuple, ast.Call], list[int]] | None:
        """``file`` as this load reads it, once: its bytes, their digest, its calls by where each is, and
        the byte each line begins at; None for a file that does not read or parse, or is not UTF-8 (``_utf8``:
        the parser's columns are bytes of the text as UTF-8, which are the file's own only then)."""
        if file not in self._sources:
            try:
                with open(file, "rb") as handle:
                    data = handle.read()
                if not _utf8(data):
                    raise ValueError("not UTF-8")
                tree = ast.parse(data, filename=file)
            except (OSError, SyntaxError, ValueError):
                self._sources[file] = None
            else:
                calls = {(node.lineno, node.end_lineno, node.col_offset, node.end_col_offset): node
                         for node in ast.walk(tree) if isinstance(node, ast.Call)}
                starts = [0]
                for text in data.splitlines(keepends=True):
                    starts.append(starts[-1] + len(text))
                self._sources[file] = (data, digest(data), calls, starts)
        return self._sources[file]

    def _literal(self, frame: Any, file: str, name: str, value: int | float) -> tuple[tuple[int, int] | None, str | None]:
        """Where the default of the ``param`` call ``frame`` stands at is spelled in ``file``, and the digest
        of the bytes it was found in: the call found by its code position (the frame's instruction, a
        line's one call of this name where the interpreter keeps no columns), its default a plain number
        whose bytes read back as ``value``. ``(None, None)`` for any other."""
        source = self._source(file)
        if source is None:
            return None, None
        data, found, calls, starts = source
        try:
            where = list(frame.f_code.co_positions())[frame.f_lasti // 2]
        except (AttributeError, IndexError):
            where = (None, None, None, None)
        call = calls.get(tuple(where)) if None not in where else None
        if call is None:
            # No columns (``-X no_debug_ranges``): the one call on the frame's line that declares this name.
            on_line = [node for node in calls.values() if node.lineno <= frame.f_lineno <= (node.end_lineno or 0)
                       and _names(node) == name]
            call = on_line[0] if len(on_line) == 1 else None
        if call is None or _names(call) != name:
            # A call whose name is no string in the code (a loop's, a comprehension's) runs for more than one
            # name: its literal is none of theirs alone.
            return None, None
        default = call.args[1] if len(call.args) > 1 else next(
            (keyword.value for keyword in call.keywords if keyword.arg == "default"), None)
        if default is None or any(isinstance(node, ast.Starred) for node in call.args[:2]) or not _plain(default):
            return None, None
        try:
            start = starts[default.lineno - 1] + default.col_offset
            end = starts[(default.end_lineno or 0) - 1] + (default.end_col_offset or 0)
        except IndexError:
            return None, None
        if data.startswith(_BOM):
            # The parser counts a first line's columns past the byte order mark.
            start, end = start + (len(_BOM) if default.lineno == 1 else 0), end + (len(_BOM) if default.end_lineno == 1 else 0)
        if not _same(_read(data[start:end]), value):
            return None, None
        return (start, end), found


def _utf8(data: bytes) -> bool:
    """Whether a file's bytes are UTF-8 text the parser reads as such: they decode, and the coding they
    declare (a cookie, a byte order mark), if any, is UTF-8."""
    try:
        coding, _lines = tokenize.detect_encoding(io.BytesIO(data).readline)
        data.decode("utf-8")
    except (SyntaxError, LookupError, UnicodeDecodeError):
        return False
    try:
        return codecs.lookup(coding).name in ("utf-8", "utf-8-sig")
    except LookupError:
        return False


def _names(call: ast.Call) -> str | None:
    """The name a call declares where its first argument spells one (a string in the code), else None."""
    first = call.args[0] if call.args else next((keyword.value for keyword in call.keywords
                                                 if keyword.arg == "name"), None)
    return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None


def _plain(node: ast.AST) -> bool:
    """Whether an expression is a plain number in the code: a numeric literal, or one with a leading minus."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) in (int, float)


def _read(text: bytes) -> int | float | None:
    """The number bytes of a script spell as a plain number (``_plain``), or None: nothing is evaluated."""
    try:
        node = ast.parse(text.decode("utf-8").strip(), mode="eval").body
    except (SyntaxError, ValueError):
        return None
    if not _plain(node):
        return None
    if isinstance(node, ast.UnaryOp):
        return -node.operand.value  # type: ignore[attr-defined]
    return node.value  # type: ignore[attr-defined]


def _same(found: int | float | None, value: int | float) -> bool:
    """Whether a number read from the code is ``value``, of its kind."""
    return found is not None and type(found) is type(value) and found == value


# The load being recorded, if any: a build's alone (``recording``).
_RECORDING: list[_Recording | None] = [None]


@contextlib.contextmanager
def recording(first_party: Callable[[str], bool] = lambda _file: True, *, values: dict[str, int | float] | None = None,
              script: str | None = None) -> Iterator[list[Declared]]:
    """Record the declarations made inside the block, a build's load of its script: the list they are
    appended to, in the order made. Each load starts from none, as it starts from no model; a ``param``
    call outside any block records nothing. A preview's load (``values``, of the canonical ``script``):
    each declaration of those names in that file returns the value given, and records it as its value."""
    held = _Recording(first_party, values, script)
    previous, _RECORDING[0] = _RECORDING[0], held
    try:
        yield held.declared
    finally:
        _RECORDING[0] = previous


# --- what a build says of a model's parameters --------------------------------------------------------


def rows(declared: list[Declared], script: str, files: Any = None) -> list[dict[str, Any]]:
    """The parameters of a model defined in ``script``, of those a load declared: each as the document
    records it, with where it is declared (``file``, ``line``) and, where it can be written, the bytes of
    its default and the digest they were found under (``span``, ``digest``); ``reason`` says why one
    cannot (``shared``: another file than ``script`` declares it; ``expression``: no plain number in the
    code). ``files``: the files a model of another script than the build's is made of, whose declarations
    alone are its own."""
    found = []
    for row in declared:
        if files is not None and row.file not in files:
            continue
        reason = "shared" if row.file != script else "expression" if row.span is None else None
        found.append({"name": row.name, "value": row.value, "kind": row.kind, "min": row.min, "max": row.max,
                      "step": row.step, "unit": row.unit, "file": row.file, "line": row.line,
                      "span": list(row.span) if reason is None and row.span is not None else None,
                      "digest": row.digest if reason is None else None, "reason": reason})
    return found


_RECORDED = ("name", "value", "kind", "min", "max", "step", "unit")


def record(listed: list[dict[str, Any]] | None) -> str | None:
    """A model's parameters as its document holds them, on its main label: ASCII JSON, a list of ``{name,
    value, kind, min, max, step, unit}`` (an option not declared is null), in the order declared; None for
    a model with none. No file, no line and no span: a document says what its parameters were, never
    where the code keeps them."""
    if not listed:
        return None
    return json.dumps([{key: row.get(key) for key in _RECORDED} for row in listed], ensure_ascii=True,
                      separators=(",", ":"))


def recorded(text: str | None) -> list[dict[str, Any]]:
    """``record`` read back: the list a document holds, ``[]`` for none or for text that is no such list."""
    if not text:
        return []
    try:
        found = json.loads(text)
    except ValueError:
        return []
    if not isinstance(found, list):
        return []
    return [{key: row.get(key) for key in _RECORDED} for row in found
            if isinstance(row, dict) and isinstance(row.get("name"), str)]


def source_of(file: str | None, script: str | None) -> str | None:
    """A declaring file as a page names it: relative to the script's folder where it is under it (with
    ``/``), else its name; None where it is not known."""
    if not file:
        return None
    if script:
        try:
            relative = os.path.relpath(file, os.path.dirname(script))
        except ValueError:  # another drive
            relative = os.pardir
        if relative != os.pardir and not relative.startswith(os.pardir + os.sep) and not os.path.isabs(relative):
            return relative.replace(os.sep, "/")
    return os.path.basename(file)


def served(listed: list[dict[str, Any]] | None, *, model: bool, live: dict[str, Any] | None) -> list[dict[str, Any]]:
    """A document's parameters as a page reads them: what the document records (``listed``), each with
    ``writable``, ``reason`` (None when writable, else one of ``REASONS``) and ``source`` (``source_of``).
    ``model``: the document is a model's, not a file; ``live``: what the worker that built it recorded,
    while it lives (``{"script", "rows"}``, ``rows``'s), else None. A parameter is writable only where
    that worker recorded the bytes of the value the document holds."""
    script = (live or {}).get("script")
    known = {row.get("name"): row for row in (live or {}).get("rows") or []}
    found = []
    for row in listed or []:
        held = known.get(row.get("name"))
        if not model:
            reason, file = "file", None
        elif held is None or not _same(held.get("value"), row.get("value")):
            reason, file = "no_worker", None
        else:
            reason, file = held.get("reason"), held.get("file")
            if reason is None and not held.get("span"):
                reason = "expression"
        found.append({**{key: row.get(key) for key in _RECORDED}, "writable": reason is None, "reason": reason,
                      "source": source_of(file, script)})
    return found


# --- changing values: what is asked, checked; the script's bytes, checked; the numbers, written ------------


def spelled(value: int | float, kind: str) -> str:
    """A number as the engine writes it into a script: an integer as its digits; a float rounded to
    ``DECIMALS`` decimals in the shortest text that reads back as it, always with a decimal point or an
    exponent, so the parameter stays a float. ``changes`` gives a value already rounded, so what is written
    reads back as the value its answer reports."""
    if kind == "int":
        return str(int(value))
    return repr(round(float(value), DECIMALS) + 0.0)  # ``+ 0.0``: a negative zero is written as zero


def _said(given: Any) -> str:
    """A value given, in a refusal's words: its ``repr``, shortened where it is long (a number of 400 digits)."""
    text = repr(given)
    return text if len(text) <= 40 else f"{text[:20]}...{text[-8:]} ({len(text)} characters)"


def _value(row: dict[str, Any], given: Any) -> int | float:
    """``given`` as a value of parameter ``row``: a finite number of its kind, in its range; else refused.
    An integer beyond what a float holds (``sys.float_info.max``) is ``not_a_number``, whatever the range: no
    page or document could hold it, and it is refused before anything converts it. A float parameter's value
    is the one written, rounded to ``DECIMALS`` decimals (what ``written[].to`` reports); a value that is not
    zero but rounds to zero is ``not_a_number``, never written as ``0.0``."""
    name = row["name"]
    if type(given) is int and abs(given) > sys.float_info.max:
        raise ParameterRefused(f"{name} takes a finite number, not {_said(given)}: it is beyond what a float holds",
                               "not_a_number", f"give {name} a number")
    if type(given) not in (int, float) or not math.isfinite(given):
        raise ParameterRefused(f"{name} takes a finite number, not {_said(given)}", "not_a_number",
                               f"give {name} a number")
    if row["kind"] == "int":
        if given != int(given):
            raise ParameterRefused(f"{name} is an integer parameter: it takes a whole number, not {_said(given)}",
                                   "not_a_number", f"give {name} a whole number")
        value: int | float = int(given)
    else:
        value = round(float(given), DECIMALS) + 0.0
        if value == 0 and given != 0:
            raise ParameterRefused(f"{name} is written with {DECIMALS} decimals: {given!r} would be written as 0.0",
                                   "not_a_number", f"give {name} 0, or a value of at least {10.0 ** -DECIMALS!r}")
    low, high = row.get("min"), row.get("max")
    if (low is not None and value < low) or (high is not None and value > high):
        raise ParameterRefused(f"{name} is {_range(low, high)}; {_said(given)} is outside it", "out_of_range",
                               f"give {name} a value in its range, or change the range in the code")
    return value


def changes(listed: list[dict[str, Any]], values: dict[str, Any]) -> list[tuple[dict[str, Any], int | float]]:
    """What a request to set ``values`` (``{name: number}``) changes of a model's parameters (``listed``:
    ``rows``'s, as its worker recorded them): each parameter whose value differs, with its new value, in
    the order declared. ``ParameterRefused`` -- nothing changes -- for a name the model has no parameter
    by (``unknown_parameter``), one that cannot be written (``not_writable``, with its ``reason``), a
    value that is no finite number of the parameter's kind (``not_a_number``) or outside its declared
    range (``out_of_range``). A value equal to the one the code holds changes nothing."""
    known = {row["name"]: row for row in listed}
    for name in values:
        if name not in known:
            has = ", ".join(known) if known else "none"
            raise ParameterRefused(f"the model has no parameter {name!r}; it has {has}", "unknown_parameter",
                                   "name one of the model's parameters")
    for name in values:
        row = known[name]
        if row.get("reason") is not None or not row.get("span"):
            reason = row.get("reason") or "expression"
            why = (f"it is declared in {os.path.basename(str(row.get('file') or ''))}, another file than the model's own"
                   if reason == "shared" else "its default is no plain number the engine can write alone in the code "
                   "(an expression, a call made for more than one name, or a file not in UTF-8)")
            raise ParameterRefused(f"{name} cannot be set: {why}", "not_writable",
                                   "edit it in the code, then run the script", reason)
    wanted = {name: _value(known[name], given) for name, given in values.items()}
    return [(row, wanted[row["name"]]) for row in listed
            if row["name"] in wanted and not _same(wanted[row["name"]], row["value"])]


def digest(data: bytes) -> str:
    """The digest a run records of a script's bytes, and a change checks them by."""
    return hashlib.sha256(data).hexdigest()


def standing(data: bytes, listed: list[dict[str, Any]], name: str) -> None:
    """Whether a script's bytes now (``data``) are the ones its last run recorded each of ``listed``'s
    positions in: their digest the recorded one, and the bytes at each span still spelling the recorded
    value. ``ParameterRefused`` (``script_changed``) otherwise: a position in bytes no run read is no
    position."""
    found = digest(data)
    for row in listed:
        start, end = row["span"]
        if row.get("digest") != found or not _same(_read(data[start:end]), row["value"]):
            raise ParameterRefused(f"{name} changed since its last run: the engine knows where "
                                   f"{row['name']} was, not where it is", "script_changed",
                                   "run the script first, then set the parameter")


def previewed(declared: list[Declared], values: dict[str, Any], script: str, found: str | None) -> None:
    """Whether a preview's load (``declared``) took every value asked (``values``) where the last run
    recorded it: each a declaration of the model's own ``script`` with a span, read in bytes of the digest
    the run recorded (``found``). ``ParameterRefused`` (``script_changed``) otherwise: the script on disk is
    not the one that ran, and a preview shows the run's code at other values, never code no run read."""
    named = {row.name: row for row in declared if row.file == script}
    for name in values:
        row = named.get(name)
        if row is None or row.span is None or (found is not None and row.digest != found):
            raise ParameterRefused(f"{os.path.basename(script)} changed since its last run: the engine previews the "
                                   "code that ran, not another", "script_changed",
                                   "run the script first, then change the parameter")


def splice(data: bytes, edits: list[tuple[int, int, str]]) -> bytes:
    """``data`` with each edit's text in place of its bytes (``(start, end, text)``), the last first so no
    edit moves another's position; every other byte as it was."""
    made = bytearray(data)
    for start, end, text in sorted(edits, reverse=True):
        made[start:end] = text.encode("ascii")
    return bytes(made)
