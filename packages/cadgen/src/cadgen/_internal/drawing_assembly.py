"""An assembly drawn as a set: the parts list read off the assembly, the balloons
that key a view to it, and the general arrangement and part sheets
:func:`cadgen.eng_drawing.assembly_sheets` makes.

A parts list is the assembly's distinct parts, each once, with how many times it
occurs. Two occurrences are one part when they carry the same name, colour and
material and the same geometry: one prototype placed several times (the kernel's shape
shared, as the engine places a part used twice and as ``read_step`` and
``read_xbf`` hand back a shared product), or an exact translated copy, which a
boolean check confirms. A name, a colour or a shape alone never merges two
parts: two parts that happen to have identical geometry can be different parts
(a steel spacer and a brass one), a label's detail often names a finish
(``piston_rod:chrome``), and mirror images have identical volumes. Identical
shapes under different names are kept apart and reported, so the author can
merge them with :meth:`PartsList.merge` when they are one part.

A balloon's leader lands on a point of its part the view sees, found by casting
rays from the viewer; the balloons stand in even columns whose leaders do not
cross. The parts list itself is drawn with the rest of the sheet's furniture.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterator, NamedTuple, Sequence

from cadgen._internal.drawing_base import (
    _DEFAULT_TEXT, _DIM_ROW, FAMILIES, _LABEL_ROOM, _MARGIN, _SIDES, _STANDARD_SCALES, _TITLE_W, _look,
    _scale_label,
)
from cadgen._internal.drawing_sheet import (
    _LARGEST_SCALE, _OffFrame, _list_height, _next_smaller, _notes_base, _notes_height, _revisions_height,
)
from cadgen._internal.drawing_views import _view_extent

if TYPE_CHECKING:
    from cadgen._internal.drawing_report import _Facts
    from cadgen.eng_drawing import Sheet, View


#: How the parts of an assembly may be joined, each with the word its flag note
#: begins with. A liquid adhesive is never modelled, so the note carries it.
JOINTS = ("weld", "braze", "solder", "rivet", "crimp", "press_fit", "bond", "tape", "overmold", "snap",
          "not_bonded")
_JOINT_WORDS = {"press_fit": "PRESS FIT", "snap": "SNAP FIT", "not_bonded": "NOT BONDED"}


def _joint_note(text: str, joint: str | None) -> str:
    """A flag note's words: the joint's own first ("BOND: LOCTITE 401")."""
    if joint is None:
        return text
    if joint not in JOINTS:
        raise ValueError(f"unknown joint {joint!r}; one of {', '.join(JOINTS)}")
    word = _JOINT_WORDS.get(joint, joint.upper())
    return f"{word}: {text}" if text else word


def _item_of(view, key: int | str) -> Item:
    """The item of the parts list a view balloons that a flag names."""
    if not view._balloons:
        raise ValueError(f"flag(item={key!r}) on the {view.name} view finds the item in the parts list the view "
                         f"balloons, and it balloons none; {view.name}.balloons(parts) first")
    return view._balloons[0][key]


def _item_point(view, key: int | str) -> tuple[float, float, float]:
    """A point a view sees on an item of the parts list it balloons."""
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector

    item = _item_of(view, key)
    cast = IntCurvesFace_ShapeIntersector()
    cast.Load(view.shape.wrapped, 1e-7)
    point = visible_point(item.occurrences, cast, _look(view))
    if point is None:
        raise ValueError(f"flag(item={key!r}): the {view.name} view shows none of item {item.number} "
                         f"({item.description or 'unnamed'}); flag it in a view that shows it, or with at=")
    return point


#: The fields an author may fill in on a parts-list row. Everything else on an
#: item is read off the model.
FIELDS = ("description", "part_number", "material", "spec", "supplier", "family")


@dataclass(slots=True, eq=False)
class Item:
    """One row of a parts list: a distinct part and how many the assembly holds.

    ``number`` is the item number its balloons carry. ``description`` defaults to
    the model's own name for the part made readable (``piston_rod:chrome`` reads
    ``PISTON ROD, CHROME``); ``part_number``, ``material``, its ``spec`` and
    ``supplier`` are blank unless the author states them, because the model does
    not. ``family`` is the material family a section hatches it as. ``shape`` is
    one occurrence in the part's own frame, for its detail sheet; ``occurrences``
    are all of them, placed in the assembly. An item the model does not hold (an
    adhesive, a grease) has neither, and a quantity of ``"AR"``, as required.
    """

    number: int
    description: str
    quantity: int | str
    part_number: str = ""
    material: str = ""
    spec: str = ""
    supplier: str = ""
    family: str = ""
    labels: tuple[str, ...] = ()
    refs: tuple[str, ...] = ()
    shape: Any = None
    occurrences: tuple = ()
    #: The prototypes (geometries placed one or more times) its occurrences are.
    prototypes: tuple = ()


class PartsList:
    """An assembly's parts, numbered in the order the assembly first holds them.

    Iterate it for the items; index it by item number or by a part's name in the
    model (``parts[3]``, ``parts["coil_spring"]``). ``assembly`` is the whole
    assembly as one shape, placed, which is what the general arrangement's views
    draw. ``twins`` are pairs of item numbers whose parts have the same shape
    under different names or colours.
    """

    def __init__(self, assembly, items: Sequence[Item], twins: Sequence[tuple[int, int]] = ()) -> None:
        self.assembly = assembly
        self.items = tuple(items)
        self.twins = tuple(twins)
        #: Set once sheets are drawn from this list: its numbering is then theirs.
        self._frozen = False

    def __iter__(self) -> Iterator[Item]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, key: int | str) -> Item:
        if isinstance(key, bool) or not isinstance(key, (int, str)):
            raise TypeError(f"a parts list is indexed by item number or part name, got {key!r}")
        if isinstance(key, int):
            if not 1 <= key <= len(self.items):
                raise KeyError(f"no item {key}: this parts list numbers 1 to {len(self.items)}")
            return self.items[key - 1]
        exact = [item for item in self.items if key in item.labels]
        named = exact or [item for item in self.items if key in {_base(label) for label in item.labels}]
        if len(named) == 1:
            return named[0]
        listing = ", ".join(f"{item.number} {item.labels[0] if item.labels else '(unnamed)'}" for item in self.items)
        if not named:
            raise KeyError(f"no part named {key!r} in this parts list; its items are {listing}")
        raise KeyError(f"{len(named)} items are named {key!r} (items "
                       f"{', '.join(str(item.number) for item in named)}); index them by number")

    def set(self, key: int | str, **fields: str) -> "PartsList":
        """State what the model cannot carry for one item: ``description``,
        ``part_number``, ``material``, its ``spec`` ("AMS 4027") and
        ``supplier``, or the material ``family`` a section hatches it as (one of
        ``FAMILIES``). Returns the list, so calls chain."""
        unknown = sorted(set(fields) - set(FIELDS))
        if unknown:
            raise TypeError(f"parts.set() takes {', '.join(FIELDS)}; not {', '.join(unknown)}")
        item = self[key]
        for name, value in fields.items():
            if not isinstance(value, str):
                raise TypeError(f"parts.set({key!r}, {name}=...) takes a string, got {value!r}")
        if fields.get("family") and fields["family"] not in FAMILIES:
            raise ValueError(f"unknown material family {fields['family']!r}; one of {', '.join(FAMILIES)}")
        for name, value in fields.items():
            setattr(item, name, value)
        return self

    def add(self, description: str, *, quantity: int | str = "AR", part_number: str = "", material: str = "",
            spec: str = "", supplier: str = "") -> Item:
        """List an item the model does not hold: an adhesive, a sealant, a grease,
        a shim set at assembly. It is numbered last, takes no balloon and has no
        sheet; ``quantity`` is a count or ``"AR"``, as required."""
        if self._frozen:
            raise ValueError("add() lists a new item, and sheets are already drawn from this list; add before "
                             "assembly_sheets() or balloons()")
        if not (quantity == "AR" or (isinstance(quantity, int) and not isinstance(quantity, bool) and quantity > 0)):
            raise ValueError(f"quantity is a positive count or \"AR\" (as required), got {quantity!r}")
        for name, value in (("description", description), ("part_number", part_number), ("material", material),
                            ("spec", spec), ("supplier", supplier)):
            if not isinstance(value, str):
                raise TypeError(f"parts.add({name}=...) takes a string, got {value!r}")
        if not description:
            raise ValueError("parts.add() needs a description: it is the item's only name")
        item = Item(len(self.items) + 1, description, quantity, part_number=part_number, material=material,
                    spec=spec, supplier=supplier)
        self.items += (item,)
        return item

    def merge(self, *keys: int | str, description: str | None = None) -> "PartsList":
        """List several items as one part: the parts the model names differently
        (``mounting_eye:lower``, ``mounting_eye:upper``) that are one part. Their
        geometry must be the same: a shared prototype, or an exact translated
        copy, of one material. The first item keeps its place and takes the
        others' quantities and what :meth:`set` stated for any of them; two
        different values of one field are refused, as two parts. The items
        after it are numbered again. ``description`` replaces the one read from
        their labels (the segments they share)."""
        if self._frozen:
            raise ValueError("merge() renumbers the parts list, and sheets are already drawn from it; merge "
                             "before assembly_sheets() or balloons()")
        if len(keys) < 2:
            raise TypeError("merge() takes two or more items")
        chosen = []
        for key in keys:
            item = self[key]
            if any(item is other for other in chosen):
                raise ValueError(f"merge(): item {item.number} is named twice")
            chosen.append(item)
        absent = next((item for item in chosen if item.shape is None), None)
        if absent is not None:
            raise ValueError(f"merge(): item {absent.number} ({absent.description}) is not in the model, so it is "
                             "the same shape as nothing; merge the parts the model holds")
        first = min(chosen, key=lambda item: item.number)
        for other in chosen:
            if other is first:
                continue
            shared = set(first.prototypes) & set(other.prototypes)
            if not shared and not _same_part(first.shape, other.shape):
                raise ValueError(
                    f"merge(): item {other.number} ({other.description or 'unnamed'}) is not the same shape as item "
                    f"{first.number} ({first.description or 'unnamed'}); only identical parts are one part"
                )
            if _material(other.shape) != _material(first.shape):
                raise ValueError(
                    f"merge(): item {other.number} ({other.description or 'unnamed'}) is not made of what item "
                    f"{first.number} ({first.description or 'unnamed'}) is, in the model; two materials are two parts"
                )
        # What set() stated for them: one value each, or the merge would print one
        # part's and drop the other's.
        stated = {}
        for name in FIELDS:
            if name == "description":
                continue
            values = {getattr(item, name) for item in chosen} - {""}
            if len(values) > 1:
                listed = ", ".join(f"item {item.number} {getattr(item, name)!r}" for item in chosen
                                   if getattr(item, name))
                raise ValueError(f"merge(): the items differ in {name} ({listed}); one part has one {name}, so "
                                 "set() it the same on each, or leave them apart")
            if values:
                stated[name] = values.pop()
        for other in chosen:
            if other is first:
                continue
            first.labels += other.labels
            first.refs += other.refs
            first.occurrences += other.occurrences
            first.prototypes += tuple(p for p in other.prototypes if p not in first.prototypes)
            first.quantity += other.quantity
        first.description = description if description is not None else _describe(first.labels)
        for name, value in stated.items():
            setattr(first, name, value)
        gone = {id(item) for item in chosen if item is not first}
        kept = [item for item in self.items if id(item) not in gone]
        old = {item.number: item for item in self.items}
        for number, item in enumerate(kept, start=1):
            item.number = number
        renumber = {n: item.number for n, item in old.items() if id(item) not in gone}
        self.items = tuple(kept)
        self.twins = tuple(sorted({tuple(sorted((renumber[a], renumber[b]))) for a, b in self.twins
                                   if a in renumber and b in renumber and renumber[a] != renumber[b]}))
        return self


def parts_list(source) -> PartsList:
    """The parts list of an assembly: a build123d ``Compound`` built with
    ``children=``, as an assembly model's ``.shape``, ``cadgen.read_xbf`` and
    ``cadgen.read_step`` hand one back. Occurrences sharing one geometry (one
    prototype placed several times) are one item."""
    from build123d import Location

    if not getattr(source, "children", None):
        raise TypeError(
            "parts_list() reads an assembly: a build123d Compound made with children=[...], such as an "
            "assembly model's .shape or cadgen.read_step(path). A single part has no parts list; draw it with "
            "Sheet.three_views()."
        )
    leaves = list(_walk(source, ()))
    if not leaves:
        raise ValueError("parts_list(): the assembly holds no parts")
    assembly = source
    # A prototype is one geometry however often it is placed: occurrences of it share
    # the kernel's shape (``IsPartner``), as the engine places a part used twice.
    prototypes: list = []
    groups: list[dict] = []
    for label, ref, world in leaves:
        local = world.located(Location())
        key = next((n for n, held in enumerate(prototypes) if held.IsPartner(local.wrapped)), None)
        if key is None:
            prototypes.append(local.wrapped)
            key = len(prototypes) - 1
        colour, material = _colour(world), _material(world)
        group = None
        for g in groups:
            if g["label"] != label or g["colour"] != colour or g["material"] != material:
                continue
            if key in g["keys"] or _same_part(g["local"], local):
                group = g
                break
        if group is None:
            groups.append({"label": label, "colour": colour, "material": material, "keys": [key],
                           "local": local, "labels": [label], "refs": [ref], "placed": [world]})
        else:
            if key not in group["keys"]:
                group["keys"].append(key)
            group["labels"].append(label)
            group["refs"].append(ref)
            group["placed"].append(world)
    twins = []
    for i, a in enumerate(groups):
        for j in range(i + 1, len(groups)):
            b = groups[j]
            if set(a["keys"]) & set(b["keys"]) or _same_part(a["local"], b["local"]):
                twins.append((i + 1, j + 1))
    return PartsList(assembly, [
        Item(number, _describe(g["labels"]), len(g["placed"]), labels=tuple(g["labels"]), refs=tuple(g["refs"]),
             shape=g["local"], occurrences=tuple(g["placed"]), prototypes=tuple(g["keys"]))
        for number, g in enumerate(groups, start=1)], twins)


def _material(shape) -> str | None:
    """A shape's material (a ``bd_materials`` one) as a comparable key, or None:
    two grades of steel are two parts, however alike they look."""
    from cadgen.engine.document import material_key

    return material_key(getattr(shape, "material", None))


def _colour(shape) -> tuple | None:
    """A shape's colour as a comparable tuple, or None when it has none."""
    colour = getattr(shape, "color", None)
    if colour is None:
        return None
    try:
        return tuple(round(float(c), 3) for c in tuple(colour))
    except TypeError:
        return (str(colour),)


def _walk(shape, path: tuple[str, ...]):
    """An assembly's leaves: each one's name, its ref (its path of names in the
    tree, as ``cadgen.engine.refs`` writes an occurrence's: ``hand/finger.2`` is
    the second child of ``hand`` named ``finger``), and the leaf placed where the
    assembly puts it."""
    from collections import Counter

    from cadgen.engine.refs import Segment

    children = list(shape.children)
    counts = Counter(child.label or "" for child in children)
    seen: Counter = Counter()
    for child in children:
        label = child.label or ""
        seen[label] += 1
        number = seen[label] if counts[label] > 1 else None
        plain = bool(label) and label == label.strip() and not any(ch in label for ch in '/,"')
        segment = (f"{label}.{number}" if number else label) if plain else str(Segment(label, True, number))
        if getattr(child, "children", None):
            yield from _walk(child, path + (segment,))
        else:
            yield label, "/".join(path + (segment,)), child.located(child.global_location)


def _base(label: str) -> str:
    """The part a label names, before any detail: ``mounting_eye:lower`` is a mounting eye."""
    return (label or "").split(":")[0].strip()


def _describe(labels: Sequence[str]) -> str:
    """A part's name as the parts list prints it: the label segments every
    occurrence shares, read out (``piston_rod:chrome`` -> ``PISTON ROD, CHROME``)."""
    split = [label.split(":") for label in labels if label]
    if not split:
        return ""
    common = []
    for segments in zip(*split):
        if any(s != segments[0] for s in segments):
            break
        common.append(segments[0])
    words = common or split[0]
    return ", ".join(w.replace("_", " ").strip().upper() for w in words if w.strip())


def _same_part(a, b) -> bool:
    """Whether ``b`` is an exact translated copy of ``a``: the same faces, volume
    and size, and nothing left over when one is moved onto the other."""
    from build123d import CenterOf, Location

    if not a.solids() or not b.solids() or len(a.faces()) != len(b.faces()):
        return False
    volume = a.volume
    if abs(volume - b.volume) > 1e-6 * max(volume, 1.0) or abs(a.area - b.area) > 1e-6 * max(a.area, 1.0):
        return False
    sa, sb = a.bounding_box().size, b.bounding_box().size
    if any(abs(x - y) > 1e-4 for x, y in zip(sa, sb)):
        return False
    try:
        moved = a.moved(Location(b.center(CenterOf.MASS) - a.center(CenterOf.MASS)))
        left = sum(s.volume for s in (moved - b).solids()) + sum(s.volume for s in (b - moved).solids())
    except Exception:  # noqa: BLE001 - a boolean the kernel cannot do proves nothing; list them apart
        return False
    return left <= 1e-6 * max(volume, 1.0)


#: How far apart a face's samples are, and how many one occurrence may cost.
_SAMPLE_PITCH = 4.0
_SAMPLES = 2500


#: Two coaxial surfaces of different parts meet, one in the other, when their
#: diameters differ by at most 10 % of the bore or 2 mm, whichever is more: a
#: fit, a clearance a rod runs in, or an interference. Further apart is a gap.
_FIT_SHARE = 0.10
_FIT_LEAST = 2.0


@dataclass(frozen=True)
class Fit:
    """A turned surface of one item in a bore of another, on one axis: their
    nominal diameters, the axis's direction, a point on it where they meet, and
    in how many places the assembly has them so."""

    inner: int
    outer: int
    shaft: float
    bore: float
    axis: tuple[float, float, float]
    at: tuple[float, float, float]
    places: int = 1


@dataclass(frozen=True)
class Abutment:
    """Two items' flat faces touching square to a fit's axis: no end play at
    nominal sizes. ``at`` is a point on the axis in the plane they share, and
    ``places`` how many times the assembly has them so."""

    items: tuple[int, int]
    axis: tuple[float, float, float]
    at: tuple[float, float, float]
    places: int = 1


def interfaces(parts: PartsList) -> tuple[list[Fit], list[Abutment]]:
    """Where an assembly's parts meet on a turned axis: each turned surface of one
    part in a bore of another, their diameters close enough to meet (an
    interference among them), and the flat faces of parts on such an axis that
    touch square to it. Read off the placed occurrences; a joint the assembly
    repeats (four bolts in four holes, two bushings in one bore) is one, with
    the number of places: each pair of occurrences that meet there."""
    from cadgen._internal.drawing_features import _TOUCH, _full, _merge_split_faces, _surface_segments

    placed = [(item.number, shape) for item in parts for shape in item.occurrences]
    turned = []
    for _number, shape in placed:
        found = {}
        for key, (d, foot, segments) in _surface_segments(shape).items():
            whole = [seg for seg in _merge_split_faces(segments) if seg.kind == "cyl" and _full(seg)]
            if whole:
                found[key] = (d, foot, whole)
        turned.append(found)
    fits: dict[tuple, list] = {}
    on_axis: dict[tuple, tuple[tuple, set[int]]] = {}
    for i in range(len(placed)):
        for j in range(i + 1, len(placed)):
            if placed[i][0] == placed[j][0]:
                continue
            for key in turned[i].keys() & turned[j].keys():
                d, foot, _ = turned[i][key]
                for inner, outer in ((i, j), (j, i)):
                    for shaft in turned[inner][key][2]:
                        for bore in turned[outer][key][2]:
                            if shaft.concave or not bore.concave:
                                continue
                            lo, hi = max(shaft.lo, bore.lo), min(shaft.hi, bore.hi)
                            across = (2 * shaft.r_lo, 2 * bore.r_lo)
                            if hi - lo < _TOUCH or abs(across[1] - across[0]) > max(_FIT_LEAST, _FIT_SHARE * across[1]):
                                continue
                            at = tuple(round(f + (lo + hi) / 2 * c, 6) + 0.0 for f, c in zip(foot, d))
                            name = (placed[inner][0], placed[outer][0], round(across[0], 4), round(across[1], 4))
                            # Each pair of occurrences meeting is one place: two
                            # bushings in one bore are two, four pins on four axes four.
                            fits.setdefault(name, [d, at, set()])[2].add((key, inner, outer))
                            on_axis.setdefault(key, (d, set()))[1].update((i, j))
    flats: dict[tuple, list] = {}

    def square(m: int, d) -> list:
        """An occurrence's flat faces square to ``d``, with where each lies along it."""
        name = (m, tuple(round(c, 4) for c in d))
        if name not in flats:
            flats[name] = [(f, _along(f, d)) for f in placed[m][1].faces() if _square_to(f, d)]
        return flats[name]

    abutments: dict[tuple, list] = {}
    for key, (d, members) in on_axis.items():
        foot = turned[min(members)][key][1]
        for m in sorted(members):
            for n in sorted(members):
                if n <= m or placed[m][0] == placed[n][0]:
                    continue
                for fa, at_a in square(m, d):
                    for fb, at_b in square(n, d):
                        if abs(at_a - at_b) > 1e-4 or not _touching(fa, fb):
                            continue
                        items = tuple(sorted((placed[m][0], placed[n][0])))
                        at = tuple(round(f + at_a * c, 6) + 0.0 for f, c in zip(foot, d))
                        # A pair of occurrences touching in one plane is one place,
                        # however many of the axes through it share it.
                        abutments.setdefault(items, [d, at, set()])[2].add((m, n, round(at_a, 3)))
    return ([Fit(*name, d, at, len(keys)) for name, (d, at, keys) in fits.items()],
            [Abutment(items, d, at, len(spots)) for items, (d, at, spots) in abutments.items()])


def _square_to(face, d) -> bool:
    from build123d import GeomType

    if face.geom_type != GeomType.PLANE:
        return False
    n = face.normal_at()
    return abs(abs(n.X * d[0] + n.Y * d[1] + n.Z * d[2]) - 1) < 1e-9


def _along(face, d) -> float:
    c = face.center()
    return c.X * d[0] + c.Y * d[1] + c.Z * d[2]


def _touching(fa, fb) -> bool:
    """Whether two coplanar flat faces face each other over an area."""
    from OCP.BRepAlgoAPI import BRepAlgoAPI_Common
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps

    na, nb = fa.normal_at(), fb.normal_at()
    if na.X * nb.X + na.Y * nb.Y + na.Z * nb.Z > -1 + 1e-9:
        return False  # side by side, not face to face
    common = BRepAlgoAPI_Common(fa.wrapped, fb.wrapped)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(common.Shape(), props)
    return props.Mass() > 1e-6


def visible_point(occurrences, cast, look, *, faces: int = 40) -> tuple[float, float, float] | None:
    """A point on one of ``occurrences`` that the viewer looking along ``-look``
    sees: on a face turned toward them, with nothing of the assembly (``cast``,
    an intersector loaded with it) between. The most central such point of the
    first occurrence that shows one, so a leader lands well inside the part's
    outline rather than on its edge; None when every occurrence is hidden.
    """
    from OCP.BRepClass import BRepClass_FaceClassifier
    from OCP.BRepGProp import BRepGProp_Face
    from OCP.BRepTools import BRepTools
    from OCP.TopAbs import TopAbs_IN
    from OCP.gp import gp_Dir, gp_Lin, gp_Pnt, gp_Pnt2d, gp_Vec

    toward = gp_Dir(*look)
    for placed in occurrences:
        found = []
        budget = _SAMPLES
        for face in sorted(placed.faces(), key=lambda f: -f.area)[:faces]:
            if budget <= 0 or len(found) >= 12:
                break
            u0, u1, v0, v1 = BRepTools.UVBounds_s(face.wrapped)
            inside = BRepClass_FaceClassifier()
            surface = BRepGProp_Face(face.wrapped)
            # Samples every few millimetres across the face, so a part showing only
            # a narrow band between two others still shows one.

            def at(u: float, v: float):
                point, normal = gp_Pnt(), gp_Vec()
                surface.Normal(u, v, point, normal)
                return point, normal

            um, vm = (u0 + u1) / 2, (v0 + v1) / 2
            counts = [max(3, min(21, int(at(a[0], a[1])[0].Distance(at(b[0], b[1])[0]) / _SAMPLE_PITCH) + 1))
                      for a, b in (((u0, vm), (u1, vm)), ((um, v0), (um, v1)))]
            grid = [(u0 + (u1 - u0) * (i + 0.5) / counts[0], v0 + (v1 - v0) * (j + 0.5) / counts[1])
                    for i in range(counts[0]) for j in range(counts[1])]
            # Middle first: a central point makes the better leader end.
            grid.sort(key=lambda uv: abs(uv[0] - um) / max(u1 - u0, 1e-9) + abs(uv[1] - vm) / max(v1 - v0, 1e-9))
            for u, v in grid:
                if budget <= 0 or len(found) >= 12:
                    break
                budget -= 1
                # The UV rectangle overhangs a trimmed face: a plate's centre
                # sample can sit in its bore.
                inside.Perform(face.wrapped, gp_Pnt2d(u, v), 1e-7)
                if inside.State() != TopAbs_IN:
                    continue
                point, normal = at(u, v)
                if normal.Magnitude() < 1e-12:
                    continue
                normal.Normalize()
                if normal.X() * look[0] + normal.Y() * look[1] + normal.Z() * look[2] < 0.25:
                    continue
                start = gp_Pnt(point.X() + look[0] * 1e-3, point.Y() + look[1] * 1e-3, point.Z() + look[2] * 1e-3)
                cast.Perform(gp_Lin(start, toward), 0.0, 1e7)
                if cast.NbPnt() == 0:
                    found.append((point.X(), point.Y(), point.Z()))
        if found:
            mid = tuple(sum(p[k] for p in found) / len(found) for k in range(3))
            return min(found, key=lambda p: sum((p[k] - mid[k]) ** 2 for k in range(3)))
    return None


def spread(desired: Sequence[float], gap: float, lo: float, hi: float,
           avoid: Sequence[tuple[float, float]] = ()) -> list[float]:
    """Positions along one line, in the order of ``desired`` (sorted), each at
    least ``gap`` from the next and as near its desired place as that allows,
    within ``[lo, hi]`` when they fit there: a run of balloons that would touch
    is centred on the places it wanted rather than pushed all one way.

    No position falls inside an ``avoid`` interval while there is room outside
    them: each desired place goes to the nearest stretch of the line between
    them, and is spread within it."""
    free = [(lo, hi)]
    for a, b in sorted(avoid):
        free = [piece for x0, x1 in free for piece in ((x0, min(x1, a)), (max(x0, b), x1)) if piece[1] >= piece[0]]
    if not free or len(free) == 1:
        out = _spread(desired, gap, *(free[0] if free else (lo, hi)))
    else:
        out = []
        index = 0
        runs: list[list[float]] = [[] for _ in free]
        for y in desired:
            # The nearest stretch, never one before the last used: order is kept.
            index = min(range(index, len(free)), key=lambda k: max(free[k][0] - y, y - free[k][1], 0.0))
            runs[index].append(y)
        for (x0, x1), run in zip(free, runs):
            out.extend(_spread(run, gap, x0, x1))
    # Whatever the stretches could not hold moves on past the next one, so no two
    # end up closer than ``gap`` and none inside an avoided interval; a run that
    # still does not fit ends past ``hi``, which the caller refuses.
    placed: list[float] = []
    for y in out:
        if placed and y < placed[-1] + gap:
            y = placed[-1] + gap
        moved = True
        while moved:
            moved = False
            for a, b in avoid:
                if a < y < b:
                    y, moved = b, True
        placed.append(y)
    return placed


def _spread(desired: Sequence[float], gap: float, lo: float, hi: float) -> list[float]:
    def start(block) -> float:
        count, total = block
        return max(lo, min(total / count, hi - (count - 1) * gap))

    blocks: list[list] = []
    for y in desired:
        blocks.append([1, y])
        while len(blocks) > 1 and start(blocks[-2]) + blocks[-2][0] * gap > start(blocks[-1]) + 1e-9:
            count, total = blocks.pop()
            before = blocks[-1][0]
            # Each moved element's offset from its block's start grows by the rows above it.
            blocks[-1] = [before + count, blocks[-1][1] + total - count * before * gap]
    out: list[float] = []
    for block in blocks:
        first = start(block)
        out.extend(first + j * gap for j in range(block[0]))
    return out


# --- balloons -------------------------------------------------------------------------

def _refuse_balloons_on(view) -> None:
    """Balloons key a whole view, or a section that cuts the parts one by one
    (each balloon lands in its part's cut); a detail is a piece of another view,
    keyed where that view is."""
    if view._detail is not None:
        raise ValueError(f"balloons() keys a whole view or a section, and the {view.name} view is a detail; "
                         "balloon the view it enlarges.")
    if view._section is not None and view._section_parts is None:
        raise ValueError(f"balloons() on the {view.name} view's section keys the parts it cuts, and it cuts the "
                         "assembly whole; cut it part by part with section(..., parts=parts).")


#: A balloon: its radius and numeral height, the run of leader between the
#: annotation it stands outside and its circle, the space between two balloons,
#: and the dot a leader ends in on the part.
_BALLOON_R = 5.0
_BALLOON_TEXT = 5.0
_BALLOON_LEAD = 8.0
_BALLOON_AIR = 2.0
_DOT_R = 0.7
#: How far along its column a balloon may move to clear its leader from text,
#: and in what steps.
_BALLOON_SEARCH = 80.0
_BALLOON_STEP = 0.5


def _balloon_axis(bounds) -> bool:
    """Whether a view's balloons stand in columns beside it (a tall view) rather
    than in rows above and below it (a wide one)."""
    return (bounds[3] - bounds[2]) >= (bounds[1] - bounds[0])


def _draw_balloons(msp, sheet: Sheet, view: View, keyed_on_sheet: set, facts: _Facts | None, model_to_sheet, box,
                   reach: dict, text, printed: Sequence[tuple], obstacles: Sequence[tuple],
                   warnings: list | None, anchors: dict | None = None) -> list[tuple]:
    """Balloon each item the view shows that this sheet has not yet keyed.

    Each leader ends in a dot on a point of the part that the view sees (nothing
    of the assembly in front of it). The balloons stand in a column on each side
    of a tall view (a row above and below a wide one), outside everything
    already drawn there, each as near the height of the point it keys as the
    others allow. Points near the middle go to whichever side has fewer, which
    keeps the two columns even. A column may run the frame's height but keeps
    off ``obstacles`` (other views, the title block, the parts list), and no
    balloon stands where its leader would run through text already ``printed``
    (``(value, box)`` pairs); leaders that would cross are swapped. A column the
    paper cannot hold is refused, never drawn off the sheet. On a section,
    ``anchors`` (item number to sheet point) puts each leader's dot inside the
    part's cut instead, and only the parts it cuts are keyed. Returns each
    balloon's leader and circle box, ``((start, end), (x0, y0, x1, y1))``.
    """
    from ezdxf.enums import TextEntityAlignment
    from OCP.IntCurvesFace import IntCurvesFace_ShapeIntersector
    from shapely.geometry import LineString, box as rect

    look = _look(view)
    cast = IntCurvesFace_ShapeIntersector()
    cast.Load(view.shape.wrapped, 1e-7)
    keyed, drawn = [], []
    for parts in view._balloons:
        for item in parts:
            if (id(parts), item.number) in keyed_on_sheet:
                continue
            if anchors is not None:
                if item.number in anchors:
                    keyed.append((item.number, anchors[item.number], parts))
                continue
            point = visible_point(item.occurrences, cast, look)
            if point is None:
                continue
            keyed.append((item.number, model_to_sheet(point), parts))
    vx0, vx1, vy0, vy1 = box
    tall = _balloon_axis(box)
    pick, along = (0, 1) if tall else (1, 0)
    mid = ((vx0 + vx1) / 2, (vy0 + vy1) / 2)
    band = 0.1 * ((vx1 - vx0) if tall else (vy1 - vy0))
    low, high = ("left", "right") if tall else ("bottom", "top")
    sides: dict[str, list] = {low: [], high: []}
    for number, point, parts in sorted(keyed, key=lambda k: (k[1][along], k[0])):
        if point[pick] < mid[pick] - band:
            side = low
        elif point[pick] > mid[pick] + band:
            side = high
        else:
            side = low if len(sides[low]) <= len(sides[high]) else high
        sides[side].append((number, point, parts))
    r, pitch, m = _BALLOON_R, 2 * _BALLOON_R + _BALLOON_AIR, _MARGIN
    frame = ((m, sheet.width - m), (m, sheet.height - m))
    texts = [(value, rect(b[0], b[1], b[2], b[3])) for value, b in printed]

    def centre_of(line: float, spot: float) -> tuple[float, float]:
        return (line, spot) if tall else (spot, line)

    def leader(centre, point) -> LineString:
        run = math.hypot(point[0] - centre[0], point[1] - centre[1]) or 1.0
        return LineString([(centre[0] + (point[0] - centre[0]) * r / run, centre[1] + (point[1] - centre[1]) * r / run),
                           point])

    for side, rows in sides.items():
        if not rows:
            continue
        out = -1.0 if side in ("left", "bottom") else 1.0
        edge = {"left": vx0, "right": vx1, "bottom": vy0, "top": vy1}[side]
        line = edge + out * (reach[side] + _BALLOON_LEAD + r)
        across, lengthwise = frame[pick], frame[along]
        if not across[0] + 1.0 <= line - r and line + r <= across[1] - 1.0:
            raise _OffFrame(f"{view.name}.balloons(): no room on {sheet._size()} for a column of balloons on the "
                            f"{side} of the {view.name} view. A larger sheet or a smaller scale gives it room.",
                            _next_smaller(sheet._scale()))
        lo, hi = lengthwise[0] + r + 1.0, lengthwise[1] - r - 1.0
        # The strip the leaders cross, between the column and the view.
        near, far = sorted((edge, line - out * r))
        avoid = [(b[along] - 1.0, b[along + 2] + 1.0) for _v, b in printed if b[pick] < far and b[pick + 2] > near]
        # Paper the column itself may not take: other views, the title block and
        # parts list, the revision table.
        avoid += [(o[2 * along] - r - 1.0, o[2 * along + 1] + r + 1.0) for o in obstacles
                  if o[2 * pick] < line + r + 1.0 and o[2 * pick + 1] > line - r - 1.0]
        spots = spread([point[along] for _n, point, _p in rows], pitch, lo, hi, avoid)
        if spots and (spots[-1] > hi + 1e-6 or spots[0] < lo - 1e-6):
            raise _OffFrame(
                f"{view.name}.balloons(): {len(rows)} balloons do not fit on the {side} of the {view.name} view on "
                f"{sheet._size()}, clear of the other views and the parts list. A larger sheet or a smaller scale gives "
                "them room, or balloon some items on another view.",
                _next_smaller(sheet._scale()))
        # Leaders that cross swap balloons until none do.
        for _round in range(len(spots) ** 2):
            crossed = next(((i, j) for i in range(len(rows)) for j in range(i + 1, len(rows))
                            if leader(centre_of(line, spots[i]), rows[i][1]).crosses(
                                leader(centre_of(line, spots[j]), rows[j][1]))), None)
            if crossed is None:
                break
            i, j = crossed
            spots[i], spots[j] = spots[j], spots[i]
        # A leader through text: the nearest free place along the column where it
        # runs clear, or a word saying where it does not.
        for i, (number, point, _parts) in enumerate(rows):
            def clear(spot: float) -> bool:
                path = leader(centre_of(line, spot), point)
                return not any(path.intersects(shape) for _v, shape in texts)

            if clear(spots[i]):
                continue
            others = [spot for k, spot in enumerate(spots) if k != i]
            steps = int(_BALLOON_SEARCH / _BALLOON_STEP)
            candidates = sorted((spots[i] + k * _BALLOON_STEP for k in range(-steps, steps + 1) if k),
                                key=lambda y: abs(y - spots[i]))
            better = next((y for y in candidates if lo <= y <= hi
                           and all(abs(y - o) >= pitch - 1e-6 for o in others)
                           and not any(a < y < b for a, b in avoid) and clear(y)
                           and not any(leader(centre_of(line, y), point).crosses(
                               leader(centre_of(line, spots[k]), rows[k][1])) for k in range(len(rows)) if k != i)),
                          None)
            if better is not None:
                spots[i] = better
            elif warnings is not None:
                hit = next(v for v, shape in texts if leader(centre_of(line, spots[i]), point).intersects(shape))
                warnings.append(f"{view.name}.balloons(): the leader to balloon {number} runs through {hit.strip()!r}; "
                                "give the view more room, or balloon that item on another view.")
        for (number, point, parts), spot in zip(rows, spots):
            centre = centre_of(line, spot)
            path = leader(centre, point)
            msp.add_line(path.coords[0], path.coords[1], dxfattribs={"layer": "NOTES"})
            dot = msp.add_hatch(dxfattribs={"layer": "NOTES"})
            dot.set_solid_fill(color=256)
            dot.paths.add_edge_path().add_arc(point, _DOT_R, 0.0, 360.0)
            msp.add_circle(centre, r, dxfattribs={"layer": "NOTES"})
            text(str(number), centre[0], centre[1], _BALLOON_TEXT, TextEntityAlignment.MIDDLE_CENTER, "NOTES")
            drawn.append((tuple(path.coords), (centre[0] - r, centre[1] - r, centre[0] + r, centre[1] + r)))
            keyed_on_sheet.add((id(parts), number))
            if facts is not None:
                facts.of_list(parts)["ballooned"].add(number)
        reach[side] += _BALLOON_LEAD + 2 * r
    return drawn


# --- the general arrangement and part sheets ------------------------------------------

class _PartOf(NamedTuple):
    """A part's sheet of an assembly drawing: its item, the assembly's title, and
    the title, material, spec and subtitle the item last gave the sheet."""

    item: Item
    whole: str
    shown: tuple[str, str, str, str]


def _item_subtitle(item: Item, whole: str) -> str:
    return f"ITEM {item.number}{f' (QTY {item.quantity})' if item.quantity > 1 else ''} OF {whole}"


def _item_shown(item: Item, whole: str) -> tuple[str, str, str, str]:
    """What an item gives its part's sheet: title, material, spec, subtitle."""
    if item.spec and not item.material:
        raise ValueError(f"item {item.number} ({item.description or 'unnamed'}) has spec={item.spec!r} and no "
                         f"material, which its sheet's MATERIAL reads before the spec; "
                         f"parts.set({item.number}, material=...)")
    return item.description or f"ITEM {item.number}", item.material, item.spec, _item_subtitle(item, whole)


def _refresh_from_item(sheet: Sheet) -> None:
    """A part's sheet shows its item as the item stands when it renders: its
    description, material and number, so ``parts.set()`` after
    ``assembly_sheets()`` reaches the sheet. A title, material or subtitle the
    author has set on the sheet since is theirs, and kept."""
    item, whole, shown = sheet._item
    fresh = _item_shown(item, whole)
    current = (sheet.title, sheet.material, sheet.spec, sheet.subtitle)
    kept = tuple(new if now == old else now for new, now, old in zip(fresh, current, shown))
    sheet.title, sheet.material, sheet.spec, sheet.subtitle = kept
    sheet._item = _PartOf(item, whole, kept)


#: The smallest scale a general arrangement is drawn at: below it the views are specks.
_GA_SMALLEST = 1 / 50
#: The share of the general arrangement's frame height its parts list may take;
#: longer lists continue on further sheets.
_GA_LIST_SHARE = 0.45


def _assembly_room(size: tuple[float, float], overall: set) -> dict:
    """What a general-arrangement view's annotation takes on each side: its
    overall sizes, its balloons (beside a tall view, above and below a wide one)
    and its label."""
    room = {side: 4.0 for side in _SIDES}
    row = _DIM_ROW + _DEFAULT_TEXT * 1.5
    if "width" in overall:
        room["top"] += row
    if "height" in overall:
        room["left"] += row
    for side in (("left", "right") if size[1] >= size[0] else ("bottom", "top")):
        room[side] += _BALLOON_LEAD + 2 * _BALLOON_R + _BALLOON_AIR
    room["bottom"] += _LABEL_ROOM
    return room


def _arrange_assembly(sheet: Sheet, shape, second: str) -> tuple[float, list]:
    """The general arrangement's scale and views: the front view and ``second``
    side by side (or one above the other) in the paper left of the title block,
    each with room for its overall sizes, balloons and label, at the largest
    standard scale that fits; the isometric in the column above the parts list,
    at the largest standard scale up to that one which fits there, or left out
    when even a fifth of it does not."""
    m, W, H = _MARGIN, sheet.width, sheet.height
    box = shape.bounding_box().size
    extents = {"front": (box.X, box.Z), "right": (box.Y, box.Z), "top": (box.X, box.Y)}
    overall = {"front": {"width", "height"}, second: {"width"} if second == "right" else {"height"}}
    notes = _notes_height(sheet)
    a_x = (m + 4.0, W - m - _TITLE_W - 6.0)
    a_y = (m + 4.0 + (_notes_base(sheet) + notes if notes else 0.0), H - m - 4.0)
    third = sheet.projection == "THIRD ANGLE"

    def layout(s: float):
        sizes = {n: (extents[n][0] * s, extents[n][1] * s) for n in ("front", second)}
        rooms = {n: _assembly_room(extents[n], overall[n]) for n in ("front", second)}
        f, o = sizes["front"], sizes[second]
        rf, ro = rooms["front"], rooms[second]
        if second == "right":
            # Side by side, sharing the front view's height: third angle puts the
            # view from the right on the right.
            left, right = ((f, rf), (o, ro)) if third else ((o, ro), (f, rf))
            w = left[1]["left"] + left[0][0] + left[1]["right"] + right[1]["left"] + right[0][0] + right[1]["right"]
            h = max(f[1] + rf["top"] + rf["bottom"], o[1] + ro["top"] + ro["bottom"])
            x = a_x[0] + max(0.0, (a_x[1] - a_x[0] - w) / 2)
            y = a_y[0] + max(0.0, (a_y[1] - a_y[0] - h) / 2) + max(rf["bottom"], ro["bottom"]) + f[1] / 2
            cl = x + left[1]["left"] + left[0][0] / 2
            cr = x + left[1]["left"] + left[0][0] + left[1]["right"] + right[1]["left"] + right[0][0] / 2
            at = {"front": (cl, y), second: (cr, y)} if third else {"front": (cr, y), second: (cl, y)}
        else:
            # One above the other, sharing the front view's width: third angle
            # puts the view from above above.
            low, high = ((f, rf), (o, ro)) if third else ((o, ro), (f, rf))
            h = low[1]["bottom"] + low[0][1] + low[1]["top"] + high[1]["bottom"] + high[0][1] + high[1]["top"]
            w = max(f[0] + rf["left"] + rf["right"], o[0] + ro["left"] + ro["right"])
            y = a_y[0] + max(0.0, (a_y[1] - a_y[0] - h) / 2)
            x = a_x[0] + max(0.0, (a_x[1] - a_x[0] - w) / 2) + max(rf["left"], ro["left"]) + f[0] / 2
            yl = y + low[1]["bottom"] + low[0][1] / 2
            yh = y + low[1]["bottom"] + low[0][1] + low[1]["top"] + high[1]["bottom"] + high[0][1] / 2
            at = {"front": (x, yl), second: (x, yh)} if third else {"front": (x, yh), second: (x, yl)}
        return w <= a_x[1] - a_x[0] and h <= a_y[1] - a_y[0], at

    fitting = None
    for c in _STANDARD_SCALES:
        if not _GA_SMALLEST - 1e-12 <= c <= _LARGEST_SCALE:
            continue
        fits, at = layout(c)
        if fits:
            fitting = (c, at)
            break
    if fitting is None:
        # The views' own annotation -- overall sizes, balloon columns, labels --
        # does not fit beside the parts list at any useful scale. Drawing it at
        # 1:1000 would print the views as specks.
        raise ValueError(
            f"the general arrangement does not fit {sheet._size()} beside its parts list at any scale down to "
            f"{_scale_label(_GA_SMALLEST)}: the front and {second} views with their sizes and balloons need more "
            "than the paper left of the parts list. Give assembly_sheets() a larger size=."
        )
    scale, at = fitting
    slots = [("front", at["front"], None, None), (second, at[second], None, None)]
    b_x = (W - m - _TITLE_W, W - m - 4.0)
    b_y = (m + sheet._title_height() + _list_height(sheet) + 6.0, H - m - 4.0 - _revisions_height(sheet))
    iso_w, iso_h = _view_extent(shape, "iso", 1.0)
    room = _assembly_room((iso_w, iso_h), set())
    for c in (c for c in _STANDARD_SCALES if scale / 5 - 1e-9 <= c <= scale):
        if (iso_w * c + room["left"] + room["right"] <= b_x[1] - b_x[0]
                and iso_h * c + room["bottom"] + room["top"] <= b_y[1] - b_y[0]):
            x = b_x[0] + room["left"] + iso_w * c / 2 + (b_x[1] - b_x[0] - iso_w * c - room["left"] - room["right"]) / 2
            y = b_y[0] + room["bottom"] + iso_h * c / 2 + (b_y[1] - b_y[0] - iso_h * c - room["bottom"] - room["top"]) / 2
            own = None if abs(c / scale - 1) < 1e-9 else c
            slots.append(("iso", (x, y), own, "ISOMETRIC" if own is None else f"ISOMETRIC {_scale_label(c)}"))
            break
    return scale, slots


def _continuations(sheets: Sequence[Sheet]) -> dict[int, dict]:
    """For each sheet carrying a parts list, what the rest of the set says about
    it: where a split list continues from and to, and on which sheet each item it
    lists is detailed: ``{sheet number: {"from": n, "to": m, "sheets": {item
    number: sheet number}}}``, each key only where it applies."""
    runs: dict[int, list] = {}
    lists: dict[int, PartsList] = {}
    for index, sheet in enumerate(sheets, start=1):
        if sheet._parts is not None:
            parts, first, last = sheet._parts
            runs.setdefault(id(parts), []).append((first, last, index))
            lists[id(parts)] = parts
    detailed: dict[int, dict[int, int]] = {}
    for index, sheet in enumerate(sheets, start=1):
        if sheet._item is None:
            continue
        for key, parts in lists.items():
            if any(item is sheet._item.item for item in parts.items):
                detailed.setdefault(key, {})[sheet._item.item.number] = index
    out: dict[int, dict] = {}
    for key, spans in runs.items():
        spans.sort()
        for (_f0, l0, before), (f1, _l1, after) in zip(spans, spans[1:]):
            if f1 <= l0:
                raise ValueError(f"items {f1} to {l0} of one parts list are listed on sheet {before} and again on "
                                 f"sheet {after}; each item belongs to one run of the list")
            out.setdefault(before, {})["to"] = after
            out.setdefault(after, {})["from"] = before
        if key in detailed:
            for _first, _last, index in spans:
                out.setdefault(index, {})["sheets"] = detailed[key]
    return out
