"""What a document weighs, as its robot description weighs it: ``inspect``'s masses, so that a part or an assembly
declared to weigh ``grams`` (``declarations.mass``) and the point masses a part declares (``point_mass``) read
the same in ``cad <type> inspect`` as in the MJCF or URDF written of it.

The rule is the description's (``describe``'s **Mass**), here over the engine's facts of each part -- its volume,
mm^3, by its prototype's key -- with no kernel: each instance belongs to its innermost declared node; innermost
first, a node's own solids are scaled by one factor so that they, the point masses on them and its inner nodes'
totals weigh its ``grams``, a solid's weight before the scale its volume at its material's density, or at one
density for all where none of the node's own solids has one (one that has none, among some that do, carries no
mass). An instance below no declared node weighs its volume at its material's density, none without one. A
node the description refuses (its inner nodes and point masses weigh its total or more while it holds solids of
its own; a remainder and no volume to carry it; no solids and a total its inner nodes do not make up) is
refused here in the description's words (``Weights.refused``), and nothing is weighed.

What ``inspect`` says of it (``Weights.said``): the total, how much of it is declared (the declared nodes' grams
and the point masses below none) and how much computed (the solids below no declared node, at their densities),
the declared masses and point masses, and the parts whose solids are scaled to a declared mass.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

__all__ = ["Weights", "declares", "weigh"]


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
    chains: dict[int, list[tuple[int, ...]]] = {}
    names: dict[tuple[int, ...], str] = {}
    paths: dict[tuple[int, ...], str] = {}

    def walk(node: dict[str, Any], at: tuple[int, ...], above: list[tuple[int, ...]], path: str) -> None:
        names[at] = node.get("name") or "the model"
        paths[at] = path
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

    for index, instance in enumerate(instances):
        for name, point in sorted((declared(index).get("pointMasses") or {}).items()):
            found.points[index] = found.points.get(index, 0.0) + float(point["grams"]) * 1e-3
            found.point_masses.append({"part": instance.get("path"), "name": name, "grams": float(point["grams"]),
                                       "at": index})
        found.paths[index] = str(instance.get("path") or "")
        chains.setdefault(index, [()])

    totals: dict[tuple[int, ...], float] = {}
    owner: dict[int, tuple[int, ...]] = {}
    try:
        for index, chain in sorted(chains.items()):
            entries = declared(index).get("mass") or ()
            for up, grams in entries:
                if not 0 <= int(up) < len(chain):
                    raise ValueError(f"part {instances[index].get('path')!r} is declared part of a mass {up} levels "
                                     "above it, which the tree does not hold")
                totals[chain[-1 - int(up)]] = float(grams)
            if entries:
                owner[index] = chain[-1 - int(min(int(up) for up, _grams in entries))]
                found.owners[index] = paths.get(owner[index], "")
        for node in sorted(totals, key=len, reverse=True):
            grams = totals[node]
            said = f"{names.get(node, 'the model')!r}, declared to weigh {grams:g} g,"
            inner = [other for other in totals if len(other) > len(node) and other[:len(node)] == node
                     and not any(len(node) < len(between) < len(other) and other[:len(between)] == between
                                 for between in totals)]
            own = [index for index, held in sorted(owner.items()) if held == node]
            fixed = sum(totals[other] for other in inner)
            fixed += sum(float(point["grams"]) for index in own
                         for point in (declared(index).get("pointMasses") or {}).values())
            weighed = [(index, _density(declared(index))) for index in own]
            uniform = all(density is None for _index, density in weighed)
            solids: list[tuple[int, float, float]] = []
            for index, density in weighed:
                found.scaled.add(index)
                volume = _volume(declared(index), volumes)
                if (density is None and not uniform) or volume is None:
                    found.parts[index] = None
                    continue
                solids.append((index, 1.0 if density is None else density, volume))
            weight = sum(volume * density * 1e-9 for _index, density, volume in solids)  # kg
            rest = (grams - fixed) * 1e-3  # kg
            slack = grams * 1e-12  # kg: a part in 10^9 of the total
            if weight > 0 and rest <= slack:
                raise ValueError(f"{said} holds point masses and inner masses of {fixed:g} g, which leave its own "
                                 "solids nothing to weigh")
            if weight <= 0 and abs(rest) > slack:
                if own:
                    raise ValueError(f"{said} has {grams - fixed:g} g left for its own parts after its point masses "
                                     "and inner masses, and they have no volume to carry it")
                raise ValueError(f"{said} holds inner masses and point masses of {fixed:g} g, and no solid of its own "
                                 "to make up the rest")
            scale = rest / weight if weight > 0 else 0.0
            for index, density, volume in solids:
                found.parts[index] = volume * density * scale * 1e-9
            found.masses.append({"name": names.get(node, "the model"), "path": paths.get(node, ""), "grams": grams})
    except ValueError as error:
        return Weights(owners=found.owners, paths=found.paths, masses=found.masses, point_masses=found.point_masses,
                       refused=str(error))
    found.masses.sort(key=lambda row: row["path"])
    for index in range(len(instances)):
        if index in found.scaled:
            continue
        density, volume = _density(declared(index)), _volume(declared(index), volumes)
        found.parts[index] = None if density is None or volume is None else volume * density * 1e-9
    return found
