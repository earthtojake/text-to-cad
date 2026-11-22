"""A part's holes with a recogniser's reading of what closes them (``_dfm_cnc``): the detector's holes
(``_dfm_cnc_holes``), each matched to quiddity's record of the same hole (``cad.quiddity``) where there is one,
and corrected by it in the one place the detector is known to misread, where the kernel bears the record out.

**What a record changes.** The detector reads a hole through or blind by a ray each way along its axis, and
takes a floor that is no face of the hole's own -- a plane wider than the bore, one a round joins to the wall,
the floor of a recess with another hole in it -- for no floor at all: such a hole reads through. quiddity reads
those blind. So where the detector reads a hole through and the record of that same hole says it is closed, and
a ray into the hole along the record's axis meets a face of the part within a diameter of where the hole's
cylinders end, the hole is blind: its opening the end the record's axis comes in from, its floor the face the ray
meets (``flat`` where the record says flat and that face is a plane, ``drill_point`` where it says a point and it
is a cone, ``other`` where it says flat and it is neither: a ball nose), described again on the same faces
(``_dfm_cnc_holes._describe``). Nothing else of a hole is the record's to say: its faces, its bore and its
diameter, its depths, counterbores, countersinks and grooves are the detector's, measured on the kernel, as
they were. ``recognised_by`` says ``quiddity`` for a hole whose record was taken, corrected or not, and ``cad``
for one the detector reads alone.

**Its mouth follows.** What a wall that cuts a hole's mouth makes of it (``_dfm_cnc_holes.mouths``) is read after
this, of each hole as it stands here, at the ends it opens by. A hole the rays read through opens by both, and an
opening its wall has at the far one -- an undercut on its floor -- is a cut mouth to them; closed by its record
it opens by one end, so a wall is looked for across that mouth alone, and the other is an opening below the
mouth, no cut. The family lists first the holes that reach furthest past a wall, so its order can follow too.
An ``open`` mouth is a hole's whose wall goes round ``FULL_ROUND`` or more, its record taken as any other's; the
``open`` a record is declined by is a bore that does not go round, no hole here.

**Which records are taken.** One the kernel's own geometry does not contradict, and no other; where it is not
taken the detector's reading of those faces stands, exactly as it was, and the record is said declined with the
reason (``DECLINED``):

- the record itself: ``unproved`` (its evidence is not ``verified``), ``superseded`` (quiddity names another
  record of its own for those walls: an annular groove's);
- no hole of the detector's is about its faces: ``open`` (its bore does not go round, under ``FULL_ROUND``:
  quiddity calls a channel open along its side a hole), ``cored`` (something stands inside its bore), else
  ``unmatched``;
- it is not one hole of the detector's, whole: ``spans`` (its faces lie in several of the detector's holes: the
  two stretches of a hole another hole crosses are two holes here, each as deep as a drill goes in it),
  ``beyond`` (it names a face that hole does not hold), ``shared`` (another record, taken or not, names a face
  of that hole: a hole is handed to a record whole or not at all), ``other_bore`` (its bore is not that hole's
  narrowest full cylinder: a counterbore is never narrower than its bore);
- the rays contradict what it says closes the hole (``contradicted``): it says through and a ray meets the
  hole's own floor; it says closed and the ray into the hole leaves the part, or meets nothing within a diameter
  of the hole's end, or the hole's own floor is at the end it calls the opening; it says a point and the floor is
  no cone, or flat and the floor is a cone.

``bottom`` ``unknown`` is no reading of quiddity's: the record is taken and the detector's reading stands.

**No hole found is not no hole there.** The detector runs on every part, whatever quiddity found, and a hole of
its own that no record names is kept as it is: quiddity leaves faces unexplained, and a bore sealed inside the
part is an interior void to it.

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

__all__ = ["DECLINED", "QUIDDITY", "REPEATABLE", "asked", "holes", "summary"]

#: The release of quiddity whose records are taken: which faces a record names and what its fields mean are that
#: release's, and these readings were measured against it (the extra pins it). A part another release answers
#: for is read by the detector alone (``other_release``), so the code that measures says the release that reads.
QUIDDITY = "0.5.5"
#: Why a record of quiddity's is not taken (the module's **Which records are taken**).
DECLINED = ("unproved", "superseded", "open", "cored", "unmatched", "spans", "beyond", "shared", "other_bore",
            "contradicted")
#: The reasons a part has no features that are a function of the part and of ``QUIDDITY`` alone (and of the
#: platform, which a computer's own store of results does not change): the same check reads the same again. Any
#: other -- no environment that holds quiddity, another release's answer, a process that ended, ran out of time
#: or of memory, an answer or a failure of the machinery that asks -- is the moment's or this environment's,
#: and a report with one is not ``repeatable``: no result to keep for another check.
REPEATABLE = ("no_wheel", "no_faces", "unwritten", "too_many_faces", "refused", "failed", "unknown_schema",
              "unverified")
#: A record's diameter is a cylinder's within this (mm): quiddity publishes five decimals.
NEAR_MM = 1e-3
#: A hole a record says is closed has its floor within this many bore diameters of where its cylinders end: past
#: a floor's round, a drill's point or a ball's nose, and short of the far wall of whatever a through hole opens
#: into.
FLOOR_DIAMETERS = 1.0


def asked(parts: Iterable[brep.Part], kept: Any = None) -> list[dict[str, Any]]:
    """quiddity's features of each of ``parts`` (``cad.quiddity.features_of``: one recogniser's process for them
    all), in order: a result that says ``available``, or why the part has none (its ``reason``; ``other_release``
    for anything another release than ``QUIDDITY`` answered). Nothing raises: a call that does is every part's
    ``unanswered``. ``kept``: the parts' kept results (``cad._internal.dfm.parts.Kept``; None: none), where a
    part's features are found by how it stands (``_kept``), and a part's answer is kept where it is repeatable --
    available, or for a reason of the part's own (``REPEATABLE``) -- so a part is asked once for each way it
    stands; any other answer is asked again the next time."""
    from cad._internal.dfm.parts import FEATURES

    parts = list(parts)
    found: list[dict[str, Any] | None] = [None] * len(parts)
    keys = [_kept(part) if kept is not None else None for part in parts]
    for index, key in enumerate(keys):
        if key is not None:
            found[index] = kept.get(FEATURES, *key)
    asking = [index for index, result in enumerate(found) if result is None]
    if not asking:
        return found  # type: ignore[return-value]
    try:
        import cad.quiddity

        answers = cad.quiddity.features_of([parts[index] for index in asking])
        if len(answers) != len(asking):
            raise ValueError(f"{len(answers)} answers for {len(asking)} parts")
    except Exception as error:  # noqa: BLE001 -- a recogniser that cannot be asked costs no check its holes
        said = {"available": False, "quiddity": None, "reason": "unanswered",
                "detail": " ".join(f"quiddity could not be asked: {type(error).__name__}: {error}".split())}
        answers = [dict(said) for _ in asking]
    for index, answer in zip(asking, answers):
        result = _of_release(answer)
        if keys[index] is not None and (result.get("available") or result.get("reason") in REPEATABLE):
            kept.keep(FEATURES, *keys[index], result)
            result = kept.settled(result)
        found[index] = result
    return found  # type: ignore[return-value]


def _kept(part: brep.Part) -> tuple[str, dict[str, Any]] | None:
    """What a part's features are kept by (``cad._internal.dfm.parts``): its geometry and how it stands -- and the
    recogniser's result's own version, the schema it reads and the release whose records are taken; None for a
    part no document gave."""
    from cad._internal.dfm.parts import standing
    from cad.quiddity._features import FACES, SCHEMA, VERSION

    stands = standing(part)
    if stands is None:
        return None
    return part.key, {"standing": stands, "version": VERSION, "schema": SCHEMA, "quiddity": QUIDDITY, "faces": FACES}


def _of_release(result: dict[str, Any]) -> dict[str, Any]:
    """``result``, or where another release than ``QUIDDITY`` answered it -- features or none -- that it is not
    read: what another release says of a part, and why it says nothing, is that environment's."""
    version = result.get("quiddity")
    if version is None or version == QUIDDITY:
        return result
    was = "" if result.get("available") else f" ({result.get('reason')}: {result.get('detail')})"
    return {"available": False, "quiddity": version, "reason": "other_release",
            "detail": f"quiddity {version} answered{was}, and its records are read as quiddity {QUIDDITY}'s"}


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
        note.update(reason=str(features.get("reason") or "unanswered"), detail=str(features.get("detail") or ""))
        return _by(found, "cad"), holed, note
    try:
        read = _read(model, found, features, np.eye(3) if rotation is None else np.asarray(rotation), note)
    except Exception as error:  # noqa: BLE001 -- records that do not read against the part cost it no hole
        note.update(reason="misread", declined=[], disagreements=[],
                    detail=f"quiddity's holes could not be read against the part: {type(error).__name__}: {error}")
        return _by(found, "cad"), holed, note
    note["by"] = "quiddity"
    return read, holed, note


def _by(found: list[dict[str, Any]], who: str) -> list[dict[str, Any]]:
    for hole in found:
        hole["recognised_by"] = who
    return found


def _read(model: Model, found: list[dict[str, Any]], features: dict[str, Any], rotation: np.ndarray,
          note: dict[str, Any]) -> list[dict[str, Any]]:
    """The detector's holes (``found``), in its order and on its faces, each with who read it: the hole a taken
    record closes described again with that floor, every other as it is (the module's **Which records are
    taken**); the records declined and the disagreements into ``note``."""
    superseded = {record["id"] for record in features["records"]
                  if isinstance(record.get("parameters"), dict) and record["parameters"].get("superseded_by")}
    at = {face: n for n, hole in enumerate(found) for face in hole["_faces"]}
    entries = []
    named: dict[int, int] = {}  # each of the detector's holes: how many records name a face of it
    for record in features["holes"]:
        steps = [step for step in (record["counterbore"], record["spotface"], *record["outer_counterbores"]) if step]
        cones = [*((record["countersink"],) if record["countersink"] else ()), *record["mouth_chamfers"]]
        bore = sorted(face for face in record["faces"] if model.surface(face).kind == "cylinder"
                      and abs(float(model.surface(face).radius) - record["diameter_mm"] / 2.0) <= NEAR_MM)
        if not bore:
            raise ValueError(f"{record['id']} names no cylinder of its diameter, {record['diameter_mm']:g} mm")
        claimed = {*record["faces"], *(face for part in (*steps, *cones) for face in part["faces"])}
        meets = sorted({at[face] for face in claimed if face in at})
        for n in meets:
            named[n] = named.get(n, 0) + 1
        entries.append({"record": record, "bore": bore, "claimed": claimed, "steps": steps, "cones": cones,
                        "meets": meets})
    read = list(found)
    taken: set[int] = set()
    contested: set[int] = set()

    def differs(where: str, field: str, quiddity: Any, cad: Any) -> None:
        note["disagreements"].append({"location": where, "field": field, "quiddity": quiddity, "cad": cad})

    for entry in entries:
        record, bore, meets = entry["record"], entry["bore"], entry["meets"]
        hole = found[meets[0]] if meets else None
        where = hole["location"] if hole is not None else model.ref(bore[0])
        said = None
        if record["evidence_status"] != "verified":
            why = "unproved"
        elif record["id"] in superseded:
            why = "superseded"
        elif hole is None:
            why = "open" if not _goes_round(model, bore) else "cored" if detector._cored(
                model, set(bore), round(float(model.surface(bore[0]).radius), 6)) else "unmatched"
            differs(where, "hole", True, False)
        elif len(meets) > 1:
            why = "spans"
            differs(where, "holes", 1, len(meets))
        elif not entry["claimed"] <= set(hole["_faces"]):
            why = "beyond"
            differs(where, "faces", len(entry["claimed"]), len(hole["_faces"]))
        elif named[meets[0]] > 1:
            why = "shared"
            if meets[0] not in contested:
                differs(where, "holes", named[meets[0]], 1)
            contested.add(meets[0])
        elif not any(round(float(model.surface(face).radius), 6) == hole["_radius"] for face in bore):
            why = "other_bore"
            differs(where, "diameter_mm", round(2 * round(float(model.surface(bore[0]).radius), 6), 9),
                    hole["diameter_mm"])
        else:
            why, said = _closing(model, hole, record, rotation)
            if why is not None:
                differs(where, *said)
        if why is not None:
            note["declined"].append({"location": where, "record": record["id"], "reason": why})
            continue
        assert hole is not None
        if said is not None:
            closed = detector._describe(model, hole["_group"], hole["_radius"], said)
            if "grooves" in hole:
                closed["grooves"] = hole["grooves"]
            differs(where, "through", False, True)
            hole = read[meets[0]] = closed
        taken.add(meets[0])
        # what each names beside the bore, where they differ: the item lists the detector's, as it did
        stepped = sorted(float(step["diameter_mm"]) for step in entry["steps"])
        bored = sorted(float(step["diameter_mm"]) for step in hole["counterbores"])
        if len(stepped) != len(bored) or any(abs(a - b) > NEAR_MM for a, b in zip(stepped, bored)):
            differs(where, "counterbores", stepped, bored)
        sunk = sum(len(cone["faces"]) for cone in entry["cones"])
        if sunk != len(hole["countersinks"]):
            differs(where, "countersinks", sunk, len(hole["countersinks"]))
    for n, hole in enumerate(read):
        hole["recognised_by"] = "quiddity" if n in taken else "cad"
        if n not in named:
            differs(hole["location"], "hole", False, True)
    return read


def _closing(model: Model, hole: dict[str, Any], record: dict[str, Any],
             rotation: np.ndarray) -> tuple[str | None, Any]:
    """What ``record`` says closes ``hole``, the detector's hole it is, against the kernel: ``(None, None)`` where
    the two agree, or the record's word is no reading (``unknown``); ``(None, said)`` where the detector reads
    through, the record closed, and the kernel bears the record out (``said``: the floor, for
    ``_dfm_cnc_holes._describe``); ``("contradicted", (field, quiddity's, the detector's))`` where the rays
    contradict the record (the module's **Which records are taken**)."""
    word = record["bottom"]
    if word == "through":
        return (None, None) if hole["through"] else ("contradicted", ("through", True, False))
    if word not in ("flat", "drill_point"):
        return None, None
    axis = unit(hole["_axis"])
    sign = 1 if float((rotation @ np.asarray(record["axis"], dtype=float)) @ axis) > 0 else -1
    if not hole["through"]:
        # the hole's own floor, which the detector's ray met: at the end the record goes into, and of its kind
        if hole["bottom"] != "closed" and float(np.asarray(hole["opening"], dtype=float) @ axis) * sign > 0:
            return "contradicted", ("opening", brep.rounded(-axis * sign), hole["opening"])
        return (None, None) if hole["bottom"] == word else ("contradicted", ("bottom", word, hole["bottom"]))
    hit = model.first(hole["_aside"], axis * sign, skip=1e-6)
    if hit is None or not hit.face:
        return "contradicted", ("through", False, True)  # the ray into the hole leaves the part: that end is open
    cylinders = [face for face in hole["_faces"] if model.surface(face).kind == "cylinder"]
    end = max(model.extent(face, axis * sign)[1] for face in cylinders)
    if float(np.asarray(hole["_aside"]) @ (axis * sign)) + hit.distance - end > FLOOR_DIAMETERS * 2 * hole["_radius"]:
        return "contradicted", ("through", False, True)  # what it meets is no floor of this hole's: too far past it
    kind = model.surface(hit.face).kind
    if word == "drill_point" and kind != "cone":
        return "contradicted", ("bottom", word, "through")
    if word == "flat" and kind == "cone":
        return "contradicted", ("bottom", word, "through")
    return None, {"sign": sign, "floor": hit.face, "bottom": word if kind in ("plane", "cone") else "other"}


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
            "repeatable": all(entry["reason"] in REPEATABLE for entry in fallbacks)}
