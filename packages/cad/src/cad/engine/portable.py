"""A document described portably: a value of another kernel's build, read and made a document here.

A shape handed over (``model(shape, name=...)``, ``api.hand_over``) is made its document in the caller when
the caller runs the engine's kernel -- a build123d shape, documented with OCP 8.0 as a build documents one.
A value of a tool on an OCP build of its own (CadQuery's, 7.9: the registry's portable producers,
``cad.registry.Producer.portable``) cannot be: its process holds no kernel of the engine's. Its producer's
writer describes it instead, as the engine's STEP reader describes a file (``reader.describe``'s header: the
products and the roots) with one BinTools dump of the parts' shapes and the components' locations
(``reader.pack``, format 4: what OCCT 8.0 reads of 7.9's writing), and the daemon's documents worker -- a
kernel process, never the daemon's thread -- reads it here: ``tree`` assembles the build123d tree the header
and the dump make (``reader.unpack``, ``reader.assemble``), and ``document_bytes`` makes the document's bytes
of that tree as the caller would have (``shape_bytes``: ``document.collect``, ``to_xcaf``, ``to_bytes``), so
what the daemon then holds, caches, serves and exports is an ordinary document.

The header's ``format`` is this module's ``FORMAT``, checked before anything is read, and frozen as every
protocol two releases meet over is: a change that an older writer's header would not fit bumps it.
"""

from __future__ import annotations

from typing import Any

__all__ = ["FORMAT", "check", "document_bytes", "shape_bytes", "tree"]

#: The portable description's format: the header's keys and the dump's BinTools version.
FORMAT = "portable/1"


def _count(header: dict[str, Any], key: str) -> int:
    found = header.get(key)
    if not isinstance(found, int) or isinstance(found, bool) or found < 0:
        raise ValueError(f"a portable description counts its {key}")
    return found


def check(header: Any) -> dict[str, Any]:
    """``header`` as a portable description of ``FORMAT``: ``products`` and ``roots`` as the reader describes
    them, every index among them in range, and ``shapes`` and ``locations``, how many of each the dump holds
    (the shapes first). ``ValueError`` naming what is wrong for anything else."""
    if not isinstance(header, dict):
        raise ValueError("a portable description is a JSON object")
    if header.get("format") != FORMAT:
        raise ValueError(f"a portable description of format {header.get('format')!r} is not {FORMAT}")
    products, roots = header.get("products"), header.get("roots")
    if not isinstance(products, list) or not isinstance(roots, list):
        raise ValueError("a portable description names its products and its roots")
    shapes, locations = _count(header, "shapes"), _count(header, "locations")
    if not roots:
        raise ValueError("a portable description places at least one root")

    def component(entry: Any, where: str) -> None:
        if not isinstance(entry, dict) or not isinstance(entry.get("product"), int) or not isinstance(entry.get("location"), int):
            raise ValueError(f"{where} is no component: a product and a location")
        if not 0 <= entry["product"] < len(products):
            raise ValueError(f"{where} names product {entry['product']} of {len(products)}")
        if not 0 <= entry["location"] < locations:
            raise ValueError(f"{where} names location {entry['location']} of {locations}")

    for at, product in enumerate(products):
        if not isinstance(product, dict) or "name" not in product or "assembly" not in product:
            raise ValueError(f"product {at} is no product: a name, and whether it is an assembly")
        if product["assembly"]:
            if not isinstance(product.get("components"), list):
                raise ValueError(f"product {at} is an assembly of no components")
            for index, entry in enumerate(product["components"]):
                component(entry, f"product {at}'s component {index}")
        elif not isinstance(product.get("shape"), int) or not 0 <= product["shape"] < shapes:
            raise ValueError(f"product {at} names shape {product.get('shape')!r} of {shapes}")
    for index, entry in enumerate(roots):
        component(entry, f"root {index}")
    return header


def tree(header: dict[str, Any], data: bytes) -> Any:
    """The build123d tree ``header`` and the dump ``data`` describe (``reader.assemble``): the root node, an
    assembly a ``Compound`` of its placed, named, coloured components."""
    from cad.engine import reader

    found = check(header)
    shapes, locations = reader.unpack(data, int(found["shapes"]))
    if (len(shapes), len(locations)) != (found["shapes"], found["locations"]):
        raise ValueError(f"the dump holds {len(shapes) + len(locations)} shapes and locations, and its description "
                         f"counts {found['shapes']} and {found['locations']}")
    return reader.assemble(found, shapes, locations)


def shape_bytes(shape: Any, name: str) -> bytes:
    """The document's bytes of a shape handed over, named ``name``, made here as a build makes a document
    (``document.collect``, ``to_xcaf``) and serialised (``document.to_bytes``)."""
    from cad.engine import document

    made = document.collect(shape, name)
    for part in made.parts:
        part.shape = document.direct(part.shape)
        part.key = document.geometry_key(part.shape)
    document.merge(made)
    doc = document.to_xcaf(made, document.Kept())
    return document.to_bytes(doc, [part.shape for part in made.parts])


def document_bytes(header: dict[str, Any], data: bytes, name: str) -> bytes:
    """The document's bytes of the portable description ``header`` and ``data`` describe, named ``name``:
    the shape handed over as its own kernel could not write it."""
    return embody(header, data, name)["xbf"]


def embody(header: dict[str, Any], data: bytes, name: str) -> dict[str, Any]:
    """The document made of the portable description ``header`` and ``data`` describe, named ``name``, with
    what a build's report says of a document it made: ``xbf`` (its bytes), ``parts`` (its occurrences) and
    ``facts`` (``delta.facts``: what the daemon says against the last build). A ``closure`` in the header --
    a CadQuery worker's: the script's and its modules' digests and the key made of them (``closure_record``)
    -- is written on the document's main label as a build writes its closure, so the document says what
    made it, and ``cad model inspect`` reads it."""
    from cad.engine import delta, document

    shape = tree(header, data)
    made = document.collect(shape, name)
    for part in made.parts:
        part.shape = document.direct(part.shape)
        part.key = document.geometry_key(part.shape)
    document.merge(made)
    closure = header.get("closure")
    if isinstance(closure, dict):
        made.closure = closure_record(closure, header, name)
    signature = (("portable", header.get("kernel"), header.get("shapes")), tuple(part.key for part in made.parts))
    facts = delta.facts(made, f"portable::{name}", signature)
    doc = document.to_xcaf(made, document.Kept())
    return {"xbf": document.to_bytes(doc, [part.shape for part in made.parts]), "parts": len(made.parts), "facts": facts}


def closure_record(closure: dict[str, Any], header: dict[str, Any], name: str) -> str:
    """The closure a CadQuery model's document carries, as text for its main label (``previous.text``): the
    engine's record shape -- the schema, the engine, the libraries (CadQuery's OCP build among them), the
    platform, the source and the modules by digest -- with the worker's key, which has no bodies and no
    inputs (a CadQuery worker runs the body under its own memo and reads no file the engine tracks)."""
    from pathlib import Path

    from cad.engine import previous

    script = str(closure.get("script") or "")
    folder = Path(script).parent if script else Path.cwd()
    modules = closure.get("modules") if isinstance(closure.get("modules"), dict) else {}
    record = {
        "schema": previous.SCHEMA, "engine": previous._engine(),
        "libs": {**previous._libraries(), "cadquery": str(header.get("kernel") or "cadquery")},
        "platform": previous._platform(),
        "source": {"kind": "script", "path": previous._relative(script, folder) if script else None, "function": name},
        "modules": sorted([previous._relative(str(path), folder), str(digest)] for path, digest in modules.items()),
        "symbols": {}, "inputs": None, "bodies": None, "key": closure.get("key")}
    return previous.text(record)
