"""STEP: AP242, written by the kernel's XCAF writer from the document.

The assembly with its instance and product names, colours per part and per painted face,
material names and densities (the writer's material mode), and the element names on face
and edge sub-shape labels (``write.stepcaf.subshapes.name``). A document as built is
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
2.3-million-entity car took half an hour so).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

__all__ = ["SCHEMA", "WRITTEN_STAMP", "write"]

SCHEMA = "AP242DIS"
# FILE_NAME's time_stamp: the date the xbf's header holds (``document.WRITTEN_DATE``), whatever
# the clock.
WRITTEN_STAMP = "2000-01-01T00:00:00"


def write(view: Any, path: Path) -> None:
    doc = view.source.xcaf
    if doc is None:
        from cadgen.engine import document
        from cadgen.engine.export.tree import tree_of

        doc = document.to_xcaf(tree_of(view))
    write_document(doc, path)


def write_document(doc: Any, path: Path) -> None:
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.Interface import Interface_Static
    from OCP.Message import Message
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs

    from cadgen.engine.document import _XCAF_LOCK

    with _XCAF_LOCK:
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
        if not writer.Transfer(doc, STEPControl_AsIs):
            raise OSError(f"could not write {path}")
        _stamp(writer.ChangeWriter().Model())
        if writer.Write(str(path)) != IFSelect_RetDone:
            raise OSError(f"could not write {path}")
    _settle(Path(path))


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
# An assembly occurrence's id: its record's first argument, a quoted number.
_OCCURRENCE = re.compile(rb"(NEXT_ASSEMBLY_USAGE_OCCURRENCE\s*\(\s*')\d*'")


def _settle(path: Path) -> None:
    """The written file made a function of the document alone (see the module docstring): its
    presentations in the document's order (``_presentations``) and its assembly occurrences
    numbered as a fresh process numbers them (``_occurrences``); written again when either
    changed it."""
    data = path.read_bytes()
    settled = _occurrences(_presentations(data))
    if settled != data:
        path.write_bytes(settled)


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
        pieces, at = [], 0
        for quoted in _QUOTED.finditer(text):
            pieces.append(_REFERENCE.sub(renumbered, text[at:quoted.start()]))
            pieces.append(quoted.group(0))
            at = quoted.end()
        pieces.append(_REFERENCE.sub(renumbered, text[at:]))
        return b"".join(pieces)

    settled = b"".join(rewrite(records[number]) for number in sorted(placed, key=placed.__getitem__))
    return data[:start] + settled + data[end:]


def _occurrences(data: bytes) -> bytes:
    """Each assembly occurrence's id (``NEXT_ASSEMBLY_USAGE_OCCURRENCE``'s first argument) its
    place among them in the file, from 1: the kernel numbers them from a counter of the
    process's, on from every STEP it wrote before, so a warm worker's file would number them on
    from its earlier exports where a fresh process's starts at 1. The file's order is the
    transfer's, which is the document's, so the numbers are the same in every process."""
    counter = iter(range(1, 1 << 62))
    return _OCCURRENCE.sub(lambda match: match.group(1) + b"%d'" % next(counter), data)


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
