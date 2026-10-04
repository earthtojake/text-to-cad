"""An all-link parent's STEP, spliced from its children's saved STEP files (STORE.md §3).

OCCT writes an all-link parent as its own product tree followed by every child's products and
geometry again, and re-exporting all of that costs seconds on a large assembly. The children's
saved files already hold those records, exactly as the writer emitted them. So a build writes the
parent by copying each child's DATA section under its own id prefix, and generates only what the
parent owns: the header, the root and group products, and one instance block per link.

The output keeps OCCT's layout, so its cold compile is OCCT's: the root product named after the
file, every group at the identity, every leaf at its flattened world placement. A translated link
rewrites the point of each leaf placement in its copy to the text OCCT prints for the parent's
leaf translation. The writer emulation must first reproduce each child's own text.

Anything the layout checks do not recognise raises :class:`Ineligible`, and the ordinary writer
runs. That covers:
- a child linked more than once: OCCT shares it, a splice would copy it;
- a child file whose bytes are not the ones its record pins;
- children written by different writers, or in other units;
- a name with a backslash or a control character, which take the writer's own escapes;
- ids that would not fit in 32 bits.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from cadgen.store._compose_readback import pure_translation, written_text


class Ineligible(ValueError):
    """The ordinary writer must produce this parent."""


@dataclass(frozen=True)
class ChildStep:
    """A linked child as its record pins it: the saved STEP and that file's sha256."""

    path: Path
    step_hash: str


# Ids stay below 10**9, inside a signed 32-bit integer, for readers that store them so.
_MAX_ID_DIGITS = 9

_STRING = re.compile(rb"('(?:[^']|'')*')")
_HEADER = re.compile(rb"#(\d+) = ")
_NAUO_KEY = b"NEXT_ASSEMBLY_USAGE_OCCURRENCE('"
_REF = rb"#(\d+)"
_STR = rb"'((?:[^']|'')*)'"
_NAUO = re.compile(rb"#(\d+)=NEXT_ASSEMBLY_USAGE_OCCURRENCE\(" + _STR + b"," + _STR + b"," + _STR + b","
                   + _REF + b"," + _REF + rb",\$\);")
_PDS_PLACEMENT = re.compile(rb"#(\d+)=PRODUCT_DEFINITION_SHAPE\('Placement','Placement of an item',"
                            + _REF + rb"\);")
_IDT = re.compile(rb"#(\d+)=ITEM_DEFINED_TRANSFORMATION\('',''," + _REF + b"," + _REF + rb"\);")
_RR = re.compile(rb"#(\d+)=\(REPRESENTATION_RELATIONSHIP\('',''," + _REF + b"," + _REF
                 + rb"\)REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION\(" + _REF
                 + rb"\)SHAPE_REPRESENTATION_RELATIONSHIP\(\)\);")
_CDSR = re.compile(rb"#(\d+)=CONTEXT_DEPENDENT_SHAPE_REPRESENTATION\(" + _REF + b"," + _REF + rb"\);")
_AXIS = re.compile(rb"#(\d+)=AXIS2_PLACEMENT_3D\(''," + _REF + b"," + _REF + b"," + _REF + rb"\);")
_POINT = re.compile(rb"#(\d+)=CARTESIAN_POINT\('',\(([^,()]+),([^,()]+),([^,()]+)\)\);")
# The root product block the writer opens every file with.
_ROOT = (
    (3, re.compile(rb"#3=SHAPE_DEFINITION_REPRESENTATION\(#4,#10\);")),
    (4, re.compile(rb"#4=PRODUCT_DEFINITION_SHAPE\('','',#5\);")),
    (5, re.compile(rb"#5=PRODUCT_DEFINITION\('design','',#6,#9\);")),
    (6, re.compile(rb"#6=PRODUCT_DEFINITION_FORMATION\('','',#7\);")),
    (7, re.compile(rb"#7=PRODUCT\(" + _STR + b"," + _STR + rb",'',\(#8\)\);")),
    (10, re.compile(rb"#10=SHAPE_REPRESENTATION\('',\(#11(?:,#\d+)*\),#(\d+)\);")),
    (11, re.compile(rb"#11=AXIS2_PLACEMENT_3D\('',#12,#13,#14\);")),
)
# A representation context: the context itself, then its length, angle and solid-angle units
# and its uncertainty, in this order.
_CONTEXT_KINDS = (rb"\(GEOMETRIC_REPRESENTATION_CONTEXT\(3\)", rb"\(LENGTH_UNIT\(\)",
                  rb"\(NAMED_UNIT\(\*\)PLANE_ANGLE_UNIT", rb"\(NAMED_UNIT\(\*\)SI_UNIT\(\$,\.STERADIAN",
                  rb"UNCERTAINTY_MEASURE_WITH_UNIT\(")


def _normalized(record: bytes) -> bytes:
    """One record with the writer's line wrapping removed outside literals."""
    pieces = _STRING.split(record)
    pieces[0::2] = [re.sub(rb"\s+", b"", piece) for piece in pieces[0::2]]
    return b"".join(pieces)


def _renumber(body: bytes, prefix: bytes) -> bytes:
    """Every entity id outside a literal gets ``prefix`` in front of its digits.

    An id never has a leading zero, and every prefix in one file has the same width, so no two
    records collide. Splitting on every quote leaves the literals at the odd positions: an
    escaped '' inside one yields an empty even piece, which holds no '#'.
    """
    pieces = body.split(b"'")
    marked = b"#" + prefix
    pieces[0::2] = [piece.replace(b"#", marked) for piece in pieces[0::2]]
    return b"'".join(pieces)


def _occt_real(value: float) -> bytes:
    """The text OCCT's writer prints for a real (``_compose_readback.written_text``)."""
    value = float(value)
    if not math.isfinite(value):
        raise Ineligible("a placement is not finite")
    return written_text(value).encode()


def _quote(text: str) -> bytes:
    """A name as cadgen's writer spells it, quoted (``step_export.spell_name``): quotes
    doubled, non-ASCII characters as Part 21 directives, a quote OCCT's reader would misread
    as \\X\\27. A backslash or a control character takes the writer's own escapes, which this
    does not emulate."""
    from cadgen.step_export import spell_name

    try:
        return b"'" + spell_name(text) + b"'"
    except ValueError as error:
        raise Ineligible(str(error)) from None


class _StepText:
    """A saved STEP: its header and its DATA records, in increasing id order."""

    def __init__(self, path: Path, step_hash: str):
        self.path = Path(path)
        data = self.path.read_bytes()
        if hashlib.sha256(data).hexdigest() != step_hash:
            raise Ineligible(f"{self.path.name} is not the document its record pins")
        start = data.find(b"\nDATA;\n")
        end = data.rfind(b"\nENDSEC;\nEND-ISO-10303-21;")
        if start < 0 or end < start:
            raise Ineligible(f"{self.path.name} is not a single-DATA-section STEP")
        self.header = data[:start + 1]
        self.body = data[start + 7:end + 1]
        if not self.body.startswith(b"#1 = "):
            raise Ineligible(f"{self.path.name}: its DATA does not start at #1")
        tail = self.body.rfind(b"\n#", 0, len(self.body) - 1)
        last = _HEADER.match(self.body, tail + 1)
        if last is None:
            raise Ineligible(f"{self.path.name}: its last record has no header")
        self.last_id = int(last.group(1))

    def _next_header(self, pos: int) -> tuple[int, int | None]:
        if pos <= 0:
            return 0, 1
        found = pos - 1
        while True:
            found = self.body.find(b"\n#", found)
            if found < 0:
                return len(self.body), None
            match = _HEADER.match(self.body, found + 1)
            if match:
                return found + 1, int(match.group(1))
            found += 1

    def span(self, ident: int) -> tuple[int, int]:
        """Where record ``ident`` lies in the body. Records are written in id order, so this
        bisects on offsets. Every record the splice reads is checked against its full
        expected form, so a match that is really inside a literal fails the check."""
        low, high = 0, len(self.body)
        while high - low > 2048:
            middle = (low + high) // 2
            offset, number = self._next_header(middle)
            if number is not None and number <= ident:
                low = offset
                if number == ident:
                    break
            else:
                high = middle
        offset, number = self._next_header(low)
        while number is not None and number < ident:
            offset, number = self._next_header(offset + 1)
        if number != ident:
            raise Ineligible(f"{self.path.name} has no record #{ident}")
        end, _ = self._next_header(offset + 1)
        return offset, end

    def record(self, ident: int) -> bytes:
        return _normalized(self.body[slice(*self.span(ident))])


class _Child:
    """One child's saved STEP and the product tree its records describe."""

    def __init__(self, step: ChildStep):
        self.text = _StepText(step.path, step.step_hash)
        name = self.text.path.name
        for ident, pattern in _ROOT:
            match = pattern.fullmatch(self.text.record(ident))
            if match is None:
                raise Ineligible(f"{name}: record #{ident} is not the writer's root block")
            if ident == 7:
                self.root_name = match.group(1)
            if ident == 10:
                self.root_context = int(match.group(1))
        self.nauos = self._nauo_entities()

    def _nauo_entities(self) -> list[int]:
        """Every NAUO's entity id in file order. Its instance ids must read 1..k, the order the
        writer's canonical pass leaves. The keyword cannot sit inside a literal, because a quote
        there is doubled, so "('" never follows it."""
        body, name, ids = self.text.body, self.text.path.name, []
        position = body.find(_NAUO_KEY)
        while position >= 0:
            start = position + len(_NAUO_KEY)
            end = body.find(b"'", start)
            if body[start:end] != b"%d" % (len(ids) + 1):
                raise Ineligible(f"{name}: its NAUO ids are not 1..k in file order")
            header = _HEADER.match(body, body.rfind(b"\n", 0, position) + 1)
            if header is None:
                raise Ineligible(f"{name}: a NAUO is not at the start of its record")
            ids.append(int(header.group(1)))
            position = body.find(_NAUO_KEY, end)
        return ids

    def with_nauo_offset(self, body: bytes, offset: int) -> bytes:
        """``body`` with every NAUO instance id moved up by ``offset``."""
        if not offset or not self.nauos:
            return body
        parts, cursor, position = [], 0, body.find(_NAUO_KEY)
        while position >= 0:
            start = position + len(_NAUO_KEY)
            end = body.find(b"'", start)
            parts += [body[cursor:start], b"%d" % (int(body[start:end]) + offset)]
            cursor = end
            position = body.find(_NAUO_KEY, end)
        parts.append(body[cursor:])
        return b"".join(parts)

    def leaf_points(self) -> dict[str, tuple[int, tuple[bytes, bytes, bytes]]]:
        """Each leaf's id below this child's root (o1.2.1 ...) mapped to the CARTESIAN_POINT of
        its placement and that point's three coordinate texts.

        Each NAUO is the fifth record of the writer's fixed instance block: CDSR, relationship
        with transformation, IDT, placement PDS, NAUO. Every reference in it is checked rather
        than assumed."""
        name = self.text.path.name
        children: dict[int, list[tuple[int, int]]] = {}
        points: dict[int, tuple[int, tuple[bytes, bytes, bytes]]] = {}
        for nauo in self.nauos:
            match = _NAUO.fullmatch(self.text.record(nauo))
            if match is None:
                raise Ineligible(f"{name}: #{nauo} is not a plain NAUO")
            relating, related = int(match.group(5)), int(match.group(6))
            pds = _PDS_PLACEMENT.fullmatch(self.text.record(nauo - 1))
            idt = _IDT.fullmatch(self.text.record(nauo - 2))
            rr = _RR.fullmatch(self.text.record(nauo - 3))
            cdsr = _CDSR.fullmatch(self.text.record(nauo - 4))
            if (pds is None or int(pds.group(2)) != nauo or idt is None or rr is None
                    or int(rr.group(4)) != nauo - 2 or cdsr is None
                    or (int(cdsr.group(2)), int(cdsr.group(3))) != (nauo - 3, nauo - 1)):
                raise Ineligible(f"{name}: NAUO #{nauo} is not in the writer's instance block")
            axis = _AXIS.fullmatch(self.text.record(int(idt.group(3))))
            point = _POINT.fullmatch(self.text.record(int(axis.group(2)))) if axis else None
            if point is None:
                raise Ineligible(f"{name}: NAUO #{nauo} is not placed by a plain point")
            children.setdefault(relating, []).append((nauo, related))
            points[nauo] = (int(point.group(1)), (point.group(2), point.group(3), point.group(4)))
        leaves: dict[str, tuple[int, tuple[bytes, bytes, bytes]]] = {}

        def walk(definition: int, path: str) -> None:
            for index, (nauo, related) in enumerate(children.get(definition, []), start=1):
                if related in children:
                    walk(related, f"{path}.{index}")
                else:
                    leaves[f"{path}.{index}"] = points[nauo]

        walk(5, "o1")
        if len({point for point, _texts in leaves.values()}) != len(leaves):
            raise Ineligible(f"{name}: two leaf placements share a point")
        if len(leaves) + len(set(children) - {5}) != len(self.nauos):
            raise Ineligible(f"{name}: its product tree is not one tree under #5")
        return leaves


def _structure(tree: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The parent's own grouping, from its authored tree: groups of links, nothing else."""
    if tree.get("occurrences"):
        raise Ineligible("the parent has geometry of its own")
    rows = {link["id"]: link for link in tree.get("links") or []}

    def convert(node: Mapping[str, Any]) -> dict[str, Any]:
        if node.get("nodeType") == "link":
            return {"link": rows[node["id"]]}
        if node.get("nodeType") not in ("assembly", "subassembly") or not node.get("children"):
            raise Ineligible(f"node {node.get('id')} is not a group of links")
        return {"group": str(node.get("name") or ""), "children": [convert(child) for child in node["children"]]}

    return convert(tree["assembly"]["root"])["children"]


def _translation(transform: Any) -> tuple[float, float, float] | None:
    if not pure_translation(transform):
        return None
    return float(transform[3]), float(transform[7]), float(transform[11])


def _header(child: _Child, name: bytes) -> bytes:
    """The child's header, on one line per entity, with FILE_NAME naming ``name``."""
    text = _normalized(child.text.header)
    if not text.startswith(b"ISO-10303-21;HEADER;") or not text.endswith(b"ENDSEC;"):
        raise Ineligible(f"{child.text.path.name} has an unexpected header")
    pieces = _STRING.split(text[len(b"ISO-10303-21;HEADER;"):-len(b"ENDSEC;")])
    for index in range(0, len(pieces) - 1, 2):
        if pieces[index].endswith(b"FILE_NAME("):
            pieces[index + 1] = name
    return b"".join(pieces)


def splice_step(
    *,
    out: Path,
    root_name: str,
    tree: Mapping[str, Any],
    descriptor: Mapping[str, Any],
    children: Mapping[str, ChildStep],
) -> str:
    """Write ``out`` for the all-link parent whose authored tree is ``tree`` and return its sha256.

    Arguments:
    - ``descriptor``: the flattened descriptor the writer would be given, with leaf world
      transforms.
    - ``children``: each linked child's tree hash mapped to the saved STEP its record pins.

    Raises :class:`Ineligible` before anything is written whenever the ordinary writer must run.
    """
    from cadgen.store.trees import flatten

    nodes = _structure(tree)
    links: list[Mapping[str, Any]] = []

    def collect(items: list[dict[str, Any]]) -> None:
        for item in items:
            if "link" in item:
                links.append(item["link"])
            else:
                collect(item["children"])

    collect(nodes)
    if not links:
        raise Ineligible("the parent places nothing")
    loaded: dict[str, _Child] = {}
    for link in links:
        if _translation(link["transform"]) is None or link.get("color") is not None:
            raise Ineligible(f"link {link.get('name')!r} is not an uncoloured pure translation")
        child_tree = str(link["tree"])
        if child_tree in loaded:
            raise Ineligible(f"{children[child_tree].path.name} is linked more than once")
        if child_tree not in children:
            raise Ineligible(f"link {link.get('name')!r} has no saved document pinned")
        loaded[child_tree] = _Child(children[child_tree])

    # A fixed-width prefix in front of each child's own digits: the first for the parent's own
    # records, then one per link.
    width = 2
    while 10 ** (width - 1) + len(links) >= 10 ** width:
        width += 1
    if width + max(len(str(child.text.last_id)) for child in loaded.values()) > _MAX_ID_DIGITS:
        raise Ineligible("the spliced ids would not fit in 32 bits")
    own = str(10 ** (width - 1)).encode()
    prefixes = {str(link["tree"]): str(10 ** (width - 1) + 1 + index).encode() for index, link in enumerate(links)}

    # One writer and one kernel wrote every child; the parent takes their header.
    template = loaded[str(links[0]["tree"])]
    reference = _header(template, b"''")
    for child in loaded.values():
        if _header(child, b"''") != reference:
            raise Ineligible(f"{child.text.path.name} was written by another writer or kernel")
    header = (b"ISO-10303-21;\nHEADER;\n"
              + re.sub(rb";(FILE_NAME|FILE_SCHEMA)", rb";\n\1", _header(template, _quote(root_name)))
              + b"\nENDSEC;\n")

    # Every product of this writer carries one representation context. The parent's take the
    # first child's root context: units are checked equal across children. The uncertainty is
    # the writer's per-file tolerance and governs only the parent's placements.
    def context_of(child: _Child) -> list[bytes]:
        records = []
        for offset, kind in enumerate(_CONTEXT_KINDS):
            ident = child.root_context + offset
            if not re.match(rb"#%d=" % ident + kind, child.text.record(ident)):
                raise Ineligible(f"{child.text.path.name}: root context #{ident} is not the writer's")
            records.append(child.text.body[slice(*child.text.span(ident))])
        return records

    def units(records: list[bytes]) -> list[bytes]:
        shapes = []
        for record in records:
            text = _normalized(record).split(b"=", 1)[1]
            shapes.append(re.sub(rb"LENGTH_MEASURE\([^)]*\)", b"LENGTH_MEASURE()", re.sub(rb"#\d+", b"#", text)))
        return shapes

    context_records = context_of(template)
    for child in loaded.values():
        if units(context_of(child)) != units(context_records):
            raise Ineligible(f"{child.text.path.name} is in other units")

    # A translated link moves its leaves: each leaf's point becomes the text the writer prints
    # for the parent's leaf translation, once the emulation reproduces the child's own text.
    world = {row["id"]: row["transform"] for row in descriptor.get("occurrences") or []}
    edits: dict[str, dict[int, bytes]] = {}
    for link in links:
        child_tree, link_id = str(link["tree"]), str(link["id"])
        name = link.get("name") or ""
        edit = edits.setdefault(child_tree, {})
        # The child's root product takes the link's name, as the writer names that group.
        if loaded[child_tree].root_name != _quote(name)[1:-1]:
            edit[7] = b"#7 = PRODUCT(" + _quote(name) + b"," + _quote(name) + b",'',(#8));\n"
        if _translation(link["transform"]) == (0.0, 0.0, 0.0):
            continue
        own_world = {row["id"]: row["transform"] for row in flatten(child_tree).get("occurrences") or []}
        for leaf, (point, texts) in loaded[child_tree].leaf_points().items():
            child_transform = own_world.get(leaf)
            parent_transform = world.get(link_id if leaf == "o1" else f"{link_id}{leaf[2:]}")
            if child_transform is None or parent_transform is None:
                raise Ineligible(f"leaf {leaf} of {name!r} is not in both descriptors")
            if tuple(_occt_real(child_transform[index]) for index in (3, 7, 11)) != texts:
                raise Ineligible(f"the writer emulation does not reproduce {name!r} leaf {leaf}")
            coordinates = b",".join(_occt_real(parent_transform[index]) for index in (3, 7, 11))
            edit[point] = b"#%d = CARTESIAN_POINT('',(%s));\n" % (point, coordinates)

    counter = 0

    def new() -> bytes:
        nonlocal counter
        counter += 1
        return b"#" + own + str(counter).encode()

    application, context = new(), new()

    def product_block(name: str, count: int) -> dict[str, Any]:
        """The writer's block for an assembly product whose ``count`` children all sit at the
        identity: SDR, PDS, PD, PDF, PRODUCT, PC, PDC, SR with its placements, then the
        context with its units and uncertainty. Its PRPC follows its NAUO."""
        ids = {key: new() for key in ("sdr", "pds", "pd", "pdf", "product", "pc", "pdc", "sr")}
        placements = [(new(), new(), new(), new()) for _ in range(count + 1)]
        local = {template.root_context + offset: new() for offset in range(len(_CONTEXT_KINDS))}
        ids["origin"] = placements[0][0]
        ids["placements"] = [placement[0] for placement in placements[1:]]
        label = _quote(name)
        lines = [
            ids["sdr"] + b" = SHAPE_DEFINITION_REPRESENTATION(" + ids["pds"] + b"," + ids["sr"] + b");\n",
            ids["pds"] + b" = PRODUCT_DEFINITION_SHAPE(''," + b"''," + ids["pd"] + b");\n",
            ids["pd"] + b" = PRODUCT_DEFINITION('design',''," + ids["pdf"] + b"," + ids["pdc"] + b");\n",
            ids["pdf"] + b" = PRODUCT_DEFINITION_FORMATION(''," + b"''," + ids["product"] + b");\n",
            ids["product"] + b" = PRODUCT(" + label + b"," + label + b",'',(" + ids["pc"] + b"));\n",
            ids["pc"] + b" = PRODUCT_CONTEXT(''," + context + b",'mechanical');\n",
            ids["pdc"] + b" = PRODUCT_DEFINITION_CONTEXT('part definition'," + context + b",'design');\n",
            ids["sr"] + b" = SHAPE_REPRESENTATION('',(" + b",".join(p[0] for p in placements) + b"),"
            + local[template.root_context] + b");\n",
        ]
        for axis, point, z_axis, x_axis in placements:
            lines += [axis + b" = AXIS2_PLACEMENT_3D(''," + point + b"," + z_axis + b"," + x_axis + b");\n",
                      point + b" = CARTESIAN_POINT('',(0.,0.,0.));\n",
                      z_axis + b" = DIRECTION('',(0.,0.,1.));\n",
                      x_axis + b" = DIRECTION('',(1.,0.,0.));\n"]

        def remap(match: re.Match) -> bytes:
            ident = int(match.group(1))
            if ident not in local:
                raise Ineligible("the root context refers outside its block")
            return local[ident]

        for record in context_records:
            pieces = _STRING.split(record)
            pieces[0::2] = [re.sub(rb"#(\d+)", remap, piece) for piece in pieces[0::2]]
            lines.append(b"".join(pieces))
        ids["lines"] = b"".join(lines)
        return ids

    nauo_count = 0

    def instance(parent: dict[str, Any], index: int, child_definition: bytes, child_shape: bytes, name: str) -> bytes:
        """The writer's instance block: CDSR, relationship with transformation, IDT, placement
        PDS, NAUO."""
        nonlocal nauo_count
        nauo_count += 1
        cdsr, relationship, transformation, shape, usage = new(), new(), new(), new(), new()
        return b"".join([
            cdsr + b" = CONTEXT_DEPENDENT_SHAPE_REPRESENTATION(" + relationship + b"," + shape + b");\n",
            relationship + b" = ( REPRESENTATION_RELATIONSHIP(''," + b"''," + child_shape + b"," + parent["sr"]
            + b") REPRESENTATION_RELATIONSHIP_WITH_TRANSFORMATION(" + transformation
            + b") SHAPE_REPRESENTATION_RELATIONSHIP() );\n",
            transformation + b" = ITEM_DEFINED_TRANSFORMATION(''," + b"''," + parent["origin"] + b","
            + parent["placements"][index] + b");\n",
            shape + b" = PRODUCT_DEFINITION_SHAPE('Placement','Placement of an item'," + usage + b");\n",
            usage + b" = NEXT_ASSEMBLY_USAGE_OCCURRENCE('%d'," % nauo_count + _quote(name) + b",''," + parent["pd"]
            + b"," + child_definition + b",$);\n",
        ])

    # ``out`` is the build's private staged document: publication moves it into place.
    digest = hashlib.sha256()
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(out, "wb") as stream:
            def write(chunk: bytes) -> None:
                digest.update(chunk)
                stream.write(chunk)

            write(header + b"DATA;\n")
            write(application + b" = APPLICATION_PROTOCOL_DEFINITION('international standard',"
                  b"'automotive_design',2000," + context + b");\n")
            write(context + b" = APPLICATION_CONTEXT('core data for automotive mechanical design processes');\n")

            def emit_link(parent: dict[str, Any], index: int, link: Mapping[str, Any]) -> None:
                nonlocal nauo_count
                child_tree = str(link["tree"])
                child, prefix = loaded[child_tree], prefixes[child_tree]
                marked = b"#" + prefix
                write(instance(parent, index, marked + b"5", marked + b"10", str(link.get("name") or "")))
                body = child.text.body
                replacements = edits.get(child_tree) or {}
                if replacements:
                    parts, cursor = [], 0
                    for ident in sorted(replacements):
                        start, end = child.text.span(ident)
                        parts += [body[cursor:start], replacements[ident]]
                        cursor = end
                    parts.append(body[cursor:])
                    body = b"".join(parts)
                # NAUO instance ids run 1..N in file order: this link's, then its child's own.
                body = child.with_nauo_offset(body, nauo_count)
                nauo_count += len(child.nauos)
                write(_renumber(body, prefix))

            def emit_group(items: list[dict[str, Any]], name: str, parent: dict[str, Any] | None,
                           index: int | None) -> None:
                block = product_block(name, len(items))
                write(block["lines"])
                if parent is not None:
                    write(instance(parent, index, block["pd"], block["sr"], name))
                write(new() + b" = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(" + block["product"] + b"));\n")
                for position, item in enumerate(items):
                    if "link" in item:
                        emit_link(block, position, item["link"])
                    else:
                        emit_group(item["children"], item["group"], block, position)

            emit_group(nodes, root_name, None, None)
            write(b"ENDSEC;\nEND-ISO-10303-21;\n")
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    return digest.hexdigest()
