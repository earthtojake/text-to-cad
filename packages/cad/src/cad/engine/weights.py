"""What a document weighs, as its robot description weighs it: ``inspect``'s masses, so that a part or an assembly
declared to weigh ``grams`` (``declarations.mass``) and the point masses a part declares (``point_mass``) read
the same in ``cad <type> inspect`` as in the MJCF or URDF written of it.

The rule is the description's (``describe``'s **Mass**), and it is here once, with no kernel: ``apportion``, over
each instance's density and volume as its caller reads them -- ``describe`` its solids as the kernel measures them,
``weigh`` the engine's facts of each part (its volume, mm^3, by its prototype's key; a density that is no positive
number is none here, where the description refuses it). Each instance belongs to its innermost declared node;
innermost first, a node's own solids are scaled by one factor so that they, the point masses on them and its inner
nodes' totals weigh its ``grams``, a solid's weight before the scale its volume at its material's density, or at one
density for all where none of the node's own solids has one (one that has none, among some that do, carries no
mass). An instance below no declared node weighs its volume at its material's density, none without one. A
node the description refuses (its inner nodes and point masses weigh its total or more while it holds solids of
its own; a remainder and no volume to carry it; no solids and a total its inner nodes do not make up), or a part
declared part of a mass more levels above it than the tree holds, is refused in the description's words
(``Apportioned.refused``, ``Weights.refused``), and nothing is weighed.

What ``inspect`` says of it (``Weights.said``): the total, how much of it is declared (the declared nodes' grams
and the point masses below none) and how much computed (the solids below no declared node, at their densities),
the declared masses and point masses, and the parts whose solids are scaled to a declared mass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable

__all__ = ["Apportioned", "Weights", "apportion", "declares", "weigh"]

Node = tuple[int, ...]  # a node of the tree, by its child indices from the root


@dataclass
class Apportioned:
    """What the rule (the module) decides of a structure's declared masses. ``shares``: each instance below a
    declared mass, the density (kg/m^3, 1.0 where its node weighs its solids at one) and the scale its solids
    weigh at -- ``volume (mm^3) * density * scale * 1e-9`` kg -- or None where it carries none of its node's mass.
    ``owners``: each such instance's innermost declared node; ``totals``: each declared node's grams; ``names`` and
    ``paths``: every node's name (``the model`` for a nameless root) and path in the tree; ``weighed``: the declared
    nodes weighed, innermost first; ``refused``: the description's words for the first node it refuses, which ends
    the weighing (what was weighed before it is kept)."""

    shares: dict[int, tuple[float, float] | None] = field(default_factory=dict)
    owners: dict[int, Node] = field(default_factory=dict)
    totals: dict[Node, float] = field(default_factory=dict)
    names: dict[Node, str] = field(default_factory=dict)
    paths: dict[Node, str] = field(default_factory=dict)
    weighed: list[Node] = field(default_factory=list)
    refused: str | None = None


def apportion(structure: dict[str, Any], density: Callable[[int], float | None], volume: Callable[[int], float | None],
              unweighed: Callable[[str, float, list[int]], None] | None = None) -> Apportioned:
    """The rule (the module) over ``structure``'s declared masses. ``density(index)`` is instance ``index``'s
    material's density (kg/m^3), None where it has none; ``volume(index)`` its solids' volume (mm^3) at unit
    density, None where it has none. Each is asked of the instances below a declared mass alone, a node's in turn,
    innermost first, and the volume only of one whose density lets it carry any of its node's mass, so a caller that
    measures lazily measures nothing more. ``unweighed(said, grams, indices)`` hears, as each node is weighed and
    before any of its volumes is asked, the parts that have no density among its own that have one (``said`` the
    node as a refusal names it: ``'<name>', declared to weigh <grams> g,``)."""
    prototypes, instances = structure.get("prototypes") or [], structure.get("instances") or []
    found = Apportioned()
    chains: dict[int, list[Node]] = {}

    def walk(node: dict[str, Any], at: Node, above: list[Node], path: str) -> None:
        found.names[at] = node.get("name") or "the model"
        found.paths[at] = path
        if "children" in node:
            for position, child in enumerate(node["children"]):
                walk(child, at + (position,), above + [at], f"{path}/{child.get('name') or ''}" if path else
                     str(child.get("name") or ""))
        elif "instance" in node:
            chains[int(node["instance"])] = above + [at]

    tree = structure.get("tree") or {}
    walk(tree, (), [], str(tree.get("name") or ""))

    def declared(index: int) -> dict[str, Any]:
        return prototypes[instances[index]["prototype"]]

    totals, owners = found.totals, found.owners
    for index, chain in sorted(chains.items()):
        entries = declared(index).get("mass") or ()
        for up, grams in entries:
            if not 0 <= int(up) < len(chain):
                name = str(instances[index].get("path") or "").rsplit("/", 1)[-1]
                found.refused = (f"part {name!r} is declared part of a mass {up} levels above it, which the tree "
                                 "does not hold")
                return found
            totals[chain[-1 - int(up)]] = float(grams)
        if entries:
            owners[index] = chain[-1 - int(min(int(up) for up, _grams in entries))]
    for node in sorted(totals, key=len, reverse=True):
        grams = totals[node]
        said = f"{found.names[node]!r}, declared to weigh {grams:g} g,"
        inner = [other for other in totals if len(other) > len(node) and other[:len(node)] == node
                 and not any(len(node) < len(between) < len(other) and other[:len(between)] == between
                             for between in totals)]
        own = [index for index, held in sorted(owners.items()) if held == node]
        fixed = sum(totals[other] for other in inner)
        fixed += sum(float(point["grams"]) for index in own
                     for point in (declared(index).get("pointMasses") or {}).values())
        weighed = [(index, density(index)) for index in own]
        uniform = all(each is None for _index, each in weighed)
        light = [index for index, each in weighed if each is None and not uniform]
        if light and unweighed is not None:
            unweighed(said, grams, light)
        solids: list[tuple[int, float, float]] = []
        for index, each in weighed:
            if each is None and not uniform:
                found.shares[index] = None
                continue
            measured = volume(index)
            if measured is None:
                found.shares[index] = None
                continue
            solids.append((index, 1.0 if each is None else each, measured))
        weight = sum(measured * each * 1e-9 for _index, each, measured in solids)  # kg
        rest = (grams - fixed) * 1e-3  # kg
        slack = grams * 1e-12  # kg: a part in 10^9 of the total
        if weight > 0 and rest <= slack:
            found.refused = (f"{said} holds point masses and inner masses of {fixed:g} g, which leave its own solids "
                             "nothing to weigh")
            return found
        if weight <= 0 and abs(rest) > slack:
            found.refused = (f"{said} has {grams - fixed:g} g left for its own parts after its point masses and "
                             "inner masses, and they have no volume to carry it" if own else
                             f"{said} holds inner masses and point masses of {fixed:g} g, and no solid of its own "
                             "to make up the rest")
            return found
        scale = rest / weight if weight > 0 else 0.0
        for index, each, _measured in solids:
            found.shares[index] = (each, scale)
        found.weighed.append(node)
    return found


@dataclass
class Weights:
    """Each instance's weight (kg), by its index in the structure's ``instances``: its solids' (``parts``, None
    where it carries none) and its point masses' (``points``); the instances whose solids are scaled to a
    declared mass (``scaled``); the declared masses (``masses``: ``{"name", "path", "grams"}`` per node) and point
    masses (``point_masses``: ``{"part", "name", "grams"}`` per instance); and the description's refusal, if
    any (``refused``: then nothing is weighed)."""

    parts: dict[int, float | None] = field(default_factory=dict)
    points: dict[int, float] = field(default_factory=dict)
    scaled: set[int] = field(default_factory=set)
    owners: dict[int, str] = field(default_factory=dict)
    paths: dict[int, str] = field(default_factory=dict)
    masses: list[dict[str, Any]] = field(default_factory=list)
    point_masses: list[dict[str, Any]] = field(default_factory=list)
    refused: str | None = None

    def total(self, instances: Any = None) -> float | None:
        """What ``instances`` (every one by default) weigh in all, kg: None where none of them weighs anything,
        or the description refuses its masses."""
        if self.refused is not None:
            return None
        chosen = list(self.parts) if instances is None else list(instances)
        found = [value for at in chosen for value in (self.parts.get(at), self.points.get(at)) if value is not None]
        return sum(found) if found else None

    def computed(self, instances: Any = None) -> float:
        """What of ``instances``' total is computed, kg: the solids below no declared mass, at their densities."""
        chosen = list(self.parts) if instances is None else list(instances)
        return sum(self.parts.get(at) or 0.0 for at in chosen if at not in self.scaled)

    def weighs(self, at: int) -> bool:
        """Whether instance ``at`` carries any mass: its solids' or a point mass."""
        return self.refused is None and (self.parts.get(at) is not None or bool(self.points.get(at)))

    def said(self, instances: Any = None) -> dict[str, Any]:
        """What ``inspect`` says of ``instances`` (every one by default): ``mass`` (kg, their total, None where the
        description refuses), ``declared`` and ``computed`` (kg: which of it is which), the declared masses that
        hold them (``masses``, each ``{"name", "path", "grams"}``), their point masses (``pointMasses``, each
        ``{"part", "name", "grams"}``) and the parts whose solids are scaled to a declared mass (``scaled``), or
        ``refused``, the description's words."""
        chosen = sorted(self.parts if instances is None else set(instances))
        owners = {self.owners[at] for at in chosen if at in self.owners}
        found: dict[str, Any] = {
            "masses": [row for row in self.masses if instances is None or row["path"] in owners],
            "pointMasses": [row for row in self.point_masses if instances is None or row["at"] in chosen],
        }
        found["pointMasses"] = [{key: value for key, value in row.items() if key != "at"} for row in found["pointMasses"]]
        if self.refused is not None:
            return {"mass": None, "refused": self.refused, **found}
        total = self.total(chosen)
        computed = self.computed(chosen)
        return {"mass": total, "declared": None if total is None else total - computed, "computed": computed, **found,
                "scaled": [self.paths[at] for at in chosen if at in self.scaled]}


def declares(structure: dict[str, Any]) -> bool:
    """Whether any part of the structure declares a mass or point masses (``document.DECLARED``)."""
    return any(prototype.get("mass") or prototype.get("pointMasses") for prototype in structure.get("prototypes") or [])


def _density(prototype: dict[str, Any]) -> float | None:
    density = ((prototype.get("material") or {}).get("material") or {}).get("density")
    if isinstance(density, bool) or not isinstance(density, (int, float)) or not math.isfinite(density) or density <= 0:
        return None
    return float(density)


def _volume(prototype: dict[str, Any], volumes: dict[str, Any]) -> float | None:
    volume = volumes.get(prototype.get("key"))
    return float(volume) if isinstance(volume, (int, float)) and volume > 0 else None


def weigh(structure: dict[str, Any], volumes: dict[str, Any]) -> Weights:
    """The structure's weights (the module), its parts' volumes (mm^3) by prototype key in ``volumes``."""
    prototypes, instances = structure.get("prototypes") or [], structure.get("instances") or []
    found = Weights()

    def declared(index: int) -> dict[str, Any]:
        return prototypes[instances[index]["prototype"]]

    for index, instance in enumerate(instances):
        for name, point in sorted((declared(index).get("pointMasses") or {}).items()):
            found.points[index] = found.points.get(index, 0.0) + float(point["grams"]) * 1e-3
            found.point_masses.append({"part": instance.get("path"), "name": name, "grams": float(point["grams"]),
                                       "at": index})
        found.paths[index] = str(instance.get("path") or "")

    try:
        shared = apportion(structure, lambda index: _density(declared(index)),
                           lambda index: _volume(declared(index), volumes))
    except ValueError as error:  # a declaration that is no number
        return Weights(paths=found.paths, point_masses=found.point_masses, refused=str(error))
    found.owners = {index: shared.paths.get(node, "") for index, node in shared.owners.items()}
    found.masses = [{"name": shared.names.get(node, "the model"), "path": shared.paths.get(node, ""),
                     "grams": shared.totals[node]} for node in shared.weighed]
    if shared.refused is not None:
        return Weights(owners=found.owners, paths=found.paths, masses=found.masses, point_masses=found.point_masses,
                       refused=shared.refused)
    for index, share in shared.shares.items():
        if share is None:
            found.parts[index] = None
            continue
        density, scale = share
        found.parts[index] = _volume(declared(index), volumes) * density * scale * 1e-9
    found.scaled = set(shared.owners)
    found.masses.sort(key=lambda row: row["path"])
    for index in range(len(instances)):
        if index in found.scaled:
            continue
        density, volume = _density(declared(index)), _volume(declared(index), volumes)
        found.parts[index] = None if density is None or volume is None else volume * density * 1e-9
    return found
