"""The DXF emitter: build123d geometry in, deterministic DXF bytes out.

``@dxf`` follows ``@step``'s division of labor — *the function returns content,
the engine owns serialization* (design/dxf-build123d.md). A drawing generator
returns build123d 2D geometry and never touches ezdxf; everything below is the
engine side of that contract.

Three steps, in order:

1. **Normalize.** A bare ``Shape`` is the default ``CUT`` layer; a
   ``{layer: shape}`` dict names its layers explicitly; a labelled ``Compound``
   normalizes identically to the dict. Each layer's shape is exploded into its
   edges and sorted into a CANONICAL order.
2. **Export.** ``build123d.ExportDXF`` receives the layers in sorted name order
   and each layer's edges in sorted content order. ``ExportDXF`` emits one DXF
   entity per edge in the order it is handed them, so entity order in the file
   is entirely ours.
3. **Pin.** ezdxf stamps volatile provenance into every file — two random GUIDs,
   four Julian timestamps and two ``"<ezdxf version> @ <iso timestamp>"`` marker
   values — and populates the CLASSES section by iterating a SET of entity-type
   strings, which puts the emitted class order at the mercy of ``PYTHONHASHSEED``.
   Provenance is pinned to constants and the class registry is sorted, so
   identical geometry is identical bytes across processes, machines and days.
   Anything here that upstream takes away raises :class:`DxfDeterminismError`
   rather than degrading: a silent loss would reach committed fixtures long
   before it reached a test.

Why canonical ordering matters, and what the key is made of
-----------------------------------------------------------
``ExportDXF`` converts ``shape.edges()`` in OCC traversal order. Traversal order
is stable enough to pass a test written today and is NOT a property of the
drawing: an OCP upgrade, a different boolean route to the same profile, or a
kernel-internal reordering silently rewrites every fixture. So the sort key is
derived from GEOMETRIC CONTENT only — the edge's curve kind, then sampled
coordinates along it, then its length — never from traversal position or object
identity. Two runs that produce the same geometry produce the same file even if
the kernel hands the edges over in a different order.

The rounded key comes first and the full-precision key second: rounding absorbs
last-bit noise between routes to the same edge, and the exact tail means ties
can only happen between bitwise-identical edges, whose emitted entities are
identical either way. Nothing falls through to list order.

Off-plane geometry is a hard error, not a warning: a face lifted off Z=0 exports
as its XY shadow, which is silently wrong. Relocate it (``bd.Location((0, 0,
-z)) * face``).

This module owns no ezdxf import of its own — ``ExportDXF`` is the only route to
the format, and ezdxf reaches us as build123d's own dependency.
"""

from __future__ import annotations

import contextlib
import hashlib
import io
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:  # pragma: no cover - typing only; this module must not import OCP eagerly
    from build123d import Edge

# The layer a bare shape lands on. Layers are CAM operations (CUT / ENGRAVE /
# SCORE); a drawing that has only one does not need to name it.
DEFAULT_LAYER = "CUT"

# Sampling positions along an edge for the ordering key and the planarity check.
# Endpoints plus interior samples discriminate every pair of distinct edges that
# share endpoints (an arc and its chord, two arcs of opposite bulge).
_SAMPLE_PARAMETERS = (0.0, 0.25, 0.5, 0.75, 1.0)
_KEY_DECIMALS = 9
# build123d's own off-plane threshold (ExportDXF._convert_point).
_PLANAR_TOLERANCE = 1e-6

# DXF layer names may not contain these; ezdxf would either sanitize or raise
# far from the author's mistake.
_INVALID_LAYER_CHARACTERS = set('<>/\\":;?*|=`')


class DxfContractError(TypeError):
    """A ``@dxf`` function returned something that is not the drawing contract."""


class OffPlaneGeometryError(ValueError):
    """Drawing geometry does not lie in the XY plane."""


class DxfDeterminismError(RuntimeError):
    """The emitter could not guarantee that these bytes are a function of the drawing.

    Raised, never warned. Every mechanism this module uses to fix the output —
    ezdxf's fixed-metadata mode, its CLASSES registry, ExportDXF's document — is
    upstream's to change. Losing one silently would not fail any build; it would
    quietly reintroduce output that rehashes on every rebuild, and the first sign
    would be churning fixtures long after the upgrade that caused it.
    """


# --- normalization -------------------------------------------------------------------


def _shape_type():
    from build123d import Shape

    return Shape


def _validate_layer_name(name: object, *, label: str) -> str:
    if not isinstance(name, str) or not name.strip():
        raise DxfContractError(
            f"{label}: @dxf layer names must be non-empty strings, got {name!r}"
        )
    text = name.strip()
    bad = sorted(_INVALID_LAYER_CHARACTERS.intersection(text))
    if bad:
        raise DxfContractError(
            f"{label}: DXF layer name {text!r} contains reserved character(s) "
            f"{''.join(bad)!r}"
        )
    return text


def _layer_edges(value: object, *, layer: str, label: str) -> tuple["Edge", ...]:
    """Every edge of one layer's geometry, in canonical content order."""
    shape_type = _shape_type()
    shapes: list[Any]
    if isinstance(value, shape_type):
        shapes = [value]
    elif isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        shapes = list(value)
    else:
        raise DxfContractError(
            f"{label}: layer {layer!r} must hold build123d geometry, "
            f"got {type(value).__name__}"
        )
    edges: list[Edge] = []
    for shape in shapes:
        if not isinstance(shape, shape_type):
            raise DxfContractError(
                f"{label}: layer {layer!r} must hold build123d geometry, "
                f"got {type(shape).__name__}"
            )
        edges.extend(shape.edges())
    if not edges:
        raise DxfContractError(f"{label}: layer {layer!r} contains no geometry")
    return tuple(sorted(edges, key=_edge_sort_key))


def _labelled_compound_layers(result: object, *, label: str) -> dict[str, Any] | None:
    """``{child label: child}`` when this Compound's children name layers.

    All labelled is a layer map; none labelled is one drawing that happens to be
    a compound, and lands on the default layer. Anything between is a mistake
    with two silent readings, so it raises: labelling three children of four
    would otherwise merge all four onto ``CUT`` without a word.
    """
    children = tuple(getattr(result, "children", ()) or ())
    if not children:
        return None
    labels = [str(getattr(child, "label", "") or "").strip() for child in children]
    if not any(labels):
        return None
    if not all(labels):
        unlabelled = [index for index, name in enumerate(labels) if not name]
        raise DxfContractError(
            f"{label}: a Compound names DXF layers through its children's labels, "
            f"but {len(unlabelled)} of {len(children)} children are unlabelled "
            f"(at index {', '.join(str(index) for index in unlabelled)}). Label "
            "every child, or return a {layer: shape} dict."
        )
    duplicates = sorted({name for name in labels if labels.count(name) > 1})
    if duplicates:
        raise DxfContractError(
            f"{label}: Compound children repeat the layer label(s) "
            f"{', '.join(repr(name) for name in duplicates)}. One child per layer — "
            "merge them into a single child, or return a {layer: shape} dict."
        )
    return dict(zip(labels, children, strict=True))


def normalize_layers(result: object, *, label: str) -> tuple[tuple[str, tuple["Edge", ...]], ...]:
    """The drawing as ``((layer, edges), ...)``, layers sorted by name.

    Layer order is alphabetical and edge order is content-derived, so the
    emitted file is a pure function of the geometry.
    """
    shape_type = _shape_type()

    if isinstance(result, dict):
        raw = result
    elif isinstance(result, shape_type):
        raw = _labelled_compound_layers(result, label=label) or {DEFAULT_LAYER: result}
    else:
        raise DxfContractError(
            f"{label}: @dxf must return build123d 2D geometry — a shape, or a "
            f"{{layer: shape}} dict — got {type(result).__name__}"
        )
    if not raw:
        raise DxfContractError(f"{label}: @dxf returned no geometry")

    layers: dict[str, tuple[Edge, ...]] = {}
    for name, value in raw.items():
        clean = _validate_layer_name(name, label=label)
        if clean in layers:
            raise DxfContractError(f"{label}: duplicate DXF layer {clean!r}")
        layers[clean] = _layer_edges(value, layer=clean, label=label)
    return tuple((name, layers[name]) for name in sorted(layers))


# --- canonical ordering --------------------------------------------------------------


def _edge_samples(edge: "Edge") -> tuple[tuple[float, float, float], ...]:
    points = []
    for parameter in _SAMPLE_PARAMETERS:
        position = edge.position_at(parameter)
        points.append((float(position.X), float(position.Y), float(position.Z)))
    return tuple(points)


def _edge_sort_key(edge: "Edge") -> tuple:
    """A total order over edges derived from GEOMETRIC CONTENT ONLY.

    ``(curve kind, rounded samples + length, exact samples + length)``. The
    rounded half absorbs last-bit differences between two constructions of the
    same edge; the exact tail means a tie needs two edges agreeing bit-for-bit at
    five sampled points and in length, which for anything but a genuine duplicate
    is pathological. Traversal position and object identity appear nowhere.
    """
    samples = _edge_samples(edge)
    try:
        length = float(edge.length)
    except Exception:  # noqa: BLE001 - a degenerate edge has no length; order it by samples alone
        length = 0.0
    exact = (*[value for point in samples for value in point], length)
    rounded = tuple(round(value, _KEY_DECIMALS) for value in exact)
    return (str(edge.geom_type), rounded, exact)


def _assert_planar(layers: tuple[tuple[str, tuple["Edge", ...]], ...], *, label: str) -> None:
    for layer, edges in layers:
        for edge in edges:
            for _x, _y, z in _edge_samples(edge):
                if abs(z) > _PLANAR_TOLERANCE:
                    raise OffPlaneGeometryError(
                        f"{label}: layer {layer!r} has geometry off the XY plane "
                        f"(a point at z={z:.6g}). A DXF is 2D: exporting this would "
                        "silently write its XY shadow. Relocate the geometry first, "
                        "e.g. `flat = bd.Location((0, 0, -z)) * face`."
                    )


# --- emission ------------------------------------------------------------------------


@contextlib.contextmanager
def _pinned_ezdxf_metadata():
    """ezdxf's fixed-metadata mode, restored afterwards.

    This is the pin: it zeroes ``$FINGERPRINTGUID``/``$VERSIONGUID``, sets the
    four ``$TD*`` Julian timestamps to J2000, and neutralizes both created-by /
    written-by marker values. :func:`_assert_volatile_fields_pinned` then CHECKS
    the emitted text, so if the option is ever renamed or dropped upstream the
    build fails loudly instead of quietly emitting a file that rehashes on every
    rebuild.
    """
    import ezdxf

    options = ezdxf.options
    previous = bool(getattr(options, "write_fixed_meta_data_for_testing", False))
    try:
        options.write_fixed_meta_data_for_testing = True
        yield
    finally:
        options.write_fixed_meta_data_for_testing = previous


def _canonicalize_class_registry(document: object) -> None:
    """Sort the CLASSES section by class name.

    ezdxf populates it during save with ``for dxftype in
    entitydb.dxf_types_in_use()`` — iteration over a SET of strings, so the
    order of the emitted CLASS records follows string hashing and changes with
    ``PYTHONHASHSEED``. That is the whole of the hazard the old pipeline paid
    for with a re-exec of the interpreter: measured here, one drawing wrote two
    different byte streams across five cold runs, differing only in the order of
    the ``LAYOUT`` and ``ACDBPLACEHOLDER`` records.

    Registering the required classes early and then sorting the registry by its
    ``(name, cpp_class_name)`` key fixes the order at content. The save path
    re-runs registration, but ``add_class`` skips keys already present, so this
    order is the one that reaches the file.

    An unrecognized registry shape RAISES rather than skipping. Skipping would
    turn this module's guarantee into a coin flip that only a random hash seed
    could expose — the failure would reach committed fixtures long before it
    reached a test.
    """
    section = getattr(document, "classes", None)
    registry = getattr(section, "classes", None)
    if section is None or not isinstance(registry, dict):
        raise DxfDeterminismError(
            "ezdxf's CLASSES registry is not the mapping this emitter can order "
            f"(got {type(registry).__name__}). Its population iterates a set of "
            "entity-type strings, so without sorting it the written bytes follow "
            "PYTHONHASHSEED. Re-establish a content order for the new shape."
        )
    section.add_required_classes(document.dxfversion)
    ordered = sorted(registry.items())
    registry.clear()
    registry.update(ordered)


_PINNED_GUID = "{00000000-0000-0000-0000-000000000000}"
_PINNED_JULIAN = "2451545.0"
_PINNED_MARKER = "0.0 @ 2000-01-01T00:00:00.000000+00:00"
# header variable -> (group code of its value, the pinned value)
_PINNED_HEADER_FIELDS = {
    "$FINGERPRINTGUID": ("2", _PINNED_GUID),
    "$VERSIONGUID": ("2", _PINNED_GUID),
    "$TDCREATE": ("40", _PINNED_JULIAN),
    "$TDUCREATE": ("40", _PINNED_JULIAN),
    "$TDUPDATE": ("40", _PINNED_JULIAN),
    "$TDUUPDATE": ("40", _PINNED_JULIAN),
}
# "1.4.4 @ 2026-08-30T18:14:31.649023+00:00" — ezdxf's created-by / written-by
# markers, which live as group-1 values on DICTIONARYVAR objects.
_MARKER_RE = re.compile(r"^\d+\.\d+(?:\.\d+)? @ \d{4}-\d{2}-\d{2}T[\d:.+\-]+$")


def _assert_volatile_fields_pinned(text: str, *, label: str) -> None:
    """Verify that nothing volatile survived into the emitted bytes.

    Checks rather than rewrites, deliberately. An earlier version substituted the
    pinned values textually, which corrupted any drawing whose LAYER table held a
    name like ``$TDCREATE``: the matcher took the layer record's own group lines
    for header values and overwrote them. A check has no such blast radius, and
    the failure it reports — "ezdxf stopped honouring its fixed-metadata mode" —
    is one a human must act on anyway.

    A DXF group is two lines, code then value, so each field is verified against
    BOTH its name and its expected group code, and only inside the HEADER section.
    """
    lines = [line.strip() for line in text.split("\n")]
    try:
        header_end = lines.index("ENDSEC")
    except ValueError:
        header_end = len(lines)

    unpinned: list[str] = []
    for index in range(header_end):
        field = _PINNED_HEADER_FIELDS.get(lines[index])
        if field is None or index + 2 >= header_end:
            continue
        code, expected = field
        if lines[index + 1] == code and lines[index + 2] != expected:
            unpinned.append(f"{lines[index]}={lines[index + 2]!r}")

    for index in range(1, len(lines)):
        if lines[index - 1] == "1" and _MARKER_RE.match(lines[index]):
            if lines[index] != _PINNED_MARKER:
                unpinned.append(f"ezdxf marker={lines[index]!r}")

    if unpinned:
        raise DxfDeterminismError(
            f"{label}: ezdxf wrote volatile provenance that should have been pinned "
            f"({', '.join(sorted(unpinned))}). Identical drawings must produce "
            "identical bytes — the drawing's freshness record is a hash of them. "
            "ezdxf's fixed-metadata mode is what pins these; re-establish it."
        )


def emit_dxf(result: object, *, label: str) -> tuple[bytes, object]:
    """Serialize a ``@dxf`` return value. Returns ``(dxf bytes, ezdxf document)``.

    The document comes back so the caller can run drawing validation against the
    same in-memory drawing these bytes were written from.
    """
    from build123d import ExportDXF, Unit

    layers = normalize_layers(result, label=label)
    _assert_planar(layers, label=label)

    buffer = io.BytesIO()
    # The pin spans CONSTRUCTION as well as the write. ezdxf stamps its created-by
    # marker when the document is made and its written-by marker when the document
    # is saved, so pinning only the save leaves the first one carrying a real
    # version and timestamp — which is exactly what the check below caught.
    with _pinned_ezdxf_metadata():
        exporter = ExportDXF(unit=Unit.MM)
        for name, edges in layers:
            if name != "0":
                exporter.add_layer(name)
            # ExportDXF warns to STDOUT for off-plane points. We reject those
            # above, and stdout is a machine-readable channel for several cadgen
            # CLIs, so nothing from this call may reach it.
            with contextlib.redirect_stdout(io.StringIO()):
                exporter.add_shape(list(edges), layer=name)

        # Upstream's own planarity criterion, as a backstop to the sampled check:
        # ExportDXF counts every emitted point outside the XY plane.
        off_plane = getattr(exporter, "_non_planar_point_count", 0)
        if off_plane:
            raise OffPlaneGeometryError(
                f"{label}: {off_plane} exported point(s) lie off the XY plane. A DXF "
                "is 2D: relocate the geometry, e.g. `bd.Location((0, 0, -z)) * face`."
            )

        document = getattr(exporter, "_document", None)
        if document is None:
            raise DxfDeterminismError(
                "build123d's ExportDXF no longer exposes the ezdxf document this "
                "emitter orders and validates. Determinism and drawing validation "
                "both depend on reaching it; re-establish that access."
            )
        _canonicalize_class_registry(document)
        exporter.write(buffer)
    payload = buffer.getvalue()
    _assert_volatile_fields_pinned(payload.decode("utf-8"), label=label)
    return payload, document


def dxf_bytes_hash(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def write_dxf(payload: bytes, output_path: Path) -> str:
    """Write the drawing atomically and return its content hash."""
    from cadgen._internal.atomic_replace import write_bytes_atomic

    write_bytes_atomic(Path(output_path), payload)
    return dxf_bytes_hash(payload)
