"""AP242 semantic PMI read back from a STEP file without OCCT, and checked against a document's.

Every STEP the engine writes of a document with PMI -- a build's declared one, ``cadgen
export``'s and ``api.export``'s, the viewer's -- is checked in the file it wrote (``check``,
through ``pmi.checked``): this module reads the file with a Part 21 tokenizer of its own, sharing
no code with the engine's writer or OCCT's STEP translator, and walks AP242's PMI entities as ISO
10303-242 and the CAx-IF Recommended Practices for PMI define them:

- dimensions: ``DIMENSIONAL_SIZE`` / ``DIMENSIONAL_LOCATION``, their nominal from the
  ``DIMENSIONAL_CHARACTERISTIC_REPRESENTATION``'s ``SHAPE_DIMENSION_REPRESENTATION``, its
  limits (its items named ``'lower limit'`` and ``'upper limit'``), its descriptive notes (a basic
  dimension's ``'theoretical'``), and their ``PLUS_MINUS_TOLERANCE``'s ``TOLERANCE_VALUE``
  (lower, upper);
- datums: ``DATUM`` (its identification), the ``DATUM_FEATURE`` a ``SHAPE_ASPECT_RELATIONSHIP``
  ties to it;
- geometric tolerances: any ``*_TOLERANCE`` entity (simple or complex), its magnitude, its
  ``DATUM_SYSTEM``'s compartments in order, its ``TOLERANCE_ZONE``'s form;
- each annotation's geometry: the ``GEOMETRIC_ITEM_SPECIFIC_USAGE`` of its shape aspect, the
  ``ADVANCED_FACE`` it identifies (its name), and that face's surface: a ``PLANE`` (origin,
  normal) or a ``CYLINDRICAL_SURFACE`` (radius), another by its type; a tolerance on several
  faces is on a ``COMPOSITE_SHAPE_ASPECT``, each face's through the aspect a
  ``SHAPE_ASPECT_RELATIONSHIP`` relates to it;
- a part's general tolerances: the CAx-IF PMI practice's ``PROPERTY_DEFINITION`` 'default
  tolerances' of its ``PRODUCT_DEFINITION_SHAPE``, its representation's ``DESCRIPTIVE_REPRESENTATION_ITEM``
  'tolerance class' (``ISO 2768-mK``);
- every measure's unit, from its unit entity (``SI_UNIT(.MILLI.,.METRE.)`` is mm);
- the product each record is of: its shape aspect's ``of_shape`` (a ``PRODUCT_DEFINITION_SHAPE``,
  through its ``PRODUCT_DEFINITION`` and formation to the ``PRODUCT``'s name), its faces' (the
  product whose ``SHAPE_DEFINITION_REPRESENTATION`` their usage's representation is) and each
  datum's its frame names: one product, or none.

It also says what is malformed for a strict reader: a measure written untyped where AP242's
``measure_value`` select needs its type, a reference to no record, and an entity it does not read.

``compare`` matches a document's PMI entries (the structure's ``pmi``) one to one with what the
file says, each part's with its own product's records alone, without guessing identities: within a
part, a face name its product's geometry holds twice or a datum letter its records write twice
verifies nothing of that part, and two products of one name verify neither; any problem fails the
check, which refuses the file of a document the code made (``pmi.checked``). Given the model's faces
(``pmi.step_surfaces``), each face the file ties an annotation to is held to its geometry too: a
plane's normal and offset, a cylinder's axis and radius, so a face of the right name on the wrong
surface verifies nothing (a face of another kind is checked by its name). It is a bounded check of
the semantics this engine writes, not an AP242 validator or a test of any importer.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cadgen.engine import refs

# --- the file as records ---------------------------------------------------------------------


@dataclass(frozen=True)
class Ref:
    id: int


@dataclass(frozen=True)
class Enum:
    name: str


@dataclass(frozen=True)
class Typed:
    type: str
    value: Any


UNSET = None
DERIVED = "*"

_REF = re.compile(r"#(\d+)")
_ENUM = re.compile(r"\.([A-Z_][A-Z0-9_]*)\.")
_POINT_NUMBER = re.compile(r"[-+]?\.?\d[\d.]*(?:[eE][-+]?\d+)?")
_NUMBER = re.compile(r"[-+]?\d+(\.\d*)?([eE][-+]?\d+)?")
_KEYWORD = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_SCHEMA = re.compile(r"FILE_SCHEMA\s*\(\s*\(\s*'([^']*)'")


def _tokens(text: str):
    at, end = 0, len(text)
    while at < end:
        char = text[at]
        if char.isspace():
            at += 1
        elif char == "'":
            close = at + 1
            while True:
                close = text.index("'", close)
                if close + 1 < end and text[close + 1] == "'":
                    close += 2
                    continue
                break
            yield ("str", text[at + 1:close].replace("''", "'"))
            at = close + 1
        elif char == "#":
            match = _REF.match(text, at)
            yield ("ref", int(match.group(1)))
            at = match.end()
        elif char == ".":
            match = _ENUM.match(text, at)
            if match:
                yield ("enum", match.group(1))
            else:
                match = _POINT_NUMBER.match(text, at)
                yield ("num", match.group(0))
            at = match.end()
        elif char in "-+0123456789":
            match = _NUMBER.match(text, at)
            yield ("num", match.group(0))
            at = match.end()
        elif char in "(),=;$*":
            yield (char, char)
            at += 1
        elif char == '"':
            close = text.index('"', at + 1)
            yield ("binary", text[at + 1:close])
            at = close + 1
        else:
            match = _KEYWORD.match(text, at)
            if not match:
                raise ValueError(f"unexpected {text[at:at + 20]!r}")
            yield ("kw", match.group(0).upper())
            at = match.end()


def _number(text: str) -> Any:
    return float(text) if any(char in text for char in ".eE") else int(text)


def _value(kind: str, text: Any) -> Any:
    if kind == "ref":
        return Ref(text)
    if kind == "enum":
        return Enum(text)
    if kind == "num":
        return _number(text)
    if kind == "$":
        return UNSET
    if kind == "*":
        return DERIVED
    return text  # a string, or binary


def _parameters(tokens: list, at: int) -> tuple[list, int]:
    """A parenthesised parameter list from ``tokens[at]`` (its ``(``): its values and the end."""
    if tokens[at][0] != "(":
        raise ValueError(f"a parameter list starts with '(', not {tokens[at]}")
    at += 1
    values: list = []
    if tokens[at][0] == ")":
        return values, at + 1
    while True:
        kind, value = tokens[at]
        if kind == "(":
            inner, at = _parameters(tokens, at)
            values.append(tuple(inner))
        elif kind == "kw":
            inner, at = _parameters(tokens, at + 1)
            values.append(Typed(value, inner[0] if len(inner) == 1 else tuple(inner)))
        else:
            values.append(_value(kind, value))
            at += 1
        kind = tokens[at][0]
        at += 1
        if kind == ")":
            return values, at
        if kind != ",":
            raise ValueError(f"parameters are separated by ',', not {tokens[at - 1]}")


def parse(text: str) -> dict[int, list[tuple[str, list]]]:
    """Every record of a Part 21 file's DATA section: its partial entities, each its type and
    parameters (one for a simple record, several for a complex one)."""
    body = text[text.index("DATA;") + 5:text.index("ENDSEC;", text.index("DATA;"))]
    records: dict[int, list[tuple[str, list]]] = {}
    for statement in _statements(body):
        tokens = list(_tokens(statement))
        if tokens[0][0] != "ref" or tokens[1][0] != "=":
            raise ValueError(f"a record starts '#n=': {statement[:60]!r}")
        number, at = tokens[0][1], 2
        if tokens[at][0] == "(":
            parts, at = [], at + 1
            while tokens[at][0] != ")":
                name = tokens[at][1]
                values, at = _parameters(tokens, at + 1)
                parts.append((name, values))
            records[number] = parts
        else:
            values, _end = _parameters(tokens, at + 1)
            records[number] = [(tokens[at][1], values)]
    return records


def _statements(body: str):
    """The DATA section's statements, each up to its ``;`` outside a string."""
    start, at, quoted = 0, 0, False
    while at < len(body):
        char = body[at]
        if char == "'":
            quoted = not quoted
        elif char == ";" and not quoted:
            statement = body[start:at].strip()
            if statement:
                yield statement
            start = at + 1
        at += 1


# --- the report --------------------------------------------------------------------------------

# A limit dimension's representation items (CAx-IF's value range), by name.
_LIMITS = ("lower limit", "upper limit")


class Report:
    def __init__(self, records: dict[int, list[tuple[str, list]]]) -> None:
        self.records = records
        self.problems: list[str] = []
        self.referrers: dict[int, list[int]] = {}
        for number, parts in records.items():
            for _type, values in parts:
                for ref in _refs(values):
                    self.referrers.setdefault(ref, []).append(number)
                    if ref not in records:
                        self.problems.append(f"#{number} refers to #{ref}, which is no record")
        # Each shape representation's product (its record), by its ``SHAPE_DEFINITION_REPRESENTATION``.
        self.represents: dict[int, int | None] = {}
        for number in self.of_type("SHAPE_DEFINITION_REPRESENTATION"):
            definition, representation = self.part(number, "SHAPE_DEFINITION_REPRESENTATION")[:2]
            if isinstance(definition, Ref) and isinstance(representation, Ref):
                self.represents[representation.id] = self._product(definition.id)

    def _product(self, shape: int) -> int | None:
        """The ``PRODUCT`` record a ``PRODUCT_DEFINITION_SHAPE`` (by its number) is the shape of:
        through its ``PRODUCT_DEFINITION`` and that one's formation; None where the chain breaks."""
        try:
            definition = self.part(shape, "PRODUCT_DEFINITION_SHAPE")[2]
            formation = self.part(definition.id, "PRODUCT_DEFINITION")[2]
            kind = next(name for name in self.types(formation.id) if name.startswith("PRODUCT_DEFINITION_FORMATION"))
            product = self.part(formation.id, kind)[2]
            self.part(product.id, "PRODUCT")
            return product.id
        except (AttributeError, IndexError, KeyError, StopIteration, TypeError):
            return None

    def product(self, shape: int) -> str | None:
        """The name of the product a ``PRODUCT_DEFINITION_SHAPE`` is the shape of, or None."""
        return self._name(self._product(shape))

    def _name(self, product: int | None) -> str | None:
        return None if product is None else self.part(product, "PRODUCT")[1]

    def of_shape(self, aspect: int) -> str | None:
        """The product a shape aspect (a datum, a datum feature) is of: its ``of_shape``'s."""
        values = next((values for name, values in self.records.get(aspect, []) if name in _ASPECTS), None)
        return self.product(values[2].id) if values and isinstance(values[2], Ref) else None

    def faces_of(self) -> dict[int | None, list[str]]:
        """Every face name of each product (its record), as its shape representations hold them
        (each walked down from its items): what a name is unique within."""
        found: dict[int | None, list[str]] = defaultdict(list)
        for representation, product in self.represents.items():
            seen, stack = set(), [representation]
            while stack:
                number = stack.pop()
                if number in seen or number not in self.records:
                    continue
                seen.add(number)
                if "ADVANCED_FACE" in self.types(number):
                    found[product].append(self.part(number, "ADVANCED_FACE")[0])
                for _type, values in self.records[number]:
                    stack.extend(_refs(values))
        return found

    def types(self, number: int) -> list[str]:
        return [name for name, _values in self.records.get(number, [])]

    def part(self, number: int, name: str) -> list:
        for found, values in self.records[number]:
            if found == name:
                return values
        raise KeyError(f"#{number} is no {name}: {self.types(number)}")

    def of_type(self, name: str) -> list[int]:
        return sorted(number for number, parts in self.records.items() if any(found == name for found, _ in parts))

    def referring(self, number: int, name: str) -> list[int]:
        return sorted(referrer for referrer in self.referrers.get(number, []) if name in self.types(referrer))

    # Units and measures.
    def unit(self, number: int) -> str:
        parts = dict(self.records[number])
        if "SI_UNIT" in parts:
            prefix, name = parts["SI_UNIT"]
            prefix = prefix.name if isinstance(prefix, Enum) else None
            base = name.name
            symbol = {"METRE": "m", "RADIAN": "rad", "STERADIAN": "sr"}.get(base, base.lower())
            prefixes = {"MILLI": "m", "CENTI": "c", "MICRO": "u", "KILO": "k", None: ""}
            return (prefixes[prefix] if prefix in prefixes else prefix.lower()) + symbol
        if "CONVERSION_BASED_UNIT" in parts:
            return parts["CONVERSION_BASED_UNIT"][0]
        return "+".join(parts)

    def measure(self, number: int) -> dict[str, Any]:
        """A measure-with-unit record: its value, unit, and the type it is written with."""
        values = None
        for name, given in self.records[number]:
            if name in ("MEASURE_WITH_UNIT", "LENGTH_MEASURE_WITH_UNIT", "PLANE_ANGLE_MEASURE_WITH_UNIT") and given:
                values = given
        if values is None:
            raise KeyError(f"#{number} holds no measure: {self.types(number)}")
        component, unit = values[0], values[1]
        typed = isinstance(component, Typed)
        if not typed:
            self.problems.append(f"#{number}: {self.types(number)} holds an untyped measure value ({component}); "
                                 "AP242's measure_value is a select and needs its type (LENGTH_MEASURE(...))")
        return {"value": float(component.value if typed else component), "unit": self.unit(unit.id),
                "type": component.type if typed else None}

    # Geometry.
    def face(self, aspect: int) -> dict[str, Any] | None:
        """What a shape aspect identifies: its usage's face, named, with its surface."""
        usages = self.referring(aspect, "GEOMETRIC_ITEM_SPECIFIC_USAGE")
        if len(usages) != 1:
            self.problems.append(f"#{aspect}: {len(usages)} GEOMETRIC_ITEM_SPECIFIC_USAGE (one is expected)")
            return None
        usage = self.part(usages[0], "GEOMETRIC_ITEM_SPECIFIC_USAGE")
        item = usage[4].id
        product = self._name(self.represents.get(usage[3].id)) if isinstance(usage[3], Ref) else None
        if "ADVANCED_FACE" not in self.types(item):
            return {"item": self.types(item), "product": product}
        name, _bounds, geometry, same_sense = self.part(item, "ADVANCED_FACE")
        return {"face": f"#{item}", "name": name, "surface": self.surface(geometry.id),
                "same_sense": same_sense.name if isinstance(same_sense, Enum) else same_sense, "product": product}

    def features(self, aspect: int) -> list[dict[str, Any] | None]:
        """What a toleranced shape aspect identifies: its face, or a ``COMPOSITE_SHAPE_ASPECT``'s
        faces, one through each aspect a ``SHAPE_ASPECT_RELATIONSHIP`` relates to it, in order."""
        if "COMPOSITE_SHAPE_ASPECT" not in self.types(aspect):
            return [self.face(aspect)]
        members = []
        for relation in self.referring(aspect, "SHAPE_ASPECT_RELATIONSHIP"):
            _name, _description, relating, related = self.part(relation, "SHAPE_ASPECT_RELATIONSHIP")
            if relating == Ref(aspect):
                members.append(related.id)
        if not members:
            self.problems.append(f"#{aspect}: a COMPOSITE_SHAPE_ASPECT that relates no shape aspect")
        return [self.face(member) for member in members]

    def surface(self, number: int) -> dict[str, Any]:
        kind = self.types(number)[0]
        values = self.part(number, kind)
        if kind == "PLANE":
            origin, normal = self.placement(values[1].id)
            return {"type": "plane", "origin": origin, "normal": normal}
        if kind == "CYLINDRICAL_SURFACE":
            origin, axis = self.placement(values[1].id)
            return {"type": "cylinder", "radius": float(values[2]), "origin": origin, "axis": axis}
        return {"type": kind.lower()}

    def placement(self, number: int) -> tuple[list[float], list[float]]:
        values = self.part(number, "AXIS2_PLACEMENT_3D")
        origin = [float(v) for v in self.part(values[1].id, "CARTESIAN_POINT")[1]]
        axis = [float(v) for v in self.part(values[2].id, "DIRECTION")[1]] if values[2] is not UNSET else [0.0, 0.0, 1.0]
        return origin, axis

    # PMI.
    def dimensions(self) -> list[dict[str, Any]]:
        found = []
        for kind in ("DIMENSIONAL_SIZE", "DIMENSIONAL_LOCATION"):
            for number in self.of_type(kind):
                values = self.part(number, kind)
                entry: dict[str, Any] = {"record": f"#{number}", "entity": kind}
                if kind == "DIMENSIONAL_SIZE":
                    entry["name"] = values[1]
                    aspects = [values[0].id]
                else:
                    entry["name"] = values[0]
                    aspects = [values[2].id, values[3].id]
                entry["features"] = [self.face(aspect) for aspect in aspects]
                entry["product"] = _one([self.of_shape(aspect) for aspect in aspects], entry["features"])
                entry["nominal"] = self.nominal(number)
                entry["limits"] = self.limits(number)
                entry["notes"] = self.notes(number)
                entry["tolerance"] = self.plus_minus(number)
                found.append(entry)
        return found

    def _representations(self, dimension: int) -> list[int]:
        return [self.part(holder, "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION")[1].id
                for holder in self.referring(dimension, "DIMENSIONAL_CHARACTERISTIC_REPRESENTATION")]

    def _role(self, item: int) -> str | None:
        """A representation item's name: what its value is (``'nominal value'``, ``'lower limit'``)."""
        names = [values[0] for name, values in self.records[item] if name == "REPRESENTATION_ITEM"]
        return names[0] if names else None

    def nominal(self, dimension: int) -> dict[str, Any] | None:
        for representation in self._representations(dimension):
            for item in self.part(representation, "SHAPE_DIMENSION_REPRESENTATION")[1]:
                if "DESCRIPTIVE_REPRESENTATION_ITEM" in self.types(item.id) or self._role(item.id) in _LIMITS:
                    continue  # a note (``notes``) or a limit (``limits``), not the value
                measure = self.measure(item.id)
                measure["role"] = self._role(item.id)
                return measure
        return None

    def limits(self, dimension: int) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """A dimension's limits, (lower, upper), each a measure: its representation's items named
        ``'lower limit'`` and ``'upper limit'`` (CAx-IF's), or None where it has none."""
        found = {}
        for representation in self._representations(dimension):
            for item in self.part(representation, "SHAPE_DIMENSION_REPRESENTATION")[1]:
                if self._role(item.id) in _LIMITS:
                    found[self._role(item.id)] = self.measure(item.id)
        if not found:
            return None
        if len(found) != 2:
            self.problems.append(f"#{dimension}: a dimension of one limit ({', '.join(found)}); limits are a lower "
                                 "and an upper")
            return None
        return found["lower limit"], found["upper limit"]

    def notes(self, dimension: int) -> list[list[str]]:
        """A dimension's descriptive items, [name, description] each: CAx-IF's dimension modifiers
        (5.3), ``['dimensional note', 'theoretical']`` for a basic dimension."""
        found = []
        for representation in self._representations(dimension):
            for item in self.part(representation, "SHAPE_DIMENSION_REPRESENTATION")[1]:
                if "DESCRIPTIVE_REPRESENTATION_ITEM" in self.types(item.id):
                    name, description = self.part(item.id, "DESCRIPTIVE_REPRESENTATION_ITEM")
                    found.append([name, description])
        return found

    def plus_minus(self, dimension: int) -> dict[str, Any] | None:
        for holder in self.referring(dimension, "PLUS_MINUS_TOLERANCE"):
            tolerance_value = self.part(holder, "PLUS_MINUS_TOLERANCE")[0].id
            lower, upper = self.part(tolerance_value, "TOLERANCE_VALUE")
            low, high = self.measure(lower.id), self.measure(upper.id)
            if low["unit"] != high["unit"]:
                self.problems.append(f"#{tolerance_value}: its lower and upper deviations are in different units "
                                     f"({low['unit']}, {high['unit']})")
            return {"lower": low["value"], "upper": high["value"], "unit": high["unit"],
                    "types": [low["type"], high["type"]]}
        return None

    def datums(self) -> list[dict[str, Any]]:
        found = []
        for number in self.of_type("DATUM"):
            values = self.part(number, "DATUM")
            features, aspects = [], [number]
            for relation in self.referring(number, "SHAPE_ASPECT_RELATIONSHIP"):
                relating = self.part(relation, "SHAPE_ASPECT_RELATIONSHIP")[2].id
                if "DATUM_FEATURE" in self.types(relating):
                    features.append(self.face(relating))
                    aspects.append(relating)
            found.append({"record": f"#{number}", "identification": values[4], "features": features,
                          "product": _one([self.of_shape(aspect) for aspect in aspects], features)})
        return found

    def general_tolerances(self) -> list[dict[str, Any]]:
        """Each part's general tolerances: a 'default tolerances' property of a product's shape, its
        'tolerance class' (the standard, ``ISO 2768-mK``) and the product it is of."""
        found = []
        for number in self.of_type("PROPERTY_DEFINITION"):
            name, _description, definition = self.part(number, "PROPERTY_DEFINITION")[:3]
            if name != "default tolerances" or not isinstance(definition, Ref):
                continue
            classes = []
            for link in self.referring(number, "PROPERTY_DEFINITION_REPRESENTATION"):
                representation = self.part(link, "PROPERTY_DEFINITION_REPRESENTATION")[1]
                items = self.part(representation.id, "REPRESENTATION")[1] if isinstance(representation, Ref) else []
                for item in items:
                    if "DESCRIPTIVE_REPRESENTATION_ITEM" in self.types(item.id):
                        label, said = self.part(item.id, "DESCRIPTIVE_REPRESENTATION_ITEM")[:2]
                        if label == "tolerance class":
                            classes.append(said)
            found.append({"record": f"#{number}", "class": classes[0] if len(classes) == 1 else None,
                          "product": self.product(definition.id)})
        return found

    def tolerances(self) -> list[dict[str, Any]]:
        found = []
        for number, parts in sorted(self.records.items()):
            names = [name for name, _ in parts]
            kinds = [name for name in names if name.endswith("_TOLERANCE") and name not in
                     ("PLUS_MINUS_TOLERANCE", "GEOMETRIC_TOLERANCE")]
            if not kinds:
                if any(name.startswith("GEOMETRIC_TOLERANCE") for name in names):
                    self.problems.append(f"#{number}: a geometric tolerance of no characteristic this reads")
                continue
            supported = {kinds[0], "GEOMETRIC_TOLERANCE", "GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE"}
            for name in names:
                if name not in supported:
                    self.problems.append(f"#{number}: {name} is not read here, so its meaning is not checked")
            base = dict(parts).get("GEOMETRIC_TOLERANCE") or dict(parts)[kinds[0]]
            magnitude, aspect = base[2], base[3]
            entry: dict[str, Any] = {"record": f"#{number}", "entity": kinds[0],
                                     "magnitude": self.measure(magnitude.id), "datums": [], "zone": None,
                                     "features": self.features(aspect.id)}
            # Of one product, or of none: its aspect, its faces and every datum its frame names.
            products = [self.of_shape(aspect.id)]
            reference = dict(parts).get("GEOMETRIC_TOLERANCE_WITH_DATUM_REFERENCE")
            for system in reference[0] if reference else ():
                products.append(self.of_shape(system.id) if "DATUM_SYSTEM" in self.types(system.id) else None)
                for compartment in self.part(system.id, "DATUM_SYSTEM")[4]:
                    base_datum = self.part(compartment.id, "DATUM_REFERENCE_COMPARTMENT")[4]
                    entry["datums"].append(self.part(base_datum.id, "DATUM")[4] if isinstance(base_datum, Ref)
                                           else str(base_datum))
                    products.append(self.of_shape(base_datum.id) if isinstance(base_datum, Ref) else None)
            entry["product"] = _one(products, entry["features"])
            for zone in self.referring(number, "TOLERANCE_ZONE"):
                form = self.part(zone, "TOLERANCE_ZONE")[5].id
                entry["zone"] = self.part(form, "TOLERANCE_ZONE_FORM")[0]
                for definition in self.referrers.get(zone, []):
                    entry.setdefault("zone_definitions", []).append(self.types(definition))
            found.append(entry)
        return found


# The entities whose third attribute is the ``PRODUCT_DEFINITION_SHAPE`` they are of (``of_shape``).
_ASPECTS = ("SHAPE_ASPECT", "COMPOSITE_SHAPE_ASPECT", "DATUM_FEATURE", "DATUM", "DATUM_SYSTEM")


def _one(products: list[str | None], features: list[dict[str, Any] | None]) -> str | None:
    """The one product a record and the faces it is on are of, or None where they are of none or of
    several (a record of one part on another's faces, or measured from its datums, matches nothing)."""
    found = set(products) | {(feature or {}).get("product") for feature in features}
    return found.pop() if len(found) == 1 else None


def _refs(values: Any):
    if isinstance(values, Ref):
        yield values.id
    elif isinstance(values, Typed):
        yield from _refs(values.value)
    elif isinstance(values, (list, tuple)):
        for value in values:
            yield from _refs(value)


def report(path: Path, data: bytes | None = None) -> dict[str, Any]:
    """What a STEP file's PMI says: its schema, its products' names (``products``, one per
    ``PRODUCT``), its dimensions, datums and tolerances (each with the ``product`` it and its faces
    are of, or None), the face names each product uses more than once (``ambiguousFaceNames``, by
    product), and its problems. ``data`` is the file's bytes where they are read already
    (``check``)."""
    text = (path.read_bytes() if data is None else data).decode("utf-8")
    found = Report(parse(text))
    schema = _SCHEMA.search(text.split("DATA;", 1)[0])
    faces = found.faces_of()
    # The products that hold geometry, by name (an assembly holds none: its parts do).
    held = {product: names for product, names in faces.items() if names}
    result = {"file": path.name, "schema": schema.group(1) if schema else None,
              "products": sorted(str(found._name(product)) for product in held),
              "dimensions": found.dimensions(), "datums": found.datums(), "tolerances": found.tolerances(),
              "generalTolerances": found.general_tolerances()}
    # Every face of a product counts, annotated or not: one it holds twice names neither.
    by_name: dict[str | None, list[str]] = defaultdict(list)
    for product, names in held.items():
        by_name[found._name(product)].extend(names)
    result["ambiguousFaceNames"] = {
        product: sorted(name for name, count in Counter(names).items() if count > 1)
        for product, names in sorted(by_name.items(), key=lambda item: str(item[0]))}
    result["problems"] = sorted(set(found.problems))
    return result


# --- the check of an export --------------------------------------------------------------------


def _near(actual: Any, expected: Any) -> bool:
    return (isinstance(actual, (int, float)) and isinstance(expected, (int, float))
            and math.isfinite(actual) and math.isfinite(expected)
            and abs(actual - expected) <= 1e-9 * max(1, abs(actual), abs(expected)))


def _measure(actual: Any, expected: Any) -> bool:
    return (isinstance(actual, dict) and isinstance(expected, dict)
            and actual.get("unit") == expected.get("unit")
            and _near(actual.get("value"), expected.get("value")))


def _element(ref: str) -> str:
    """A canonical ref's element: the face's name, which the STEP writes on its ``ADVANCED_FACE``."""
    element = refs.parse(ref)[1][-1].element
    return element if isinstance(element, str) else f"{element[0]} {element[1]}"


def _dimension_matches(dimension: dict[str, Any], row: dict[str, Any]) -> bool:
    kind = dimension.get("type")
    if kind not in ("diameter", "distance") or row.get("name") != {"diameter": "diameter", "distance": "linear distance"}[kind]:
        return False
    nominal, tolerance = dimension.get("nominal"), dimension.get("tolerance")
    # A basic dimension carries AP242's 'theoretical' note (CAx-IF 5.3), and nothing else does.
    if bool(dimension.get("basic")) != (["dimensional note", "theoretical"] in (row.get("notes") or [])):
        return False
    actual = row.get("tolerance")
    if tolerance is not None and tolerance.get("type") == "limits":
        # Limits are sizes of their own: a file's serve no nominal (``nominal: null``), and are millimetres.
        unit = nominal.get("unit") if isinstance(nominal, dict) else "mm"
        return actual is None and _limits_match(tolerance, unit, row)
    if not isinstance(nominal, dict):
        return False
    if row.get("limits") is not None or not _measure(row.get("nominal"), nominal):
        return False
    if tolerance is None:
        return actual is None
    return (tolerance.get("type") == "plus_minus" and isinstance(actual, dict)
            and actual.get("unit") == nominal.get("unit")
            and _near(actual.get("lower"), tolerance.get("lower"))
            and _near(actual.get("upper"), tolerance.get("upper")))


def _limits_match(tolerance: dict[str, Any], unit: Any, row: dict[str, Any]) -> bool:
    """A dimension given limits against a row: the same two limits, in the nominal's unit. XCAF
    holds the limits alone, so the file's nominal value is their midpoint, never the one measured."""
    lower, upper, limits = tolerance.get("lower"), tolerance.get("upper"), row.get("limits")
    if not (isinstance(lower, (int, float)) and isinstance(upper, (int, float))
            and isinstance(limits, (list, tuple)) and len(limits) == 2):
        return False
    return (_measure(limits[0], {"value": lower, "unit": unit}) and _measure(limits[1], {"value": upper, "unit": unit})
            and _measure(row.get("nominal"), {"value": (lower + upper) / 2, "unit": unit}))


# The entity each characteristic the engine writes is written as.
_TOLERANCE_ENTITIES = {"flatness": "FLATNESS_TOLERANCE", "position": "POSITION_TOLERANCE",
                       "surface_profile": "SURFACE_PROFILE_TOLERANCE"}


def _tolerance_matches(tolerance: dict[str, Any], row: dict[str, Any]) -> bool:
    entity = _TOLERANCE_ENTITIES.get(tolerance.get("characteristic"))
    # The reader does not establish material modifiers or zones other than a diameter's.
    if entity is None or tolerance.get("modifier") or tolerance.get("zone") not in (None, "", "diameter"):
        return False
    return (row.get("entity") == entity
            and _measure(row.get("magnitude"), tolerance)
            and row.get("datums", []) == tolerance.get("datums", [])
            and row.get("zone") == ("cylindrical or circular" if tolerance.get("zone") == "diameter" else None))


# How near a file's surface is to the model's: a length within a millionth of the part's size (and
# of a millimetre, the least), a direction within 1e-9 of parallel.
_LENGTH, _PARALLEL = 1e-6, 1e-9


def _unit(vector: Any) -> list[float] | None:
    if not (isinstance(vector, (list, tuple)) and len(vector) == 3
            and all(isinstance(v, (int, float)) for v in vector)):
        return None
    length = math.sqrt(sum(v * v for v in vector))
    return [v / length for v in vector] if length > 0 and math.isfinite(length) else None


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _off_axis(point: list[float], origin: list[float], axis: list[float]) -> float:
    """How far ``point`` lies from the line through ``origin`` along the unit ``axis``."""
    d = [p - o for p, o in zip(point, origin)]
    along = _dot(d, axis)
    return math.sqrt(max(0.0, _dot(d, d) - along * along))


def _same_surface(found: Any, model: Any) -> bool:
    """A face's surface as the file writes it against the model's face (``pmi.step_surfaces``): a
    plane's normal parallel (either sense: one plane) and its origin on the model's plane; a
    cylinder's radius, its axis parallel and through the model's axis. A face of another kind is
    checked by its name alone, as long as the file writes no plane or cylinder for it."""
    if not isinstance(found, dict) or not isinstance(model, dict):
        return False
    kind = model.get("type")
    if kind not in ("plane", "cylinder"):
        return found.get("type") not in ("plane", "cylinder")
    if found.get("type") != kind:
        return False
    origin, at = found.get("origin"), model.get("origin")
    if not all(isinstance(point, (list, tuple)) and len(point) == 3 for point in (origin, at)):
        return False
    scale = max([1.0, *(abs(v) for v in (*origin, *at)), abs(found.get("radius") or 0), abs(model.get("radius") or 0)])
    direction, wanted = _unit(found.get("normal" if kind == "plane" else "axis")), _unit(
        model.get("normal" if kind == "plane" else "axis"))
    if direction is None or wanted is None or abs(abs(_dot(direction, wanted)) - 1.0) > _PARALLEL:
        return False
    if kind == "plane":
        return abs(_dot([a - b for a, b in zip(origin, at)], wanted)) <= _LENGTH * scale
    radius, expected = found.get("radius"), model.get("radius")
    return (isinstance(radius, (int, float)) and isinstance(expected, (int, float))
            and abs(radius - expected) <= _LENGTH * scale and _off_axis(origin, at, wanted) <= _LENGTH * scale)


def _matches(entry: dict[str, Any], row: dict[str, Any], surfaces: dict[str, Any] | None = None) -> bool:
    """Whether ``row`` of a file is ``entry``: on the faces of its names, each face's surface the
    model's (``surfaces``, by canonical ref; not compared where None), with its values. A general
    tolerance (a note stating one) is on no face: its part's 'default tolerances', of its standard."""
    stated = (entry.get("note") or {}).get("general_tolerance") if entry["kind"] == "note" else None
    if stated:
        return "class" in row and row["class"] == stated
    given = entry.get("refs") or []
    if not given or any(not isinstance(ref.get("ref"), str) or ref.get("status", "ok") != "ok" for ref in given):
        return False
    features = row.get("features", [])
    if sorted(_element(ref["ref"]) for ref in given) != sorted(feature.get("name", "") for feature in features):
        return False
    if surfaces is not None:
        by_name = {feature.get("name"): feature for feature in features}
        if not all(_same_surface(by_name[_element(ref["ref"])].get("surface"), surfaces.get(ref["ref"]))
                   for ref in given):
            return False
    if entry["kind"] == "datum":
        letter = (entry.get("datum") or {}).get("letter")
        return bool(letter) and row.get("identification") == letter
    if entry["kind"] == "dimension":
        return _dimension_matches(entry.get("dimension") or {}, row)
    if entry["kind"] == "geometric_tolerance":
        return _tolerance_matches(entry.get("geometric_tolerance") or {}, row)
    return False


def _written_as_nothing(entry: dict[str, Any]) -> bool:
    """A general profile that covers no face: linked to nothing, so the writer writes no record of it."""
    return (entry.get("kind") == "geometric_tolerance" and entry.get("status") == "ok" and not entry.get("refs")
            and bool((entry.get("geometric_tolerance") or {}).get("general")))


def compare(entries: list[dict[str, Any]], found: dict[str, Any], surfaces: dict[str, Any] | None = None,
            parts: dict[int, str] | None = None) -> dict[str, Any]:
    """A document's PMI entries against a file's ``report``: how many match one record each, of
    how many, and why any does not; a file whose problems say it cannot be checked at all (no AP242,
    a record the reader cannot read) matches nothing. Within each part alone: an entry is held to
    the records of its part's product (``parts``: each prototype index's name, as the file names
    its product), so face names and datum letters need be unique only within a part, and a name
    its part uses twice, two parts of one name, or a letter one part's records repeat verifies
    none of that part. Given the model's faces (``surfaces``: ``pmi.step_surfaces``), each record's
    faces are held to their geometry too, so a face of the right name on the wrong surface matches
    nothing. A general profile that covers no face matches no record, and is verified by none
    being left over. A note is the document's alone (a STEP carries none): it is neither expected
    nor counted, but a general tolerance, which the file states as its part's 'default
    tolerances'. Nothing is guessed: any problem fails the check."""
    from cadgen.engine.pmi import step_entries

    entries = step_entries(entries)
    parts = parts or {}
    problems = list(found.get("problems") or [])
    result = {"matched": 0, "total": len(entries), "problems": problems}
    if not entries:
        problems.append("The model has no PMI to verify.")
    if not str(found.get("schema", "")).startswith("AP242_"):
        problems.append("The file does not declare AP242.")
    if problems:
        return result
    rows = (list(found.get("datums", [])) + list(found.get("dimensions", [])) + list(found.get("tolerances", []))
            + list(found.get("generalTolerances", [])))
    products = Counter(found.get("products") or [])
    ambiguous = found.get("ambiguousFaceNames")
    # Each part's entries, by the product the file names it as: checked apart, or not at all.
    by_part: dict[Any, list[dict[str, Any]]] = defaultdict(list)
    for entry in entries:
        by_part[entry.get("part")].append(entry)
    unverifiable: set[Any] = set()
    for part, held in by_part.items():
        name = parts.get(part) if isinstance(part, int) else None
        said = f"part {name}" if name is not None else f"part {part}"
        if name is None:
            problems.append(f"{said}: the document names no product for it; its annotations cannot be verified.")
        elif sum(1 for other in by_part if parts.get(other) == name) > 1 or products[name] != 1:
            problems.append(f"{said}: {products[name] or 'no'} products of the file are named {name!r}; name each "
                            "part apart, or its annotations cannot be verified.")
        else:
            owners_of: dict[str, set[str]] = defaultdict(set)
            for entry in held:
                for ref in entry.get("refs", []):
                    if isinstance(ref.get("ref"), str):
                        owners_of[_element(ref["ref"])].add(ref["ref"])
            letters = [row.get("identification") for row in found.get("datums", []) if row.get("product") == name]
            if any(len(owners) > 1 for owners in owners_of.values()):
                problems.append(f"{said}: two of its faces share a name; their exported associations cannot be "
                                "verified.")
            elif not isinstance(ambiguous, dict):
                problems.append("The reader did not establish whether exported face names are unique.")
            elif any(face in owners_of for face in ambiguous.get(name) or ()):
                problems.append(f"{said}: an exported face name is ambiguous across its geometry; its association "
                                "cannot be verified.")
            elif len(set(letters)) != len(letters):
                problems.append(f"{said}: its exported datum letters are repeated; their references cannot be "
                                "verified.")
            else:
                continue
        unverifiable.add(part)
    remaining = list(rows)
    # Each entry said by its id, and by its part's name too where the document has several.
    several = len(by_part) > 1
    letters_of: dict[str, set[Any]] = defaultdict(set)
    for entry in entries:
        if entry.get("kind") == "datum":
            letters_of[(entry.get("datum") or {}).get("letter")].add(entry.get("part"))
    for entry in entries:
        if entry.get("part") in unverifiable:
            continue
        named = entry.get("label") or entry.get("id")
        if several:
            named = f"{parts.get(entry.get('part'))}/{named}"
        if _written_as_nothing(entry):
            result["matched"] += 1
            continue
        product = parts.get(entry.get("part"))
        mine = [row for row in remaining if row.get("product") == product]
        match = next((row for row in mine if entry.get("status") == "ok" and _matches(entry, row, surfaces)), None)
        if match is None and surfaces is not None and any(entry.get("status") == "ok" and _matches(entry, row)
                                                          for row in mine):
            problems.append(f"{named}: its face in the file is not the model's face (its plane or cylinder "
                            "differs).")
        elif match is None:
            problems.append(f"{named}: values, units, datum order or face association could not be verified.")
            letter = (entry.get("datum") or {}).get("letter") if entry.get("kind") == "datum" else None
            if letter is not None and len(letters_of[letter]) > 1:
                # Found of OCCT's writer: it writes one DATUM per letter in a file, every part's frames on it.
                problems.append(f"Datum {letter} is defined on {len(letters_of[letter])} parts: the STEP writer "
                                "writes one datum of a letter per file; give each part's datums letters of their "
                                "own.")
        else:
            remaining.remove(match)
            result["matched"] += 1
    left = [row for row in remaining if not any(parts.get(part) == row.get("product") for part in unverifiable)]
    if left:
        problems.append(f"{len(left)} exported annotations did not match the model.")
    return result


def check(entries: list[dict[str, Any]], target: Path, surfaces: dict[str, Any] | None = None,
          parts: dict[int, str] | None = None) -> dict[str, Any]:
    """``compare`` of the file at ``target`` (against the model's faces, ``surfaces``, each part
    as its product, ``parts``), with the SHA-256 of the bytes checked, read once: the result
    belongs to those bytes, whatever the viewer opens next. A file the reader cannot read is a
    check that found a problem, counted as ``compare`` counts, the notes never."""
    from cadgen.engine.pmi import step_entries

    data = target.read_bytes()
    try:
        result = compare(entries, report(target, data), surfaces, parts)
    except Exception as error:  # noqa: BLE001 - said as the check's problem, which refuses the file
        result = {"matched": 0, "total": len(step_entries(entries)),
                  "problems": [f"The STEP reader could not complete the check: {error}"]}
    return {**result, "sha256": hashlib.sha256(data).hexdigest()}
