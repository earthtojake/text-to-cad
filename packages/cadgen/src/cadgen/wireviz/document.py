"""A :class:`~cadgen.wireviz.design.Harness` as a WireViz YAML document.

The document is the harness: what the CAD Viewer draws (WireViz's own SVG of
it), what ``@harness(bom=)`` and ``cadgen harness bom`` list, and what a person opens in
WireViz. It carries nothing about where it came from -- no script, no time --
and its bytes are a function of the harness alone: keys in a fixed order,
connectors and cables in the order the script declared them, connection sets
in the order it connected them, every string double-quoted (a bare ``NO`` or
``ON`` is a boolean to a YAML reader) and every number written the one way
WireViz reads it (a length always has a decimal point: WireViz's YAML reader
takes ``1e-06`` for text).

One ``connect`` call is one WireViz connection set, split where its rows run
between different connectors or cables (a set names one designator per
column).
"""

from __future__ import annotations

from typing import Any, Sequence

from cadgen.wireviz.design import COMPONENT_KEYS, PART_TEXT, Harness, HarnessError, decimal

__all__ = ["harness_document"]


def _quote(text: str) -> str:
    # Strings reach here checked (cadgen.wireviz.design._text): printable, with "\n" only
    # in multi-line fields, so these three are the only escapes a value can need.
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def _scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return decimal(value)
    if isinstance(value, str):
        return _quote(value)
    raise TypeError(f"no YAML spelling for {value!r}")


def _flow(values: Sequence[Any]) -> str:
    return "[" + ", ".join(_scalar(value) for value in values) + "]"


def _fields(lines: list[str], fields: dict[str, Any], keys: Sequence[str]) -> None:
    """``keys`` of ``fields`` that are present, in that order, four spaces in."""
    for key in keys:
        if key not in fields:
            continue
        value = fields[key]
        if key == "additional_components":
            lines.append("    additional_components:")
            for component in value:
                names = [name for name in COMPONENT_KEYS if name in component]
                for index, name in enumerate(names):
                    lead = "      - " if index == 0 else "        "
                    lines.append(f"{lead}{name}: {_scalar(component[name])}")
        elif isinstance(value, (list, tuple)):
            lines.append(f"    {key}: {_flow(value)}")
        else:
            lines.append(f"    {key}: {_scalar(value)}")


def harness_document(harness: Harness) -> str:
    """The harness as WireViz YAML text, or :class:`HarnessError` naming what stops it."""
    if not isinstance(harness, Harness):
        raise HarnessError(f"a @harness function returns a harness.Harness, got {type(harness).__name__}")
    problems = harness.problems()
    if problems:
        raise HarnessError("the harness cannot be written:\n  " + "\n  ".join(problems))
    lines: list[str] = []
    if harness.title is not None:
        lines += ["metadata:", f"  title: {_quote(harness.title)}"]
    lines.append("connectors:")
    for connector in harness.connectors:
        lines.append(f"  {_quote(connector.name)}:")
        _fields(lines, connector.fields, ("type", "subtype", "color", "style", *PART_TEXT))
        lines.append(f"    pins: {_flow([pin.id for pin in connector.pins])}")
        if any(pin.label for pin in connector.pins):
            lines.append(f"    pinlabels: {_flow([pin.label for pin in connector.pins])}")
        _fields(lines, connector.fields, ("pincolors", "hide_disconnected_pins", "notes", "additional_components"))
    lines.append("cables:")
    for cable in harness.cables:
        lines.append(f"  {_quote(cable.name)}:")
        _fields(lines, cable.fields, ("category", "type", "gauge", "length"))
        lines.append(f"    wirecount: {cable.wirecount}")
        if any(cable.colors):
            lines.append(f"    colors: {_flow(cable.colors)}")
        if cable.wirelabels:
            lines.append(f"    wirelabels: {_flow(cable.wirelabels)}")
        if cable.shield is not None:
            lines.append("    shield: true")
        _fields(lines, cable.fields, ("color", *PART_TEXT, "notes", "additional_components"))
    lines.append("connections:")
    for rows in _connection_sets(harness):
        lines.append("  -")
        first = rows[0]
        columns = []
        if first.start is not None:
            columns.append((first.start.connector.name, [row.start.id for row in rows]))
        columns.append((first.wire.cable.name, [row.wire.id for row in rows]))
        if first.end is not None:
            columns.append((first.end.connector.name, [row.end.id for row in rows]))
        for designator, ids in columns:
            lines.append(f"    - {_quote(designator)}: {_flow(ids)}")
    return "\n".join(lines) + "\n"


def _connection_sets(harness: Harness) -> list[list]:
    """Each ``connect`` call's rows, split into runs that share their connectors and cable."""
    sets: list[list] = []
    runs: dict[tuple, list] = {}
    for connection in harness.connections:
        key = (
            connection.group,
            connection.start.connector.name if connection.start is not None else None,
            connection.wire.cable.name,
            connection.end.connector.name if connection.end is not None else None,
        )
        if key not in runs:
            runs[key] = []
            sets.append(runs[key])
        runs[key].append(connection)
    return sets
