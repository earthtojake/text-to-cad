"""A part's holes as a recogniser reads them (``_dfm_cnc``): quiddity's records of the part's holes
(``cad.quiddity``), each measured by this library's own detector (``_dfm_cnc_holes``), which also finds the holes
quiddity does not claim and every hole of a part it was not available for.

**Who says what.** quiddity says which faces are one hole, which of its cylinders is the bore, and what closes it:
``through``, ``flat`` or ``drill_point``. Every figure of the item is still measured here, on those faces, by the
kernel (``_dfm_cnc_holes._describe``): the diameter is the bore cylinder's own radius (quiddity publishes it to five
decimals, and a rule compares to a nanometre), the depth the bore's axis between its two ends, the counterbores the
hole's other cylinders, the countersinks its cones, a drill point's angle its cone's, the opening the end quiddity's
axis comes in from. So an item means what it meant, whichever read the hole; ``recognised_by`` says which
(``quiddity``, or ``cad`` for the detector alone).

**Which records are taken.** A record of the ``holes`` family, ``verified``, of the release these readings were
measured against (``QUIDDITY``), whose bore is a hole as this library means one: its cylinders sweep ``FULL_ROUND``
about the axis together and nothing stands inside them (``_dfm_cnc_holes._cored``). The others are declined, each
said with its reason (``DECLINED``): quiddity calls a channel open along its side a hole, and marks the outer wall
of an annular groove as one it has a better record for.

**One hole, once** (by faces). The detector runs on every part, whatever quiddity found: no hole found is not no
hole there, and quiddity leaves faces unexplained (a hole whose wall is a cone has no record). A hole of the
detector's none of whose faces a taken record names is kept as it is. One that shares a face with a taken record
is that record's hole and is not reported again: the record's faces are the hole's, with the detector's faces of it
that no record names (the plane of a counterbore's step, a seat's cone that a keyway splits: the hole's still, as
the detector reads them), and where two records meet one of the detector's holes those faces go with the first. A
face is one hole's: a record that names a face an earlier one took is declined. ``bottom`` ``unknown`` is no
reading of quiddity's, so there the detector's ray along the axis says what closes the hole.

**What is said of it** (``summary``, the ``holes`` family's ``recognition``): the library and the release that
answered, the holes and the parts by who read them, each part quiddity was not available for with the reason
(``fallbacks``: its holes are the detector's, as they were before quiddity was asked), each record declined, and
each hole the two read differently, with both readings (``disagreements``).
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import numpy as np

from cad.build123d import _dfm_brep as brep
from cad.build123d import _dfm_cnc_holes as detector
from cad.build123d._dfm_cnc_model import Model, unit

__all__ = ["DECLINED", "MOMENTARY", "QUIDDITY", "asked", "holes", "summary"]

#: The release of quiddity whose records are taken: which faces a record names and what its fields mean are that
#: release's, and these readings were measured against it (the extra pins it). A part another release answers
#: for is read by the detector alone (``other_release``), so the code that measures says the release that reads.
QUIDDITY = "0.5.5"
#: Why a record of quiddity's is not taken as a hole: its evidence is not ``verified``; quiddity itself names
#: another record of its own for those walls (``superseded_by``: an annular groove's); its bore does not go round
#: (under ``FULL_ROUND``: a channel open along its side); something stands inside its bore (an annular cavity's
#: outer wall); it names a face an earlier record took.
DECLINED = ("unproved", "superseded", "open", "cored", "shared")
#: The reasons a part has no features that are the moment's or this environment's, not the part's: no environment
#: that holds quiddity could be made, another release answered, the recogniser's process ended or ran out of
#: time. The same check may read the part's holes with quiddity next time, so its report is not ``repeatable``.
MOMENTARY = ("not_installed", "other_release", "stopped", "timed_out")
#: A record's diameter is a cylinder's within this (mm): quiddity publishes five decimals.
NEAR_MM = 1e-3
#: The closings quiddity reads; any other word of its (``unknown``) is no reading.
_BOTTOMS = ("through", "flat", "drill_point")


def asked(parts: Iterable[brep.Part]) -> list[dict[str, Any]]:
    """quiddity's features of each of ``parts`` (``cad.quiddity.features_of``: one recogniser's process for them
    all), in order: a result that says ``available``, or why the part has none (its ``reason``). Nothing raises: a
    call that does is every part's ``failed``."""
    parts = list(parts)
    if not parts:
        return []
    try:
        import cad.quiddity

        found = cad.quiddity.features_of(parts)
        if len(found) != len(parts):
            raise ValueError(f"{len(found)} answers for {len(parts)} parts")
    except Exception as error:  # noqa: BLE001 -- a recogniser that cannot be asked costs no check its holes
        said = {"available": False, "quiddity": None, "reason": "failed",
                "detail": " ".join(f"quiddity could not be asked: {type(error).__name__}: {error}".split())}
        return [dict(said) for _ in parts]
    return [_of_release(result) for result in found]


def _of_release(result: dict[str, Any]) -> dict[str, Any]:
    """``result``, or where another release than ``QUIDDITY`` answered it, why it is not read."""
    version = result.get("quiddity")
    if not result.get("available") or version == QUIDDITY:
        return result
    return {"available": False, "quiddity": version, "reason": "other_release",
            "detail": f"quiddity {version} answered, and its records are read as quiddity {QUIDDITY}'s"}


def holes(model: Model, features: dict[str, Any] | None,
          rotation: np.ndarray | None = None) -> tuple[list[dict[str, Any]], set[int], dict[str, Any] | None]:
    """The part's holes, the ordinals of every face that belongs to one, and what read them (a note for
    ``summary``; None where quiddity was not asked: ``features`` None). ``features`` is quiddity's result for the
    part as it stands in its own coordinates, ``rotation`` what turned the part into ``model``'s frame."""
    found, holed = detector.holes(model)
    if features is None:
        return _by(found, "cad"), holed, None
    note: dict[str, Any] = {"part": model.part.name, "by": "cad", "version": features.get("quiddity"),
                            "reason": None, "detail": None, "declined": [], "disagreements": []}
    if not features.get("available"):
        note.update(reason=str(features.get("reason") or "failed"), detail=str(features.get("detail") or ""))
        return _by(found, "cad"), holed, note
    try:
        merged = _merged(model, found, features, np.eye(3) if rotation is None else np.asarray(rotation), note)
    except Exception as error:  # noqa: BLE001 -- records that do not read against the part cost it no hole
        note.update(reason="failed", declined=[], disagreements=[],
                    detail=f"quiddity's holes could not be read against the part: {type(error).__name__}: {error}")
        return _by(found, "cad"), holed, note
    note["by"] = "quiddity"
    return merged, {face for hole in merged for face in hole["_faces"]}, note


def _by(found: list[dict[str, Any]], who: str) -> list[dict[str, Any]]:
    for hole in found:
        hole["recognised_by"] = who
    return found


def _merged(model: Model, found: list[dict[str, Any]], features: dict[str, Any], rotation: np.ndarray,
            note: dict[str, Any]) -> list[dict[str, Any]]:
    """The holes of the part: each taken record's, measured here, and the detector's (``found``) that no taken
    record meets (the module's **One hole, once**), in the detector's order, a record's hole where the first of
    the detector's it meets stood and one it alone found last."""
    superseded = {record["id"] for record in features["records"]
                  if isinstance(record.get("parameters"), dict) and record["parameters"].get("superseded_by")}
    owner: dict[int, int] = {}
    declined: set[int] = set()
    taken: list[dict[str, Any]] = []
    for record in features["holes"]:
        steps = [step for step in (record["counterbore"], record["spotface"], *record["outer_counterbores"]) if step]
        cones = [*((record["countersink"],) if record["countersink"] else ()), *record["mouth_chamfers"]]
        bore = sorted(face for face in record["faces"] if model.surface(face).kind == "cylinder"
                      and abs(float(model.surface(face).radius) - record["diameter_mm"] / 2.0) <= NEAR_MM)
        claimed = {*record["faces"], *(face for part in (*steps, *cones) for face in part["faces"])}
        if not bore:
            raise ValueError(f"{record['id']} names no cylinder of its diameter, {record['diameter_mm']:g} mm")
        radius = round(float(model.surface(bore[0]).radius), 6)
        why = None
        if record["evidence_status"] != "verified":
            why = "unproved"
        elif record["id"] in superseded:
            why = "superseded"
        elif any(face in owner for face in claimed):
            why = "shared"
        elif not any(hole["_radius"] == radius and set(bore) <= set(hole["_faces"]) for hole in found):
            # no hole of the detector's about this bore: is it one, as the detector means a hole?
            if not _goes_round(model, bore):
                why = "open"
            elif detector._cored(model, set(bore), radius):
                why = "cored"
        if why is not None:
            note["declined"].append({"location": model.ref(bore[0]), "record": record["id"], "reason": why})
            declined |= claimed
            continue
        for face in claimed:
            owner[face] = len(taken)
        taken.append({"record": record, "bore": bore, "radius": radius, "claimed": claimed, "steps": steps,
                      "cones": cones, "met": []})
    firsts: dict[int, int] = {}
    for n, hole in enumerate(found):
        meets = sorted({owner[face] for face in hole["_faces"] if face in owner})
        for k in meets:
            taken[k]["met"].append(n)
        if meets:
            firsts[n] = meets[0]
    placed: dict[int, list[dict[str, Any]]] = {}
    alone: list[dict[str, Any]] = []
    for k, one in enumerate(taken):
        theirs = [found[n] for n in one["met"]]
        group = set(one["claimed"])
        for n in one["met"]:
            if firsts[n] == k:
                group |= {face for face in found[n]["_faces"] if face not in owner}
        if len(theirs) == 1 and group == theirs[0]["_group"]:
            group = theirs[0]["_group"]  # the very set the detector described: its faces in the same order
        record = one["record"]
        said = None
        if record["bottom"] in _BOTTOMS:
            said = {"bottom": record["bottom"], "into": rotation @ np.asarray(record["axis"], dtype=float)}
        named = frozenset({*one["bore"], *(face for step in one["steps"] for face in step["faces"])})
        hole = detector._described(model, group, one["radius"], said, named)
        # a groove the detector set aside from a hole of these stays one, unless the record names its cylinder
        carried = [groove for old in theirs for groove, face in zip(old.get("grooves") or (), old.get("_grooves") or ())
                   if face not in owner]
        if carried:
            hole["grooves"] = [*carried, *(hole.get("grooves") or ())]
        hole["recognised_by"] = "quiddity"
        note["disagreements"].extend(_differences(hole, one, theirs, taken, said is not None))
        if theirs:
            placed.setdefault(one["met"][0], []).append(hole)
        else:
            alone.append(hole)
    merged: list[dict[str, Any]] = []
    for n, hole in enumerate(found):
        if n in placed:
            merged.extend(placed[n])
        elif n not in firsts:
            hole["recognised_by"] = "cad"
            if not declined & set(hole["_faces"]):  # a record declined says so already
                note["disagreements"].append({"location": hole["location"], "field": "hole", "quiddity": False,
                                              "cad": True})
            merged.append(hole)
    return merged + alone


def _goes_round(model: Model, bore: list[int]) -> bool:
    """Whether a bore's cylinders go round its axis: those that overlap along it sweep ``FULL_ROUND`` about it
    together, somewhere along it (a hole a slot splits lengthwise does; a channel open along its side does not,
    in however many stretches it lies along its axis)."""
    axis = unit(model.surface(bore[0]).axis)
    stretches: list[list[float]] = []  # low, high, the sweep of the faces that overlap there
    for low, high, sweep in sorted((*model.extent(face, axis), model.span_rad(face)) for face in bore):
        if stretches and low < stretches[-1][1] - 1e-6:
            stretches[-1][1] = max(stretches[-1][1], high)
            stretches[-1][2] += sweep
        else:
            stretches.append([low, high, sweep])
    return any(sweep >= detector.FULL_ROUND for _low, _high, sweep in stretches)


def _differences(hole: dict[str, Any], one: dict[str, Any], theirs: list[dict[str, Any]],
                 taken: list[dict[str, Any]], read: bool) -> list[dict[str, Any]]:
    """Where a taken record and the detector read one hole differently, each with both readings: ``hole`` (one
    found it and the other did not), ``holes`` (how many each makes of these faces), and of one hole of each:
    ``through``, ``bottom`` (where quiddity read one: ``read``), ``diameter_mm``, ``counterbores`` (their
    diameters) and ``countersinks`` (their cones' count: a seat's and a mouth chamfer's alike)."""
    where = hole["location"]

    def differs(field: str, quiddity: Any, cad: Any) -> dict[str, Any]:
        return {"location": where, "field": field, "quiddity": quiddity, "cad": cad}

    if not theirs:
        return [differs("hole", True, False)]
    records = {k for k, other in enumerate(taken) if set(other["met"]) & set(one["met"])}
    if len(theirs) != 1 or len(records) != 1:
        return [differs("holes", len(records), len({n for k in records for n in taken[k]["met"]}))]
    old = theirs[0]
    found = []
    if read and old["through"] != hole["through"]:
        found.append(differs("through", hole["through"], old["through"]))
    elif read and old["bottom"] != hole["bottom"]:
        found.append(differs("bottom", hole["bottom"], old["bottom"]))
    if old["diameter_mm"] != hole["diameter_mm"]:
        found.append(differs("diameter_mm", hole["diameter_mm"], old["diameter_mm"]))
    stepped = sorted(float(step["diameter_mm"]) for step in one["steps"])
    bored = sorted(float(bore["diameter_mm"]) for bore in old["counterbores"])
    if len(stepped) != len(bored) or any(abs(a - b) > NEAR_MM for a, b in zip(stepped, bored)):
        found.append(differs("counterbores", stepped, bored))
    sunk = sum(len(cone["faces"]) for cone in one["cones"])
    if sunk != len(old["countersinks"]):
        found.append(differs("countersinks", sunk, len(old["countersinks"])))
    return found


def summary(notes: Iterable[dict[str, Any] | None], measured: Iterable[dict[str, Any] | None],
            items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """The ``holes`` family's ``recognition``: ``notes`` each part's note (a copy's its first's), ``measured``
    the notes of the parts measured themselves (each geometry once: the fallbacks, the records declined and the
    disagreements are said once, at the part measured), ``items`` every hole reported."""
    notes = [note for note in notes if note is not None]
    measured = [note for note in measured if note is not None]
    versions = [note["version"] for note in notes if note.get("version")]
    counts = {"quiddity": 0, "cad": 0}
    for item in items:
        counts[item.get("recognised_by") or "cad"] += 1
    fallbacks = [{"part": note["part"], "reason": note["reason"], "detail": note["detail"]}
                 for note in measured if note["reason"] is not None]
    return {"library": "quiddity", "version": versions[0] if versions else None, "holes": counts,
            "parts": {who: sum(1 for note in notes if note["by"] == who) for who in ("quiddity", "cad")},
            "fallbacks": fallbacks,
            "declined": [entry for note in measured for entry in note["declined"]],
            "disagreements": [entry for note in measured for entry in note["disagreements"]],
            "repeatable": not any(entry["reason"] in MOMENTARY for entry in fallbacks)}
