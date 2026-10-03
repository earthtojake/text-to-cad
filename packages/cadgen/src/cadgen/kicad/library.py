"""KiCad's symbol and footprint libraries, read by ``Library:Name``.

A part names its symbol (``Device:R``) and its footprint
(``Resistor_SMD:R_0603_1608Metric``) the way KiCad does: the library, a colon,
the entry. The library is found in the project's own folders first, then in the
libraries the KiCad install ships:

- a symbol library is ``<Library>.kicad_sym`` (one file) or
  ``<Library>.kicad_symdir/`` (KiCad 10's folder form, one file per symbol);
- a footprint library is ``<Library>.pretty/``, one ``<Name>.kicad_mod`` each.

Every library file a build reads is one of its inputs (cadgen's file trace sees
the open), so a library that changes makes the boards that used it stale. That
is why a parse is cached by the file's BYTES and never by its path: the bytes
are read on every lookup, the parse of bytes already seen is reused.

What comes back is KiCad's own data: a :class:`Symbol` keeps the pins with
their numbers, names and electrical types, a :class:`Footprint` keeps its pads.
Each also keeps the S-expression the writers embed in a document, exactly as
the library holds it (a derived symbol flattened onto its parent, as KiCad
does when it places one).
"""

from __future__ import annotations

import copy
import difflib
import hashlib
import math
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from cadgen.kicad import sexpr
from cadgen.kicad.sexpr import Sym

__all__ = [
    "Footprint",
    "FootprintPad",
    "LibraryError",
    "Libraries",
    "Symbol",
    "SymbolPin",
    "find_footprints",
    "find_symbols",
    "split_lib_id",
]


class LibraryError(LookupError):
    """A ``Library:Name`` that names nothing, with what is there instead."""


def split_lib_id(lib_id: str, *, what: str) -> tuple[str, str]:
    text = str(lib_id or "").strip()
    library, colon, name = text.partition(":")
    if not colon or not library or not name:
        raise LibraryError(
            f"{what} {lib_id!r} must be written Library:Name, the way KiCad names it "
            f"(for example {'Device:R' if what == 'symbol' else 'Resistor_SMD:R_0603_1608Metric'})"
        )
    return library, name


# --- parse cache, keyed by bytes --------------------------------------------

_PARSED: dict[str, list] = {}
_PARSED_ORDER: list[str] = []
_PARSED_LIMIT = 64
_parse_lock = threading.Lock()


def _remember(key: str, tree: list) -> list:
    with _parse_lock:
        _PARSED[key] = tree
        _PARSED_ORDER.append(key)
        while len(_PARSED_ORDER) > _PARSED_LIMIT:
            _PARSED.pop(_PARSED_ORDER.pop(0), None)
    return tree


def _recall(key: str) -> list | None:
    with _parse_lock:
        return _PARSED.get(key)


def _parsed(path: Path) -> list:
    """The tree in ``path``. The file is READ every time; only the parse is reused."""
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    return _recall(digest) or _remember(digest, sexpr.parse(data.decode("utf-8")))


def _block_end(text: str, start: int) -> int:
    """The index just past the list that opens at ``start``."""
    depth = 0
    index = start
    length = len(text)
    while index < length:
        char = text[index]
        if char == '"':
            index += 1
            while index < length and text[index] != '"':
                index += 2 if text[index] == "\\" else 1
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise LibraryError("a symbol library ends inside a symbol")


def _library_symbols(path: Path, names: set[str]) -> list:
    """A library tree holding only the top-level symbols ``names`` (and what they extend).

    A symbol library is one file of every symbol it has (``Device`` is 2.4 MB);
    parsing all of it to read one resistor cost most of a build. The file is
    still read whole, so the build's trace sees it; only the needed symbols'
    text is parsed.
    """
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    text = data.decode("utf-8")
    header_end = text.find("(symbol ")
    found: dict[str, list] = {}
    pending = set(names)
    while pending:
        name = pending.pop()
        if name in found:
            continue
        key = f"{digest}:{name}"
        node = _recall(key)
        if node is None:
            # A sub-symbol is named "<Name>_<unit>_<style>", never a bare top-level name,
            # so the first `(symbol "<Name>"` is the symbol, however the file is laid out.
            match = re.search(r'\(symbol\s+"' + re.escape(name) + r'"(?=[\s)])', text)
            if match is None:
                found[name] = None  # type: ignore[assignment]
                continue
            start = text.index("(", match.start())
            node = _remember(key, sexpr.parse(text[start:_block_end(text, start)]))
        found[name] = node
        parent = sexpr.value(node, "extends")
        if parent is not None and str(parent) not in found:
            pending.add(str(parent))
    head = sexpr.parse(text[:header_end].rstrip() + ")") if header_end > 0 else [Sym("kicad_symbol_lib")]
    return head + [node for node in found.values() if node is not None]


# --- symbols -----------------------------------------------------------------


@dataclass(frozen=True)
class SymbolPin:
    """One pin of a symbol, in the symbol's own coordinates (y up, as KiCad's library)."""

    number: str
    name: str
    electrical_type: str
    unit: int
    body_style: int
    x: float
    y: float
    angle: float
    length: float
    hidden: bool

    @property
    def tip(self) -> tuple[float, float]:
        """Where a wire attaches: the pin's ``at`` point, in symbol coordinates."""
        return self.x, self.y


@dataclass
class Symbol:
    lib_id: str
    name: str
    properties: dict[str, str]
    pins: tuple[SymbolPin, ...]
    unit_count: int
    power: str | None
    tree: list
    source: Path
    # KiCad's "Exclude from bill of materials", inverted: the schematic owns it,
    # and a footprint follows it (``exclude_from_bom``).
    in_bom: bool = True

    @property
    def reference_prefix(self) -> str:
        prefix = self.properties.get("Reference", "U").strip() or "U"
        return prefix.rstrip("?")

    @property
    def default_footprint(self) -> str | None:
        value = self.properties.get("Footprint", "").strip()
        return value or None

    def pins_named(self, key: str) -> list[SymbolPin]:
        """Pins whose number is ``key``, else pins whose name is ``key``."""
        text = str(key)
        by_number = [pin for pin in self.pins if pin.number == text]
        if by_number:
            return by_number
        return [pin for pin in self.pins if pin.name == text]

    def pin_numbers(self) -> list[str]:
        return list(dict.fromkeys(pin.number for pin in self.pins))


def _sub_symbol_unit(name: str, base: str) -> tuple[int, int] | None:
    """``("R_1_1", "R")`` -> ``(1, 1)``: the unit and body style a sub-symbol draws."""
    if not name.startswith(base + "_"):
        return None
    parts = name[len(base) + 1 :].split("_")
    if len(parts) != 2:
        return None
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None


def _text_of(node: list | None) -> str:
    if node is None or len(node) < 2:
        return ""
    value = node[1]
    return str(value) if not isinstance(value, list) else ""


def _is_hidden(node: list) -> bool:
    hide = sexpr.find(node, "hide")
    if hide is not None:
        return len(hide) < 2 or hide[1] == "yes"
    # An older library writes a bare `hide` atom.
    return any(item == "hide" for item in node[1:] if isinstance(item, Sym))


def _symbol_pins(tree: list, base: str) -> tuple[SymbolPin, ...]:
    pins: list[SymbolPin] = []
    for sub in sexpr.find_all(tree, "symbol"):
        unit = _sub_symbol_unit(str(sub[1]), base)
        if unit is None:
            continue
        for pin in sexpr.find_all(sub, "pin"):
            at = sexpr.find(pin, "at") or [Sym("at"), 0, 0, 0]
            pins.append(
                SymbolPin(
                    number=_text_of(sexpr.find(pin, "number")),
                    name=_text_of(sexpr.find(pin, "name")),
                    electrical_type=str(pin[1]),
                    unit=unit[0],
                    body_style=unit[1],
                    x=float(at[1]),
                    y=float(at[2]),
                    angle=float(at[3]) if len(at) > 3 else 0.0,
                    length=float(sexpr.value(pin, "length", 0.0)),
                    hidden=_is_hidden(pin),
                )
            )
    return tuple(pins)


def _flatten(library: list, name: str, *, lib_id: str, source: Path) -> list:
    """The symbol ``name`` as a schematic embeds it: parents folded in, renamed ``lib_id``."""
    entries = {str(node[1]): node for node in sexpr.find_all(library, "symbol")}
    chain: list[list] = []
    seen: set[str] = set()
    current = name
    while True:
        node = entries.get(current)
        if node is None:
            if not chain:
                raise LibraryError(f"no symbol {current!r} in {source}")
            raise LibraryError(f"{name!r} in {source} extends {current!r}, which the library does not define")
        if current in seen:
            raise LibraryError(f"{name!r} in {source} extends itself through {current!r}")
        seen.add(current)
        chain.append(node)
        parent = sexpr.value(node, "extends")
        if parent is None:
            break
        current = str(parent)
    root = copy.deepcopy(chain[-1])
    root_name = str(root[1])
    # Properties and flags: the most derived symbol wins, field by field.
    for derived in reversed(chain[:-1]):
        for child in derived[2:]:
            if not isinstance(child, list) or child[0] in {"extends", "symbol"}:
                continue
            if child[0] == "property":
                key = child[1]
                existing = [i for i, item in enumerate(root) if isinstance(item, list) and item[0] == "property" and item[1] == key]
                if existing:
                    root[existing[0]] = copy.deepcopy(child)
                else:
                    insert_at = max(
                        (i for i, item in enumerate(root) if isinstance(item, list) and item[0] == "property"),
                        default=1,
                    ) + 1
                    root.insert(insert_at, copy.deepcopy(child))
            else:
                existing = [i for i, item in enumerate(root) if isinstance(item, list) and item[0] == child[0]]
                if existing:
                    root[existing[0]] = copy.deepcopy(child)
    # Sub-symbols are named after the symbol that draws them.
    for item in root[2:]:
        if isinstance(item, list) and item[0] == "symbol":
            unit = _sub_symbol_unit(str(item[1]), root_name)
            if unit is not None:
                item[1] = f"{name}_{unit[0]}_{unit[1]}"
    root[1] = lib_id
    return root


@dataclass(frozen=True)
class FootprintPad:
    """One pad, in footprint coordinates (y down, as KiCad's board)."""

    number: str
    kind: str
    shape: str
    x: float
    y: float
    angle: float
    width: float
    height: float
    layers: tuple[str, ...]
    drill: float | None


@dataclass
class Footprint:
    lib_id: str
    name: str
    pads: tuple[FootprintPad, ...]
    attributes: tuple[str, ...]
    models: tuple[str, ...]
    courtyard: tuple[float, float, float, float] | None
    tree: list
    source: Path

    @property
    def pad_numbers(self) -> list[str]:
        return list(dict.fromkeys(pad.number for pad in self.pads if pad.number))

    def pads_numbered(self, number: str) -> list[FootprintPad]:
        return [pad for pad in self.pads if pad.number == str(number)]


def _footprint_pads(tree: list) -> tuple[FootprintPad, ...]:
    pads: list[FootprintPad] = []
    for pad in sexpr.find_all(tree, "pad"):
        at = sexpr.find(pad, "at") or [Sym("at"), 0, 0]
        size = sexpr.find(pad, "size") or [Sym("size"), 0, 0]
        drill_node = sexpr.find(pad, "drill")
        drill = None
        if drill_node is not None:
            numbers = [item for item in drill_node[1:] if isinstance(item, (int, float))]
            drill = float(numbers[0]) if numbers else None
        layers = sexpr.find(pad, "layers")
        pads.append(
            FootprintPad(
                number=str(pad[1]),
                kind=str(pad[2]),
                shape=str(pad[3]),
                x=float(at[1]),
                y=float(at[2]),
                angle=float(at[3]) if len(at) > 3 else 0.0,
                width=float(size[1]),
                height=float(size[2]) if len(size) > 2 else float(size[1]),
                layers=tuple(str(layer) for layer in (layers[1:] if layers else ())),
                drill=drill,
            )
        )
    return tuple(pads)


def _graphic_points(node: list) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for key in ("start", "end", "mid", "center"):
        child = sexpr.find(node, key)
        if child is not None and len(child) >= 3:
            points.append((float(child[1]), float(child[2])))
    pts = sexpr.find(node, "pts")
    if pts is not None:
        for xy in sexpr.find_all(pts, "xy"):
            points.append((float(xy[1]), float(xy[2])))
    if sexpr.head(node) == "fp_circle":
        center = sexpr.find(node, "center")
        end = sexpr.find(node, "end")
        if center is not None and end is not None:
            radius = math.hypot(float(end[1]) - float(center[1]), float(end[2]) - float(center[2]))
            cx, cy = float(center[1]), float(center[2])
            points.extend([(cx - radius, cy - radius), (cx + radius, cy + radius)])
    return points


def _courtyard(tree: list) -> tuple[float, float, float, float] | None:
    points: list[tuple[float, float]] = []
    for node in tree[1:]:
        if not isinstance(node, list) or not str(node[0]).startswith("fp_"):
            continue
        layer = sexpr.value(node, "layer")
        if layer not in {"F.CrtYd", "B.CrtYd"}:
            continue
        points.extend(_graphic_points(node))
    if not points:
        return None
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


# --- the search path -----------------------------------------------------------


@dataclass
class Libraries:
    """The folders a build looks parts up in: the project's first, then KiCad's."""

    project: Sequence[Path] = ()
    symbol_dirs: Sequence[Path] = ()
    footprint_dirs: Sequence[Path] = ()
    model_dir: Path | None = None
    _symbols: dict[str, Symbol] = field(default_factory=dict, repr=False)
    _footprints: dict[str, Footprint] = field(default_factory=dict, repr=False)
    # Why KiCad's own libraries are not on the path, when they are not.
    _kicad_missing: str | None = field(default=None, repr=False)

    @classmethod
    def for_project(cls, project: Iterable[Path] = (), *, install=None) -> "Libraries":
        """The project's library folders, then the KiCad install's (``find_kicad()`` by default).

        With no KiCad installed, the project's own folders still resolve; a lookup
        that needed KiCad's libraries fails then, saying how to install KiCad.
        """
        missing = None
        if install is None:
            from cadgen.kicad.install import KicadMissingError, find_kicad

            try:
                install = find_kicad()
            except KicadMissingError as error:
                missing = str(error)
        folders = [Path(path).expanduser().resolve() for path in project]
        kicad_symbols = (install.symbol_dir,) if install is not None and install.symbol_dir is not None else ()
        kicad_footprints = (install.footprint_dir,) if install is not None and install.footprint_dir is not None else ()
        libraries = cls(
            project=tuple(folders),
            symbol_dirs=tuple(folders) + kicad_symbols,
            footprint_dirs=tuple(folders) + kicad_footprints,
            model_dir=install.model_dir if install is not None else None,
        )
        libraries._kicad_missing = missing
        return libraries

    # -- symbols --

    def _symbol_files(self, library: str) -> list[Path]:
        """``<library>.kicad_sym`` files and ``.kicad_symdir`` folders, in search order."""
        found: list[Path] = []
        for folder in self.symbol_dirs:
            folder = Path(folder)
            if folder.is_file() and folder.name == f"{library}.kicad_sym":
                found.append(folder)
                continue
            if (folder / f"{library}.kicad_sym").is_file():
                found.append(folder / f"{library}.kicad_sym")
            if (folder / f"{library}.kicad_symdir").is_dir():
                found.append(folder / f"{library}.kicad_symdir")
        return found

    def symbol(self, lib_id: str) -> Symbol:
        library, name = split_lib_id(lib_id, what="symbol")
        cached = self._symbols.get(lib_id)
        if cached is not None:
            # Read again so this build's trace sees the input; nothing is re-parsed.
            cached.source.read_bytes()
            return cached
        sources = self._symbol_files(library)
        if not sources:
            raise LibraryError(
                f"no symbol library {library!r} (looked in {self._where(self.symbol_dirs)}){self._near_libraries(library, 'symbol')}"
            )
        source = sources[0]
        if source.is_dir():
            entry = source / f"{name}.kicad_sym"
            if not entry.is_file():
                raise LibraryError(f"symbol library {library!r} has no {name!r}{self._near_names(name, [p.stem for p in source.glob('*.kicad_sym')])}")
            tree = _parsed(entry)
            library_tree = tree
            # A derived symbol's parent lives in its own file in the same folder.
            parent = None
            for node in sexpr.find_all(tree, "symbol"):
                parent = sexpr.value(node, "extends")
            if parent is not None and (source / f"{parent}.kicad_sym").is_file():
                library_tree = list(tree) + list(sexpr.find_all(_parsed(source / f"{parent}.kicad_sym"), "symbol"))
        else:
            library_tree = _library_symbols(source, {name})
        names = [str(node[1]) for node in sexpr.find_all(library_tree, "symbol")]
        if name not in names:
            every = [str(node[1]) for node in sexpr.find_all(_parsed(source), "symbol")] if source.is_file() else names
            raise LibraryError(f"symbol library {library!r} has no {name!r}{self._near_names(name, every)}")
        flat = _flatten(library_tree, name, lib_id=lib_id, source=source)
        properties = {str(node[1]): str(node[2]) for node in sexpr.find_all(flat, "property") if len(node) > 2}
        pins = _symbol_pins(flat, name)
        units = {pin.unit for pin in pins} | {
            unit[0]
            for unit in (_sub_symbol_unit(str(node[1]), name) for node in sexpr.find_all(flat, "symbol"))
            if unit is not None
        }
        power_node = sexpr.find(flat, "power")
        power = None
        if power_node is not None:
            power = str(power_node[1]) if len(power_node) > 1 else "global"
        symbol = Symbol(
            lib_id=lib_id,
            name=name,
            properties=properties,
            pins=pins,
            unit_count=max([unit for unit in units if unit > 0], default=1),
            power=power,
            tree=flat,
            source=source if source.is_file() else source / f"{name}.kicad_sym",
            in_bom=str(sexpr.value(flat, "in_bom") or "yes") != "no",
        )
        self._symbols[lib_id] = symbol
        return symbol

    # -- footprints --

    def footprint(self, lib_id: str) -> Footprint:
        library, name = split_lib_id(lib_id, what="footprint")
        cached = self._footprints.get(lib_id)
        if cached is not None:
            cached.source.read_bytes()
            return cached
        folders = [Path(folder) / f"{library}.pretty" for folder in self.footprint_dirs]
        folders = [folder for folder in folders if folder.is_dir()]
        if not folders:
            raise LibraryError(
                f"no footprint library {library!r} (looked in {self._where(self.footprint_dirs)}){self._near_libraries(library, 'footprint')}"
            )
        entry = folders[0] / f"{name}.kicad_mod"
        if not entry.is_file():
            raise LibraryError(
                f"footprint library {library!r} has no {name!r}"
                f"{self._near_names(name, [p.stem for p in folders[0].glob('*.kicad_mod')])}"
            )
        tree = _parsed(entry)
        attr = sexpr.find(tree, "attr")
        footprint = Footprint(
            lib_id=lib_id,
            name=name,
            pads=_footprint_pads(tree),
            attributes=tuple(str(item) for item in (attr[1:] if attr else ()) if isinstance(item, Sym)),
            models=tuple(str(node[1]) for node in sexpr.find_all(tree, "model")),
            courtyard=_courtyard(tree),
            tree=tree,
            source=entry,
        )
        self._footprints[lib_id] = footprint
        return footprint

    def model_path(self, reference: str) -> Path | None:
        """A footprint's ``(model ...)`` path with KiCad's variables expanded, if it exists."""
        text = str(reference)
        if self.model_dir is not None:
            for major in range(9, 13):
                text = text.replace(f"${{KICAD{major}_3DMODEL_DIR}}", str(self.model_dir))
        path = Path(text).expanduser()
        return path if path.is_file() else None

    # -- messages --

    def _where(self, folders: Sequence[Path]) -> str:
        where = ", ".join(str(folder) for folder in folders) or "no folders"
        if self._kicad_missing:
            where += f"; KiCad's own libraries are not available ({self._kicad_missing})"
        return where

    def _near_libraries(self, library: str, kind: str) -> str:
        names: list[str] = []
        folders = self.symbol_dirs if kind == "symbol" else self.footprint_dirs
        suffix = ".kicad_sym" if kind == "symbol" else ".pretty"
        for folder in folders:
            folder = Path(folder)
            if folder.is_dir():
                names.extend(path.name[: -len(suffix)] for path in folder.iterdir() if path.name.endswith(suffix))
        return self._near_names(library, names)

    @staticmethod
    def _near_names(name: str, candidates: Sequence[str]) -> str:
        close = difflib.get_close_matches(name, list(candidates), n=5, cutoff=0.5)
        if not close:
            lowered = name.lower()
            close = [candidate for candidate in candidates if lowered in candidate.lower()][:5]
        return f"; did you mean {', '.join(close)}?" if close else ""


# --- search ----------------------------------------------------------------------

_SYMBOL_ENTRY = re.compile(r'\(symbol\s+"([^"]+)"')
_PROPERTY = re.compile(r'\(property\s+"(Description|ki_keywords)"\s+"((?:[^"\\]|\\.)*)"')


def _words(text: str) -> list[str]:
    return [word for word in re.split(r"[\s,]+", str(text).lower()) if word]


def _symbol_index(path: Path) -> list[tuple[str, str]]:
    """``(name, description + keywords)`` for each top-level symbol in a ``.kicad_sym``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: list[tuple[str, str]] = []
    matches = list(_SYMBOL_ENTRY.finditer(text))
    for index, match in enumerate(matches):
        name = match.group(1)
        if re.search(r"_\d+_\d+$", name):  # a unit drawing, not a symbol
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        about = " ".join(value for key, value in _PROPERTY.findall(text[match.end():end]))
        entries.append((name, about))
    return entries


def find_symbols(text: str, *, limit: int = 20, libraries: "Libraries | None" = None) -> list[tuple[str, str]]:
    """Symbols whose library, name, description or keywords hold every word of ``text``.

    ``[("Regulator_Linear:AMS1117-3.3", "1A Low Dropout regulator ..."), ...]``,
    names that contain the words first. Searches the project's libraries and KiCad's.
    """
    words = _words(text)
    if not words:
        raise LibraryError("find_symbols needs some words to look for, e.g. 'ldo 3.3' or 'usb c receptacle'")
    libraries = libraries or Libraries.for_project()
    found: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for folder in libraries.symbol_dirs:
        folder = Path(folder)
        files = [folder] if folder.is_file() else sorted(folder.glob("*.kicad_sym"))
        for path in files:
            library = path.stem
            for name, about in _symbol_index(path):
                lib_id = f"{library}:{name}"
                if lib_id in seen:
                    continue
                haystack = f"{lib_id} {about}".lower()
                if all(word in haystack for word in words):
                    seen.add(lib_id)
                    in_name = sum(word in lib_id.lower() for word in words)
                    found.append((-in_name, lib_id, about.strip()))
    found.sort()
    return [(lib_id, about) for _rank, lib_id, about in found[:limit]]


def find_footprints(text: str, *, limit: int = 20, libraries: "Libraries | None" = None) -> list[str]:
    """Footprints whose ``Library:Name`` holds every word of ``text`` (``"sot-223"``, ``"0603 resistor"``).

    KiCad names footprints by their package and dimensions
    (``Package_SO:SOIC-8_3.9x4.9mm_P1.27mm``), so the words are matched against
    that name; a library name like ``Resistor_SMD`` counts. Shortest names first.
    """
    words = _words(text)
    if not words:
        raise LibraryError("find_footprints needs some words to look for, e.g. 'soic-8' or '0603 led'")
    libraries = libraries or Libraries.for_project()
    found: set[str] = set()
    for folder in libraries.footprint_dirs:
        for pretty in sorted(Path(folder).glob("*.pretty")):
            library = pretty.name[: -len(".pretty")]
            for entry in pretty.glob("*.kicad_mod"):
                lib_id = f"{library}:{entry.stem}"
                lowered = lib_id.lower()
                if all(word in lowered for word in words):
                    found.add(lib_id)
    return sorted(found, key=lambda lib_id: (len(lib_id), lib_id))[:limit]
