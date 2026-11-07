"""``cad.kicad.route``: copper for the connections an agent names, written into the board an edit has open.

```python
from cad import kicad_pcb
from cad.kicad import route

with kicad_pcb.edit("board.kicad_pcb") as b:
    routed = route(b, [
        {"net": "/CLK", "layers": ["F.Cu"]},                     # every pad of the net joined
        {"net": "+5V", "layers": {"F.Cu": 1, "B.Cu": 3}, "width": 0.5, "vias": 2},
        ("U1.3", "C4.1"),                                         # one connection, pad to pad
    ], layers=["F.Cu", "B.Cu"], via_cost=2)                        # options for every entry without its own
print("\\n".join(routed.human_lines()))
```

The plan is the agent's: what to route, in what order, on which layers, how wide, with what clearance, and
how many vias and at what cost. The router routes only that, each connection round everything already on the
board (copper a person drew, copper an earlier entry routed) by the board's own rules, and moves, changes or
deletes nothing that is there. A connection it cannot route is said by name, with why, and the rest go on, so
the copper that did land is saved with the block. It raises before anything is routed for a plan or a board it
cannot route by: a mistake in the plan (a differential pair in it too), an outline that does not close, a custom
rule it cannot keep or read, a pad primitive it cannot read, a region past its memory; and after only when KiCad
drops what it wrote or a route fails its own exact check (a bug): the edit then saves nothing. The copper is written in one commit into the open board, which the edit saves at the block's end;
nothing else is written anywhere. The search and the pull-tight pass are ``cad.kicad._routing``'s.
"""

from __future__ import annotations

import difflib
import json
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

__all__ = ["Routed", "route"]

#: The keys an entry of the plan, and route's keyword options, may name (law 16: a closed set).
OPTIONS = ("layers", "width", "clearance", "vias", "via_cost")
_KEYS = ("net", "pads", *OPTIONS)
#: What a via costs, in millimetres of track, where the plan does not say.
VIA_COST = 2.0
_HOW = ("route needs a plan: the connections to route, in order -- each a net (\"/CLK\"), a pair of pads "
        "((\"U1.3\", \"C4.1\")) or a dict of either with its options (layers, width, clearance, vias, via_cost) -- "
        "and the copper layers each may use, in the entry or for all of them: "
        "route(b, [{\"net\": \"/CLK\", \"layers\": [\"F.Cu\"]}]) or route(b, [\"/CLK\", (\"U1.3\", \"C4.1\")], layers=[\"F.Cu\", \"B.Cu\"])")


@dataclass(frozen=True)
class Routed:
    """What a ``route`` call did: every connection it was asked for, in the order routed (``connections``: each
    its net, its two ends, routed or not and why not, the copper it added), and the totals. ``ok`` when every
    one is routed."""

    connections: tuple[Any, ...]
    tracks: int
    vias: int
    length: float
    seconds: float

    @property
    def ok(self) -> bool:
        return all(connection.routed for connection in self.connections)

    @property
    def failed(self) -> tuple[Any, ...]:
        return tuple(connection for connection in self.connections if not connection.routed)

    def human_lines(self) -> list[str]:
        """One line per connection, then the totals."""
        lines = [connection.line() for connection in self.connections]
        apart = len(self.failed)
        lines.append(f"{'OK' if not apart else 'NOT ROUTED'}: {len(self.connections) - apart} of {len(self.connections)} "
                     f"connection(s) routed, {self.tracks} segment(s), {self.vias} via(s), {self.length:.1f} mm of "
                     f"track, in {self.seconds:.1f} s" + (f"; {apart} not routed, each said above" if apart else ""))
        return lines


# --- the plan --------------------------------------------------------------------------------------------------


def _number(value: Any, name: str, where: str, low: float = 0.0, whole: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < low:
        kind = ("a whole number" if whole else "a number" if name == "via_cost"
                else "a cost per mm (a number)" if name.startswith("the cost of") else "a number of millimetres")
        raise ValueError(f"{where}: {name} is {kind}, {low:g} or more, not {value!r}")
    if whole and int(value) != value:
        raise ValueError(f"{where}: {name} is a whole number, not {value!r}")
    return float(value)


def _layers(value: Any, copper: Sequence[str], where: str) -> tuple[tuple[str, float], ...]:
    if isinstance(value, str):
        value = [value]
    if isinstance(value, Mapping):
        pairs = [(str(layer), _number(cost, f"the cost of {layer}", where, 0.0)) for layer, cost in value.items()]
        if any(cost <= 0 for _, cost in pairs):
            raise ValueError(f"{where}: each layer's cost per mm is more than 0")
    elif isinstance(value, (list, tuple)):
        pairs = [(str(layer), 1.0) for layer in value]
    else:
        raise ValueError(f"{where}: layers is a list of copper layers (\"F.Cu\", \"B.Cu\") or a mapping of each to its "
                         f"cost per mm, not {value!r}")
    if not pairs:
        raise ValueError(f"{where}: layers names no layer; the board's copper layers are {', '.join(copper)}")
    for layer, _ in pairs:
        if layer not in copper:
            raise ValueError(f"{where}: {layer!r} is not a copper layer of this board; its copper layers are {', '.join(copper)}")
    if len({layer for layer, _ in pairs}) != len(pairs):
        raise ValueError(f"{where}: layers names a layer twice")
    return tuple(pairs)


def _reference(text: Any, where: str) -> str:
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{where}: a pad is named PART.NUMBER (\"U1.3\", or the reference \"#U1.3\"), not {text!r}")
    return text.strip().removeprefix("#")


def _entries(connections: Any, defaults: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The plan as dicts with ``net`` or ``pads`` and the options, the call's defaults filled in."""
    if isinstance(connections, (str, bytes)) or not isinstance(connections, Sequence) or not connections:
        raise ValueError(_HOW)
    entries = []
    for index, entry in enumerate(connections):
        where = f"route: entry {index + 1}"
        if isinstance(entry, str):
            entry = {"net": entry}
        elif isinstance(entry, (tuple, list)):
            if len(entry) != 2:
                raise ValueError(f"{where}: a pair of pads is two pads (\"U1.3\", \"C4.1\"), not {entry!r}")
            entry = {"pads": list(entry)}
        elif not isinstance(entry, Mapping):
            raise ValueError(f"{where}: {entry!r} is neither a net, a pair of pads nor a dict; {_HOW}")
        unknown = sorted(set(entry) - set(_KEYS))
        if unknown:
            raise ValueError(f"{where}: unknown key {', '.join(map(repr, unknown))}; an entry takes "
                             f"{', '.join(_KEYS)} (net or pads, not both)")
        if ("net" in entry) == ("pads" in entry):
            raise ValueError(f"{where}: an entry names a net or a pair of pads, one of the two: {dict(entry)!r}")
        merged = {**{key: value for key, value in defaults.items() if value is not None}, **dict(entry)}
        if merged.get("layers") is None:
            raise ValueError(f"{where} ({entry.get('net') or entry.get('pads')}) has no layers: say which copper layers "
                             f"it may use, in the entry or for every entry (route(..., layers=[...])); {_HOW}")
        entries.append(merged)
    return entries


_POLARITY = {"+": "-", "-": "+", "P": "N", "N": "P"}


def complement(net: str) -> str | None:
    """The net KiCad pairs ``net`` with as a differential pair, by its name, as its DRC engine reads it
    (``DRC_ENGINE::MatchDpSuffix``): from the end, past digits and underscores, a ``+`` or ``-``, ``P`` or ``N``,
    the complement the name with that one swapped (``D+``/``D-``, ``DP0``/``DN0``, ``D_P_1``/``D_N_1``); None when
    the name ends otherwise."""
    for back, char in enumerate(reversed(net)):
        if char.isdigit() and char.isascii() or char == "_":
            continue
        if char in _POLARITY:
            at = len(net) - 1 - back
            return net[:at] + _POLARITY[char] + net[at + 1:]
        return None
    return None


def _wants(entries: Sequence[Mapping[str, Any]], board: Any, rules: Any) -> list[Any]:
    """Each entry worked out against the board and its rules, every value checked before anything is routed."""
    from ._routing.plan import Want

    copper = board.copper
    nets = sorted({pad.net for pad in board.pads if pad.net})
    pads_of: dict[str, list] = {}
    for pad in board.pads:
        if pad.net:
            pads_of.setdefault(pad.net, []).append(pad)
    wants = []
    for index, entry in enumerate(entries):
        where = f"route: entry {index + 1}"
        if "net" in entry:
            net = entry["net"]
            if not isinstance(net, str) or not net.strip():
                raise ValueError(f"{where}: net is a net's name (\"/CLK\", or the reference \"#net:/CLK\"), not {net!r}")
            net = net.strip().removeprefix("#net:")
            if net not in pads_of:
                try:
                    board.pad(net)
                except ValueError:
                    pass
                else:
                    raise ValueError(f"{where}: {net} is a pad, not a net: a connection between two pads is a pair "
                                     f"inside the plan's list, route(b, [(\"{net}\", \"C4.1\")], ...)")
                lowered = {}
                for name in nets:
                    lowered.setdefault(name.lower(), name)
                close = [lowered[name] for name in difflib.get_close_matches(net.lower(), list(lowered), n=3)]
                raise ValueError(f"{where}: no pad of the board is on a net {net!r}"
                                 + (f"; did you mean {', '.join(map(repr, close))}?" if close else ""))
            pads, ends = pads_of[net], None
            where = f"{where} (net {net})"
        else:
            refs = entry["pads"]
            if isinstance(refs, (str, bytes)) or not isinstance(refs, Sequence) or len(refs) != 2:
                raise ValueError(f"{where}: pads is a pair of pads (\"U1.3\", \"C4.1\"), not {refs!r}")
            a, b = (_reference(ref, where) for ref in refs)
            try:
                first, second = board.pad(a), board.pad(b)
            except ValueError as error:
                raise ValueError(f"{where}: {error}") from None
            if first is second:
                raise ValueError(f"{where}: {a} to itself is no connection")
            if not first.net or first.net != second.net:
                raise ValueError(f"{where}: {a} is on {first.net or 'no net'} and {b} on {second.net or 'no net'}: "
                                 "a connection joins two pads of one net")
            net, pads, ends = first.net, [first, second], (a, b)
            where = f"{where} ({a} to {b})"
        partner = complement(net)
        if partner is not None and partner in pads_of:
            raise ValueError(f"{where}: {net} and {partner} are a differential pair to KiCad (its diff_pair_gap and any "
                             "pair rule apply), and route routes no pair: route the pair by hand (layout.md), and leave "
                             "both out of the plan")
        layers = _layers(entry["layers"], copper, where)
        named = {layer for layer, _ in layers}
        off = [pad.ref or f"a pad of {pad.part}" for pad in pads if not named & set(pad.layers)]
        if off:
            raise ValueError(f"{where}: {', '.join(off[:6])}{' and more' if len(off) > 6 else ''} "
                             f"{'is' if len(off) == 1 else 'are'} on no layer it may use "
                             f"({', '.join(layer for layer, _ in layers)}): "
                             "add the layer a pad is on, or route that pad by hand")
        netclass = rules.of(net)
        least = rules.clearance(net)
        width = _number(entry.get("width", netclass.track_width), "width", where)
        if width < rules.min_track_width - 1e-9 or width <= 0:
            raise ValueError(f"{where}: width {width:g} mm is under the board's least track width "
                             f"({rules.min_track_width:g} mm)")
        clearance = _number(entry.get("clearance", least), "clearance", where)
        if clearance < least - 1e-9:
            raise ValueError(f"{where}: clearance {clearance:g} mm is under the {least:g} mm DRC holds {net} to (its "
                             f"netclass {netclass.name} and the board's rules): change the netclass in the .kicad_pro "
                             + ("or the custom rule that sets it " if rules.custom.get("clearance", 0.0) >= least - 1e-9
                                else "") + "to route closer")
        vias = entry.get("vias")
        vias = None if vias is None else int(_number(vias, "vias", where, 0, whole=True))
        via_cost = _number(entry.get("via_cost", VIA_COST), "via_cost", where)
        diameter = max(netclass.via_diameter, rules.min_via_diameter)
        drill = max(netclass.via_drill, rules.min_via_drill)
        annulus = rules.min_annulus
        if len(layers) > 1 and vias != 0 and (diameter - drill) / 2 < annulus - 1e-9:
            raise ValueError(f"{where}: the netclass's via ({diameter:g}/{drill:g} mm) leaves a ring under the board's "
                             f"least {annulus:g} mm: set its via in the .kicad_pro")
        wants.append(Want(net, ends, layers, width, clearance, diameter, drill, vias, via_cost))
    return wants


# --- the board, read and written through KiPy ---------------------------------------------------------------------


def _project_file(board: Any, suffix: str) -> Path | None:
    """The open board's project file ending ``suffix`` (``.kicad_pro``, ``.kicad_dru``), where its project names one."""
    try:
        project = board.document.project
    except AttributeError:
        return None
    if not project.path or not project.name:
        return None
    return Path(project.path) / f"{project.name}{suffix}"


#: KiCad's own default arc error (its ARC_HIGH_DEF), where the project does not set one.
MAX_ERROR = 0.005


def _max_error(board: Any) -> float:
    """KiCad's own arc error, its board setting (``max_error`` in the project's design rules); KiCad's default
    (``MAX_ERROR``) where the project does not say."""
    project = _project_file(board, ".kicad_pro")
    if project is None:
        return MAX_ERROR
    try:
        rules = json.loads(project.read_text(encoding="utf-8"))["board"]["design_settings"]["rules"]
        return max(float(rules.get("max_error", MAX_ERROR)), 0.0)
    except (OSError, KeyError, ValueError):  # no project file, or one that does not set it (JSON's errors: ValueError)
        return MAX_ERROR


def _rules(board: Any, names: Sequence[str]) -> Any:
    """The board's rules as KiCad holds them: each net's class, its minimums, its custom rules (refused by name
    where the router cannot keep them)."""
    from ._routing.rules import NetClass, Rules, custom_limits

    nm = 1e-6

    def netclass(found: Any) -> NetClass:
        # A net of several classes gets KiCad's composite ("Effective for net: ..."): named by its classes.
        name = ", ".join(found.constituents) if found.constituents else found.name
        return NetClass(name, found.clearance * nm, found.track_width * nm, found.via_diameter * nm,
                        found.via_drill * nm)

    nets = [net for net in board.get_nets() if net.name in set(names) or net.name == ""]
    found = board.get_netclass_for_nets(nets) if nets else {}
    classes = {name: netclass(value) for name, value in found.items() if name}
    default = netclass(found[""]) if "" in found else next((c for c in classes.values() if c.name == "Default"), None)
    if default is None:
        raise ValueError("route: KiCad gave no Default netclass (none for copper of no net, nor a net of it): the "
                         "router keeps the class of every net KiCad gives, and guesses none")
    constraints = board.get_design_rules().rules.constraints
    rules = Rules(classes, default, min_clearance=constraints.min_clearance * nm,
                  min_track_width=constraints.min_track_width * nm, edge_clearance=constraints.copper_edge_clearance * nm,
                  hole_clearance=constraints.hole_clearance * nm, hole_to_hole=constraints.hole_to_hole_min * nm,
                  min_via_diameter=constraints.min_via_size * nm, min_via_drill=constraints.min_through_drill * nm,
                  min_annulus=constraints.min_via_annular_width * nm, max_error=_max_error(board))
    try:
        response = board.get_custom_design_rules()
    except Exception as error:  # noqa: BLE001 - KiPy's ApiError: a KiCad without the request gives no custom rules
        if type(error).__name__ != "ApiError":
            raise
        dru = _project_file(board, ".kicad_dru")
        if dru is not None and dru.is_file() and "(rule" in dru.read_text(encoding="utf-8", errors="replace"):
            raise ValueError(f"route keeps the board's custom rules ({dru.name}), and this KiCad cannot give them over "
                             "its API: run the edit with kicode's kicad-cli (unset CAD_KICAD_CLI), or take the rules "
                             "out while routing") from None
        response = None
    custom = []
    if response is not None:
        from kicode.proto.board.board_commands_pb2 import CustomRulesStatus  # pyrefly: ignore[missing-import]
        from kicode.proto.board.board_rules_pb2 import CustomRuleConstraintType  # pyrefly: ignore[missing-import]

        if CustomRulesStatus.Name(response.status) == "CRS_INVALID":
            raise ValueError(f"route: KiCad cannot read the board's custom rules (.kicad_dru: {response.error_text}), "
                             "so the router cannot keep them: fix them first")
        custom = [(rule.name, CustomRuleConstraintType.Name(constraint.type),
                   (constraint.numeric.min * nm) if constraint.numeric is not None else 0.0)
                  for rule in response.rules for constraint in rule.constraints]
    limits, refused = custom_limits(custom)
    if refused:
        raise ValueError(f"route: the board's custom rules {', '.join(map(repr, refused))} disallow items, or assert of "
                         "them, where a condition only KiCad's DRC evaluates holds; the router cannot promise to keep "
                         "them: route by hand there, or take the rules out while routing")
    return rules.with_custom(limits)


def _write(board: Any, tracks: Sequence[Any], vias: Sequence[Any], copper: Sequence[str]) -> None:
    """The new copper into the open board, one commit; every item KiCad kept, or a RuntimeError naming what it
    dropped (the edit then saves nothing)."""
    from kicode.board_types import Track, Via  # pyrefly: ignore[missing-import] - the kicad extra
    from kicode.geometry import Vector2  # pyrefly: ignore[missing-import]
    from kicode.proto.board.board_types_pb2 import BoardLayer  # pyrefly: ignore[missing-import]

    nets = {net.name: net for net in board.get_nets()}
    layer = {name: BoardLayer.Value("BL_" + name.replace(".", "_")) for name in copper}
    items = []
    for new in tracks:
        track = Track()
        track.start, track.end = Vector2.from_xy(*new.start), Vector2.from_xy(*new.end)
        track.width = round(new.width * 1_000_000)
        track.layer = layer[new.layer]
        track.net = nets[new.net]
        items.append(track)
    for new in vias:
        via = Via()
        via.position = Vector2.from_xy(*new.at)
        via.diameter, via.drill_diameter = round(new.diameter * 1_000_000), round(new.drill * 1_000_000)
        via.net = nets[new.net]
        items.append(via)
    if not items:
        return
    commit = board.begin_commit()
    try:
        made = board.create_items(items)
    except BaseException:
        board.drop_commit(commit)
        raise
    board.push_commit(commit, f"Route {len(tracks)} segment(s) and {len(vias)} via(s)")
    if len(made) != len(items):
        raise RuntimeError(f"route: KiCad kept {len(made)} of the {len(items)} items routed; nothing is saved")


def route(board: Any, connections: Sequence[Any] | None = None, *, layers: Any = None, width: float | None = None,
          clearance: float | None = None, vias: int | None = None, via_cost: float | None = None) -> Routed:
    """Route ``connections`` in the board an edit has open (``with kicad_pcb.edit(path) as board``), in the order
    given; see the module's doc. Each connection is a net (``"/CLK"``, ``"#net:/CLK"``), a pair of pads
    (``("U1.3", "C4.1")``) or a dict of either with options; the keyword options apply to every entry that does
    not set its own:

    - ``layers`` (required, here or in each entry): the copper layers it may use, a list, or a mapping of each to
      its cost per millimetre (1 where a list names it);
    - ``width``: the track's, mm (default: the net's netclass track width);
    - ``clearance``: what it keeps from other nets, mm (default, and least: what DRC holds the net to);
    - ``vias``: the most vias each entry may place, all its connections together (default: no limit; 0 for none);
    - ``via_cost``: what a via costs, in mm of track (default 2); the search settles for a path within 1.2 times the
      cheapest, so it trades a via for track at about that cost, not exactly.

    Answers a ``Routed``: each connection's outcome; ``.ok``, ``.failed``, ``.human_lines()``. A connection that
    cannot be routed is said on stderr too. ``ValueError`` for a plan or a board it cannot route by, before anything is
    routed (see the module's doc); ``TypeError`` for a board no edit has open."""
    from ._routing.board import read_copper
    from ._routing.plan import Router

    started = time.monotonic()
    if not callable(getattr(board, "get_as_string", None)):
        raise TypeError("route routes the board a kicad_pcb.edit block has open (with kicad_pcb.edit(path) as b: "
                        f"route(b, plan)), not {type(board).__name__} {board!r:.60}")
    entries = _entries(connections, {"layers": layers, "width": width, "clearance": clearance, "vias": vias,
                                     "via_cost": via_cost})
    copper = read_copper(board.get_as_string())
    if copper.open_outline or not copper.outline:
        ends = [f"({x:g}, {y:g})" for piece in copper.open_outline for x, y in (piece[0], piece[-1])][:4]
        raise ValueError("route keeps copper inside the board's outline, and this board's Edge.Cuts "
                         + (f"does not close: it ends apart at {', '.join(ends)}" if copper.open_outline else "draws none")
                         + "; draw the outline closed first")
    rules = _rules(board, sorted({pad.net for pad in copper.pads if pad.net}))
    router = Router(copper, rules, _wants(entries, copper, rules))
    outcomes = router.run()
    _write(board, router.tracks, router.vias, copper.copper)
    for outcome in outcomes:
        if not outcome.routed:
            print(f"route: {outcome.line()}", file=sys.stderr)
    length = sum(math.dist(track.start, track.end) for track in router.tracks) / 1_000_000
    return Routed(tuple(outcomes), len(router.tracks), len(router.vias), length, time.monotonic() - started)
