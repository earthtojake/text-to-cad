"""STEP: AP242, written by the kernel's XCAF writer from the document.

The assembly with its instance and product names, colours per part and per painted face,
material names and densities (the writer's material mode), approximate standard surface
reflectance and transparency for material-bearing parts and faces, the element names on face
and edge sub-shape labels (``write.stepcaf.subshapes.name``), and the document's semantic PMI
(``pmi``: the writer's GD&T mode; ``export.translate`` refuses a STEP that would drop the code's,
``pmi.refuse_dropped``). A document as built is
written from its XCAF document itself; one held without it (a foreign STEP's), from the
view made a document again (``tree.tree_of``). The mechanism, its
configurations and the model's provenance are never in a STEP: the kernel has no writer
for them.

The same document writes the same bytes. The writer stamps the header's FILE_NAME with the
time of writing: it is ``WRITTEN_STAMP`` instead, set on the model's header. And it adds the
colour presentations (one per styled shape) to the model from a map keyed by shape, whose
order is the shapes' addresses, another in every process: in the written file they are put
back in the order of the shape representations they style, which the transfer numbered in the
document's order (``_settle``). The kernel numbers the assembly occurrences from a counter of the
process's, on from every STEP it wrote before: they are numbered from 1 in the file's order
instead, so a warm worker's STEP is the cold one's bytes. That is done to the file's
last records, the presentations and
what they alone refer to, as text: a model's millions of entities are never handed back to the
kernel one by one, which costs a fraction of a millisecond a call through the bindings (a
2.3-million-entity car took half an hour so). The writer breaks a record's lines at fixed
columns as it writes it, so a record whose numbers are rewritten in another width would keep the
breaks of the numbers it had, other breaks in every warm export: each record renumbered is put
on one line (``_one_line``; ISO 10303-21 sets no line length). Every other record is the
writer's, broken where its own text puts the breaks, the same text in every process.

Each usage of a prototype is a ``NEXT_ASSEMBLY_USAGE_OCCURRENCE`` of its own, named by the usage
(the component's name), of the one ``PRODUCT`` the prototype is (its name); a usage coloured its
own way is an ``OVER_RIDING_STYLED_ITEM`` whose ``PRESENTATION_STYLE_BY_CONTEXT`` names that
usage's shape representation. The writer finds a usage by its prototype's shape moved by the
usage's placement, and tells placements apart by their datum: a prototype placed alike under two
parents is placed apart for the transfer and set back after (``_usages_apart``), the same numbers
written, so no usage takes another's name or colour (juno's arms: 29 of 391 usages misnamed).

A build's document is written as its xbf reads back (``write``): reading a document sets each
placement from its matrix, which moves it by a last bit (``mesh.shape_bytes``), so the STEP of
the document in a build's memory and of the same document read from its xbf, in any process,
differ in the last digits of placements near zero (2,430 DIRECTION and CARTESIAN_POINT records
of juno's 309,303, the sign of a zero among them). A build's document is written and read
once, in memory, as saving it does, and its STEP is that document's.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

__all__ = ["SCHEMA", "WRITTEN_STAMP", "write"]

SCHEMA = "AP242DIS"
# FILE_NAME's time_stamp: the date the xbf's header holds (``document.WRITTEN_DATE``), whatever
# the clock.
WRITTEN_STAMP = "2000-01-01T00:00:00"


def write(view: Any, path: Path) -> None:
    from cadgen.engine import document

    source = view.source
    doc = source.xcaf
    if doc is None:
        from cadgen.engine.export.tree import tree_of

        doc = document.to_xcaf(tree_of(view))
    elif source.live:
        # Written and read once, as its xbf reads back (the module docstring).
        doc = document.read_bytes(document.to_bytes(doc, source.shapes.values()))
    write_document(doc, path)


def write_document(doc: Any, path: Path) -> None:
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.Message import Message
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs

    from cadgen.engine import pmi
    from cadgen.engine.document import _XCAF_LOCK

    with _XCAF_LOCK:
        stated = pmi.general_tolerances(doc)
        _quiet(Message)
        # The writer defines the translator's parameters: set them once it exists.
        writer = STEPCAFControl_Writer()
        Interface_Static.SetCVal_s("write.step.unit", "MM")
        Interface_Static.SetIVal_s("write.stepcaf.subshapes.name", 1)
        Interface_Static.SetCVal_s("write.step.schema", SCHEMA)
        writer.SetNameMode(True)
        writer.SetColorMode(True)
        writer.SetMaterialMode(True)
        writer.SetLayerMode(False)
        # The document's semantic PMI (``pmi``), as AP242's: the writer's default, said.
        writer.SetDimTolMode(True)
        with _usages_apart(doc):
            if not writer.Transfer(doc, STEPControl_AsIs):
                raise OSError(f"could not write {path}")
        from cadgen.engine.step_style import write_visual_styles

        changed_styles = write_visual_styles(writer, doc)
        _stamp(writer.ChangeWriter().Model())
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise OSError(f"could not write {path}")
    _settle(Path(path), changed_styles)
    if stated:
        _default_tolerances(Path(path), stated)


@contextmanager
def _usages_apart(doc: Any) -> Iterator[None]:
    """The document with every usage of a prototype placed apart from its others while the writer
    transfers it, and as it was after. AP242 gives each usage of a product its own
    ``NEXT_ASSEMBLY_USAGE_OCCURRENCE``, named by the usage, and styles a usage by a
    ``PRESENTATION_STYLE_BY_CONTEXT`` naming its shape representation; OCCT's writer finds a
    component's usage by its prototype's shape moved by the component's placement, and a placement
    is told from another by its datum, not by its value. Two components of one prototype at one
    placement datum -- one sub-part where two assemblies hold it alike, as a robot's left and right
    arms hold their shared parts, or at the identity, which has no datum -- are one key to it: the
    last one's name went on the first one's usage and none on the other's (a reader names it by
    its id), and an instance colour was put in the other usage's context. So each component that
    would be another's key is given a datum of its own, of the same transformation, written as
    the same numbers; the components and their assemblies' compounds are set back after, each
    compound's named shape at the version it had, so the document saves to the bytes it did."""
    from OCP.TDF import TDF_AttributeIterator, TDF_Label
    from OCP.collections import Sequence_TDF_Label
    from OCP.TNaming import TNaming_NamedShape
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_Location, XCAFDoc_ShapeTool

    from cadgen.engine.document import _entry

    tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    labels = Sequence_TDF_Label()
    tool.GetShapes(labels)
    placed: dict[tuple[str, int], list] = {}
    moved: list[tuple[Any, Any]] = []
    assemblies: list[Any] = []
    for at in range(1, labels.Length() + 1):
        assembly = labels.Value(at)
        if not XCAFDoc_ShapeTool.IsAssembly_s(assembly):
            continue
        assemblies.append(assembly)
        components = Sequence_TDF_Label()
        XCAFDoc_ShapeTool.GetComponents_s(assembly, components, False)
        for place in range(1, components.Length() + 1):
            component = components.Value(place)
            referred = TDF_Label()
            XCAFDoc_ShapeTool.GetReferredShape_s(component, referred)
            location = XCAFDoc_ShapeTool.GetLocation_s(component)
            others = placed.setdefault((_entry(referred), location.HashCode()), [])
            if any(location.IsEqual(other) for other in others):
                moved.append((component, location))
                location = TopLoc_Location(location.Transformation())
                XCAFDoc_Location.Set_s(component, location)
            others.append(location)
    versions = []
    if moved:
        for assembly in assemblies:
            # Its attributes walked, never found into a new attribute: a named shape so filled
            # shares the document's nodes and frees them when it goes.
            attributes = TDF_AttributeIterator(assembly)
            while attributes.More():
                named = attributes.Value()
                if isinstance(named, TNaming_NamedShape):
                    versions.append((named, named.Version()))
                attributes.Next()
        tool.UpdateAssemblies()
    try:
        yield
    finally:
        if moved:
            for component, location in moved:
                XCAFDoc_Location.Set_s(component, location)
            tool.UpdateAssemblies()
            for named, version in versions:
                named.SetVersion(version)


def _stamp(model: Any) -> None:
    """The header's time stamp pinned (``WRITTEN_STAMP``)."""
    from OCP.APIHeaderSection import APIHeaderSection_MakeHeader
    from OCP.TCollection import TCollection_HAsciiString

    header = APIHeaderSection_MakeHeader(model)
    header.SetTimeStamp(TCollection_HAsciiString(WRITTEN_STAMP))
    header.Apply(model)


# A record's start (``#12 = ``), a reference (``#12``), and a quoted string, in which neither is one.
_RECORD = re.compile(rb"(?m)^#(\d+)\s*=")
_REFERENCE = re.compile(rb"#(\d+)")
_QUOTED = re.compile(rb"'(?:[^']|'')*'")
_PRESENTATION = b"MECHANICAL_DESIGN_GEOMETRIC_PRESENTATION_REPRESENTATION"
# An assembly occurrence's id, its record's first argument, a quoted number; then the rest of
# the record, to its end (a semicolon outside its strings).
_OCCURRENCE = re.compile(rb"NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*'\d*'((?:'(?:[^']|'')*'|[^';])*;)")
# A line break the writer made outside a string, with the next line's indent.
_BREAK = re.compile(rb"\r?\n *")


def _settle(path: Path, changed_styles: bool = False) -> None:
    """The written file made a function of the document alone (see the module docstring): its
    presentations in the document's order (``_presentations``), its assembly occurrences
    numbered as a fresh process numbers them (``_occurrences``), and its PMI records as AP242
    has them (``_pmi_records``); written again when any changed it."""
    original = path.read_bytes()
    data = _prune_unused_styles(original) if changed_styles else original
    settled = _pmi_records(_occurrences(_presentations(data)))
    if settled != original:
        path.write_bytes(settled)


def _prune_unused_styles(data: bytes) -> bytes:
    """Remove detached originals left by replacing material styles.

    OCCT appends presentation records after the geometry. Only assignment
    records with no incoming references are roots for removal; shared colours,
    curve styles and contexts remain live. An unreferenced assignment styles no
    item, so it carries no appearance to preserve.
    Dropping these unreachable chains before numbering keeps allocation order out
    of the bytes without touching geometry or any reachable presentation.
    """
    found = data.find(_PRESENTATION)
    if found < 0:
        return data
    start = data.rfind(b"\n#", 0, found) + 1
    end = data.find(b"ENDSEC;", found)
    tail = data[start:end]
    heads = list(_RECORD.finditer(tail))
    records = {int(m.group(1)): tail[m.start():heads[i + 1].start() if i + 1 < len(heads) else len(tail)]
               for i, m in enumerate(heads)}
    refs = {number: [int(ref) for ref in _REFERENCE.findall(_QUOTED.sub(b"''", text[text.index(b"=") + 1:]))]
            for number, text in records.items()}
    counts: dict[int, int] = {}
    for references in refs.values():
        for ref in references:
            counts[ref] = counts.get(ref, 0) + 1
    pending = [number for number, record in records.items()
               if record.split(b"=", 1)[1].lstrip().startswith(b"PRESENTATION_STYLE_ASSIGNMENT(")]
    removed = set()
    while pending:
        number = pending.pop()
        if number in removed or number not in records or counts.get(number, 0):
            continue
        removed.add(number)
        for ref in refs[number]:
            counts[ref] -= 1
            if counts[ref] == 0:
                pending.append(ref)
    return data[:start] + b"".join(records[int(m.group(1))] for m in heads if int(m.group(1)) not in removed) + data[end:]


def _presentations(data: bytes) -> bytes:
    """The file's records from the first presentation on -- the presentations and what the
    transfer added after them -- renumbered where they stand, each presentation by the numbers
    of its context and of what its items style, followed by what it refers to there, depth
    first; then the rest of those records in their order. Everything before them is the
    transfer's, in the document's order, and refers to none of them."""
    found = data.find(_PRESENTATION)
    if found < 0:
        return data
    start = data.rfind(b"\n#", 0, found) + 1
    end = data.find(b"ENDSEC;", found)
    tail = data[start:end]
    heads = list(_RECORD.finditer(tail))
    records: dict[int, bytes] = {}
    order: list[int] = []
    for at, match in enumerate(heads):
        number = int(match.group(1))
        records[number] = tail[match.start():heads[at + 1].start() if at + 1 < len(heads) else len(tail)]
        order.append(number)
    # Each record's references, outside its strings, in the order written.
    refs = {number: [int(ref) for ref in _REFERENCE.findall(_QUOTED.sub(b"''", text[text.index(b"=") + 1:]))]
            for number, text in records.items()}

    def arguments(number: int) -> list[bytes]:
        """A record's top-level arguments, its strings blanked."""
        text = _QUOTED.sub(b"''", records[number])
        body = text[text.index(b"(", text.index(b"=")) + 1:text.rindex(b")")]
        split, depth, begun = [], 0, 0
        for at, byte in enumerate(body):
            if byte == 40:  # (
                depth += 1
            elif byte == 41:  # )
                depth -= 1
            elif byte == 44 and depth == 0:  # ,
                split.append(body[begun:at])
                begun = at + 1
        split.append(body[begun:])
        return split

    def first_ref(argument: bytes) -> int:
        match = _REFERENCE.search(argument)
        return int(match.group(1)) if match else 0

    def styled(number: int) -> tuple:
        given = arguments(number)
        targets = []
        for item in (int(ref) for ref in _REFERENCE.findall(given[1])):
            # A styled item's third argument is what it styles; one the transfer made before the
            # presentations is in the document's order already, and stands for itself, as does
            # one of another form.
            try:
                targets.append(first_ref(arguments(item)[2]) if item in records else item)
            except (IndexError, ValueError):
                targets.append(item)
        return first_ref(given[-1]), tuple(targets)

    presentations = sorted((number for number in order if _PRESENTATION in records[number][:120]), key=styled)
    placed: dict[int, int] = {}
    for number in [*presentations, *order]:
        stack = [number]
        while stack:
            current = stack.pop()
            if current in placed or current not in records:
                continue
            placed[current] = order[0] + len(placed)
            stack.extend(reversed(refs[current]))

    def renumbered(match: re.Match) -> bytes:
        return b"#%d" % placed.get(int(match.group(1)), int(match.group(1)))

    def rewrite(text: bytes) -> bytes:
        body = text.rstrip(b"\r\n")
        pieces, at = [], 0
        for quoted in _QUOTED.finditer(body):
            pieces.append(_REFERENCE.sub(renumbered, body[at:quoted.start()]))
            pieces.append(quoted.group(0))
            at = quoted.end()
        pieces.append(_REFERENCE.sub(renumbered, body[at:]))
        return _one_line(b"".join(pieces)) + text[len(body):]

    settled = b"".join(rewrite(records[number]) for number in sorted(placed, key=placed.__getitem__))
    return data[:start] + settled + data[end:]


def _occurrences(data: bytes) -> bytes:
    """Each assembly occurrence's id (``NEXT_ASSEMBLY_USAGE_OCCURRENCE``'s first argument) its
    place among them in the file, from 1: the kernel numbers them from a counter of the
    process's, on from every STEP it wrote before, so a warm worker's file would number them on
    from its earlier exports where a fresh process's starts at 1. The file's order is the
    transfer's, which is the document's, so the numbers are the same in every process."""
    counter = itertools.count(1)
    return _OCCURRENCE.sub(
        lambda match: b"NEXT_ASSEMBLY_USAGE_OCCURRENCE('%d'" % next(counter) + _one_line(match.group(1)), data)


def _one_line(text: bytes) -> bytes:
    """A record's text, or a piece of one, on one line: the writer's line breaks taken out of it.
    Outside its strings the writer breaks a line after a separator, never in place of one, and
    indents the next: the break and the indent go. Inside a string it breaks with no indent, and
    a reader joins the lines again: the break goes. A record whose numbers changed in width keeps
    the breaks the writer made of the numbers it had; on one line it is a function of its text."""
    if b"\n" not in text:
        return text
    pieces = text.split(b"'")  # a quote doubled in a string is an empty piece outside it
    for at in range(0, len(pieces), 2):
        pieces[at] = _BREAK.sub(b"", pieces[at])
    for at in range(1, len(pieces), 2):
        pieces[at] = pieces[at].replace(b"\r", b"").replace(b"\n", b"")
    return b"'".join(pieces)


# The kernel's writer gets three PMI records wrong, found by an AP242 reader of no OCCT
# (``ap242.py``, and the standard's EXPRESS):
# - a tolerance's bounds, ``TOLERANCE_VALUE``'s, as ``MEASURE_WITH_UNIT(0.2,#u)``: the value
#   untyped, where ``measure_value`` is a select a strict reader needs typed. They are written as
#   the CAx-IF practice has them, ``LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.2),#u)``, where
#   ``#u`` is a length unit;
# - beside every diametral zone, a ``RUNOUT_ZONE_DEFINITION`` of two attributes (the schema's
#   has three: no orientation) and the ``RUNOUT_ZONE_ORIENTATION`` of 0 it leaves unreferenced: a
#   runout zone's, on a tolerance that is no runout. Both dropped, with the angle only they
#   refer to; the zone and its form stay;
# - in a document with no dimension, every tolerance's magnitude in metres: the writer takes the
#   GD&T unit from the first dimension's context and, with none, a bare ``SI_UNIT($,.METRE.)``
#   (``STEPCAFControl_Writer::GetUnit``), the value left in the document's millimetres -- a
#   flatness of 0.05 mm written as 0.05 m. Each such measure refers to the file's millimetre
#   unit instead, and the bare metre, then unreferenced, is dropped.
_TOLERANCE_VALUE = re.compile(rb"TOLERANCE_VALUE\s*\(\s*#(\d+)\s*,\s*#(\d+)\s*\)")
_UNTYPED_BOUND = re.compile(rb"MEASURE_WITH_UNIT\s*\(\s*([-+]?[0-9.]+(?:[eE][-+]?[0-9]+)?)\s*,\s*#(\d+)\s*\)\s*;")
_RUNOUT = re.compile(rb"RUNOUT_ZONE_DEFINITION\s*\(\s*#\d+\s*,\s*\(\s*\)\s*\)\s*;")
_ORIENTATION = re.compile(rb"RUNOUT_ZONE_ORIENTATION\s*\(\s*#(\d+)\s*\)\s*;")
_MILLIMETRE = re.compile(rb"\(\s*LENGTH_UNIT\s*\(\s*\)\s*NAMED_UNIT\s*\(\s*\*\s*\)\s*SI_UNIT\s*\(\s*\.MILLI\.\s*,\s*\.METRE\.\s*\)\s*\)")
_METRE = re.compile(rb"\(\s*LENGTH_UNIT\s*\(\s*\)\s*NAMED_UNIT\s*\(\s*\*\s*\)\s*SI_UNIT\s*\(\s*\$\s*,\s*\.METRE\.\s*\)\s*\)")
_MEASURE = re.compile(rb"MEASURE_WITH_UNIT\s*\(.*,\s*#(\d+)\s*\)\s*;", re.S)
_GDT_MAGNITUDE = re.compile(rb"_TOLERANCE\s*\(\s*'(?:[^']|'')*'\s*,\s*'(?:[^']|'')*'\s*,\s*#(\d+)")


def _pmi_records(data: bytes) -> bytes:
    """The PMI records the kernel's writer gets wrong, put right (see above); a file with no PMI
    is left as it is."""
    if b"_TOLERANCE" not in data:
        return data
    start = data.find(b"\nDATA;")
    end = data.find(b"ENDSEC;", start)
    body = data[start:end]
    heads = list(_RECORD.finditer(body))
    spans = {int(match.group(1)): (match.start(), heads[at + 1].start() if at + 1 < len(heads) else len(body))
             for at, match in enumerate(heads)}

    def text(number: int) -> bytes:
        begun, ended = spans[number]
        return body[begun:ended]

    replaced: dict[int, bytes] = {}
    for match in _TOLERANCE_VALUE.finditer(body):
        for bound in (int(match.group(1)), int(match.group(2))):
            found = _UNTYPED_BOUND.search(text(bound)) if bound in spans else None
            if found is None:
                continue
            unit = int(found.group(2))
            if unit not in spans or b"LENGTH_UNIT" not in text(unit):
                continue
            head = text(bound)[:text(bound).index(b"=") + 1]
            replaced[bound] = head + b" LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(%s),#%d);\n" % (found.group(1), unit)
    # A tolerance's magnitude in the writer's default metre: in the file's millimetre instead.
    millimetre = next((number for number in spans if _MILLIMETRE.search(text(number))), None)
    metres = {number for number in spans if _METRE.search(text(number))}
    if millimetre is not None and metres:
        for match in _GDT_MAGNITUDE.finditer(body):
            magnitude = int(match.group(1))
            record = replaced.get(magnitude, text(magnitude)) if magnitude in spans else b""
            found = _MEASURE.search(record)
            if found and int(found.group(1)) in metres:
                replaced[magnitude] = record[:found.start(1) - 1] + b"#%d" % millimetre + record[found.end(1):]
    runouts = [number for number in spans if b"RUNOUT_ZONE_" in text(number)[:64]]
    candidates: dict[int, int] = {}  # a record that may go: its angle, or 0
    for number in runouts:
        record = text(number)
        if _RUNOUT.search(record):
            candidates[number] = 0
        else:
            found = _ORIENTATION.search(record)
            if found:
                candidates[number] = int(found.group(1))
    if not candidates and not replaced:
        return data
    # Who refers to each record that may go (one pass, strings blanked, each as it is written).
    for number in metres:
        candidates.setdefault(number, 0)
    watched = set(candidates) | {angle for angle in candidates.values() if angle}
    referred: dict[int, set[int]] = {number: set() for number in watched}
    for number in spans:
        record = _QUOTED.sub(b"''", replaced.get(number, text(number)))
        for ref in _REFERENCE.findall(record[record.index(b"=") + 1:]):
            if int(ref) in referred:
                referred[int(ref)].add(number)
    dropped = {number for number in candidates if not referred[number]}
    for number in list(dropped):
        angle = candidates[number]
        if angle and angle in spans and b"PLANE_ANGLE_MEASURE_WITH_UNIT" in text(angle) and referred[angle] <= dropped:
            dropped.add(angle)
    if not replaced and not dropped:
        return data
    pieces = [body[:heads[0].start()]]
    pieces.extend(replaced.get(number, text(number)) for number in spans if number not in dropped)
    return data[:start] + b"".join(pieces) + data[end:]


def _default_tolerances(path: Path, stated: list[tuple[str, str]]) -> None:
    """Each part's general tolerance (``pmi.general_tolerance``: its product's name, the standard)
    appended to the written file as CAx-IF's PMI practice states a part's default tolerances, which
    OCCT's writer has no entity for: a ``PROPERTY_DEFINITION`` 'default tolerances' of the part's
    ``PRODUCT_DEFINITION_SHAPE``, its representation's item the 'tolerance class'. Numbered on from
    the file's last record, in the document's order, so the same document writes the same bytes. A
    part is found by its name among the products that hold geometry; two of one name refuse the file."""
    from cadgen.engine.export import ap242

    data = path.read_bytes()
    end = data.rindex(b"ENDSEC;")
    found = ap242.Report(ap242.parse(data.decode("utf-8")))
    # Each part's shape by its product's name: the products that hold faces (an assembly, a part's
    # own name too where it holds one part, holds none).
    held = {product for product, names in found.faces_of().items() if names}
    shapes: dict[str, list[int]] = {}
    for shape in found.of_type("PRODUCT_DEFINITION_SHAPE"):
        if found._product(shape) in held:
            shapes.setdefault(found.product(shape), []).append(shape)
    number = max(int(match.group(1)) for match in _RECORD.finditer(data))
    added = []
    for name, standard in stated:
        if len(shapes.get(name, ())) != 1:
            raise OSError(f"{path.name}: the general tolerance of part {name!r} has no one product of that name to "
                          "be written on: name each part apart")
        text = standard.encode("utf-8")
        added.append(b"#%d = REPRESENTATION_CONTEXT('','default setting');\n" % (number + 1)
                     + b"#%d = DESCRIPTIVE_REPRESENTATION_ITEM('tolerance class','%s');\n" % (number + 2, text)
                     + b"#%d = REPRESENTATION('default tolerances',(#%d),#%d);\n" % (number + 3, number + 2, number + 1)
                     + b"#%d = PROPERTY_DEFINITION('default tolerances','',#%d);\n" % (number + 4, shapes[name][0])
                     + b"#%d = PROPERTY_DEFINITION_REPRESENTATION(#%d,#%d);\n" % (number + 5, number + 4, number + 3))
        number += 5
    path.write_bytes(data[:end] + b"".join(added) + data[end:])


def _quiet(message: Any) -> None:
    """The kernel's translators report to its default messenger, which prints: no printer."""
    if getattr(_quiet, "done", False):
        return
    messenger = message.DefaultMessenger_s()
    printers = messenger.Printers()
    while printers.Size():
        messenger.RemovePrinter(printers.First())
        printers = messenger.Printers()
    _quiet.done = True  # type: ignore[attr-defined]
