"""Semantic PMI: manufacturing requirements on a part's own faces, kept in its XCAF document
as XCAF's GD&T objects and written to STEP AP242 as AP242's semantic entities.

A model gives its part annotations, each on faces of that part, and returns the part. The functions
are defined here and are ``cadgen.ap242``'s, each that writes an AP242 entity named after it; notes,
views and presentation, the xbf's alone, keep plain names (the root and ``cadgen.engine`` export
none of them)::

    from cadgen.ap242 import (annotate, datum, dimensional_location, dimensional_size, flatness_tolerance,
                              plus_minus_tolerance, position_tolerance)
    from cadgen.engine import step, xbf

    @xbf(out="XBF/plate.xbf")
    @step("plate.step")
    def plate():
        body = bd.Box(100, 60, 10) - bd.Cylinder(5, 10)
        bottom = body.faces().sort_by(bd.Axis.Z)[0]
        top = body.faces().sort_by(bd.Axis.Z)[-1]
        hole = body.faces().filter_by(bd.GeomType.CYLINDER)[0]
        return annotate(body,
            datum("A", bottom),
            dimensional_location("thickness", bottom, top, tolerance=plus_minus_tolerance(0.2)),
            dimensional_size("hole", hole, tolerance=plus_minus_tolerance(0.1, 0)),
            flatness_tolerance("top-flat", top, 0.05),
            position_tolerance("hole-pos", hole, 0.1, datums=["A"]))

**What is held.** What the code says and what this build's geometry resolves, nothing else: XCAF's
``XCAFDimTolObjects`` objects on the GD&T tool's labels (``XCAFDoc_DimTolTool``) hold the kind,
values and units (millimetres, the document's) and link the annotation to the sub-shape labels of
the faces it is on; beside each, a ``TDF_Reference`` to its part's shape label and one cadgen
attribute (``EXTRA_GUID``, JSON of ``SCHEMA``) holding what XCAF has no place for: the author's id
and label, the kind, each ref as the code wrote it, the presentation, a general profile's flag, and
an annotation linked to nothing its values (XCAF gives values meaning only through geometry). The
id and the kind are in XCAF too (its semantic name, its object). No status, no problem and nothing
of a previous build is held: an annotation's status is derived where the document is read
(``records_of_document``), as a build derives it, and a general profile's faces with it. The STEP
writer reads the XCAF objects and writes AP242's semantic PMI
(``DIMENSIONAL_SIZE``/``DIMENSIONAL_LOCATION`` with ``PLUS_MINUS_TOLERANCE`` or their limits,
``DATUM``/``DATUM_FEATURE``, ``FLATNESS_TOLERANCE``, ``POSITION_TOLERANCE`` and
``SURFACE_PROFILE_TOLERANCE`` with their ``DATUM_SYSTEM``) on ``SHAPE_ASPECT``s whose
``GEOMETRIC_ITEM_SPECIFIC_USAGE`` names the face (a profile on several faces: on a
``COMPOSITE_SHAPE_ASPECT`` relating one such aspect per face). The cadgen attribute is not
written to a STEP.

**Notes** (``note``) are the xbf's alone: XCAF comments in its notes tool (``XCAFDoc_NotesTool``),
by one fixed user (``NOTE_USER``) with no timestamp, so the same code makes the same bytes; each
with the same ``TDF_Reference`` and cadgen attribute beside it (the id, label, presentation, refs
and the ids it names as written; the text is XCAF's). A general note names no face and no
annotation and is attached to its part's shape label; a flag note is attached to each face it is
on (``AddNoteToSubshape``, the sub-shape index the face's ordinal in its part's face map, where
the note is ``ok``) and to the GD&T label of each annotation it names. A note's faces resolve as
any ref does, on a face of any kind; one whose face is gone keeps its number and text, its status
saying so. Its number is derived where served: Note 1 is the part's general profile where it has
one, then each note in the code's order. OCCT's STEP writer writes no notes, so a STEP carries
none and is never refused for one (``step_entries``). A note this module did not write (no cadgen
attribute) is not read.

**A general tolerance** (``general_tolerance``) is ISO 2768's, as a drawing states it: a general
note (``General tolerances ISO 2768-mK``) whose cadgen attribute holds the standard too, so the
note's served block says it (``general_tolerance``). It covers every face nothing else does
(``coverage``) and is the one note a STEP carries (``step_entries``): OCCT's writer has no entity
for it, so the engine appends CAx-IF's 'default tolerances' property of its part's shape, its
'tolerance class' the standard (``export.step``), which the export check reads back and matches.

**Views** (``view``) are the xbf's alone too: a part's named views, the views its requirements are
walked through in (a front, a section, a detail; an iso view showing all). Each is seen down a camera
-- a preset's name, ``cadgen snapshot --camera``'s own table (``render/presets.py``), or
``camera(direction, up)``, ``direction`` from the part toward the eye as a preset's is --
orthographic, cut where it has a section (``section``: the viewer's Clip, ``{axis, at, invert}``),
showing the ids of its ``annotate`` call it names (every one where it names none) with its own
placements of them (``place``), all in its part's frame. Each is an XCAF view in the views tool
(``XCAFDoc_ViewTool``): parallel, looking along its direction reversed (XCAF's view direction is
the one looked along), its eye the part's box centre moved toward the eye by the box's diagonal,
its window that diagonal and its zoom 1; linked to its part's shape label and the GD&T labels it
shows, its section an XCAF clipping plane (``XCAFDoc_ClippingPlaneTool``) named for it; beside it
the same ``TDF_Reference`` and a cadgen attribute holding the view as the code gave it, which the
structure's ``pmi_views`` is served from. The notes it shows are that attribute's alone: OCCT's
``SetView`` files a view's notes under its clipping-plane link. OCCT's STEP writer writes no views,
so a STEP carries none and is never refused for one. An xbf made again from a document (one part
of it) carries no views or notes yet, and is refused for any of them, by name
(``refuse_dropped``). A view this module did not write is not read.

**Values.** A dimension's nominal is the geometry's, measured at document time: a cylinder's
diameter, the distance between two parallel planes. No nominal is typed in. A tolerance is held
only where the code gives one (``plus_minus_tolerance``: signed deviations, upper above lower;
``limits``: the least and the greatest size, absolute). XCAF holds a dimension's lower deviation as
a magnitude and the STEP writer negates it, so ``plus_minus_tolerance(0.2)`` is written
``TOLERANCE_VALUE(-0.2, 0.2)``; the conversion is this module's, both ways. XCAF holds limits as a
dimension's two values in place of its nominal, its value then their midpoint, which the STEP
writer writes as the nominal value beside CAx-IF's ``'lower limit'`` and ``'upper limit'`` items:
the nominal of one the code made is measured again where its document is read, and one read from
a file has none (the file states limits; the midpoint XCAF rebuilds is no fact of it).

**References.** A ref is a face of the part annotated: a build123d ``Face`` of the shape given to
``annotate`` (numbered against it at once), or a ref in the engine's grammar (``refs``) -- an
element name (``f:plate.body.6``), the canonical ``owner/element`` ref a document serves, or an
ordinal (``face 7``). Element names are the engine's persistent naming (``kernel.trace``): a face
keeps its name across edits that do not change how it is made. Each build resolves every ref
against the part as built now: ``ok``; ``missing`` -- it names nothing (with what the name's atom
is called now, where anything is); ``ambiguous`` -- it names several faces (each listed); or
``invalid`` -- it names a face the annotation cannot stand on (a diameter on a plane, two planes
not parallel, a datum letter the part does not define). An annotation's status is its worst ref's.
One not ``ok`` is kept in the document, with its values and refs as written, and linked to no
geometry; the build reports it, and a STEP export refuses to drop it. A tolerance whose frame names
a datum not ``ok`` takes that datum's status: it is measured from nothing the part has.

**The general profile** (``general_profile``) is ASME Y14.5's "unless otherwise noted, all
surfaces": a surface profile of every face of its part that nothing else controls
(``otherwise_controlled``: a face with a size or location requirement of its own), computed by each
build from that build's annotations and geometry alone, never written in the code and never kept
from an earlier build. The datum features it names are controlled on their own and left out (no
face is profiled relative to itself). The document links it to exactly those faces, and a STEP
has it as a ``SURFACE_PROFILE_TOLERANCE`` on them, so a reader gets the faces themselves. It is
not XCAF's ``All_Over`` modifier, which in ASME means every surface beside any other requirement.
It has no ref to break: it is ``ok`` (``invalid`` where its frame names a datum the part lacks),
and one covering no face is linked to nothing and written to no STEP.

**Coverage** (``coverage``) holds a part to every face having a requirement, most through its
general profile. Of each part carrying PMI, where its document is served (``coverage_of``, the
structure's ``pmi_coverage``), and in the build's report from the same: the faces no ``ok``
toleranced dimension or geometric tolerance names (the general profile names those it covers; a
basic dimension, a datum and a note cover nothing, and the datum features a general profile names
are left to controls of their own), and the requirements that cannot both hold or hold nothing --
a datum no frame names, a flag note every link of which is broken, two dimensions of one type on
the same faces whose zones do not meet, a flatness wider than a profile on its face. Derived, never
held, and warned of: it never fails a build. Beside it, what the part's requirements leave unsaid
(``suggestions``): each a question with the answer a standard gives and why, read off this module's
tables (ISO 273, ISO 261/2306, ISO 286), asked and never applied. A limits dimension its measured nominal lies outside is
no conflict but a size the model does not have: the build fails, naming it (``outside_limits``).

**A document another system wrote** (a vendor's STEP, or an xbf converted from one) lists its
GD&T as XCAF reads it. What this module does not hold whole -- another characteristic or dimension
type, a fit, a qualifier, a modifier, limits beside any of them, a datum target, a link to an edge or
a point -- is listed ``unsupported`` with its XCAF type and why, never refused and never read as less
than it says.
An xbf converted from it copies its GD&T as read (``copy``); an export of it says what it leaves
out (``dropped``) where one of a document the code made is refused (``refuse_dropped``).

**Presentation** (``place``) is where a viewer draws an annotation: an anchor and a text offset in
millimetres, in the annotated part's frame. It is no part of the semantic record, and moving it
changes nothing an annotation means. A STEP draws it there, as AP242's presentation of the
annotation (``_present``): its text point, an annotation plane through it and a leader from the
anchor, a ``DRAUGHTING_CALLOUT`` named by its id that a ``DRAUGHTING_MODEL_ITEM_ASSOCIATION`` links
to the semantic record, so another system's viewer draws the callout where this one does. One with
no offset has no leader to draw and is written with none (OCCT writes no callout without a shape).
Read from a file (``_presentation_of``), a callout drawn as one straight line is a leader, its far
end the anchor; another system's lettering is placed at its text point.

**Scope.** What is written and read back is verified end to end (the engine's PMI tests, with
an AP242 reader of no OCCT):
datums on a plane or cylinder; diameter and linear-distance dimensions with a plus-minus
tolerance or limits; basic (theoretically exact) distances, from planes and hole axes, with no
tolerance, marked as AP242 marks them (CAx-IF's 'theoretical' dimension note); flatness; position
with an ordered datum reference frame and a diametral zone; a surface profile on one face or
several, of any kind, with a frame of up to three datums or none; a part's general profile, on
the faces nothing else controls; a part's ISO 2768 general tolerances; and, in the xbf alone, general and flag notes and a part's named
views. Each
is written by the function named after its AP242 entity (``cadgen.ap242``'s); no function writes
another XCAF characteristic or dimension type, and every other modifier and tolerance form is
refused by name (``PMIUnsupported``), never approximated. PMI is part-level: an annotation is on one part, and an
assembly is refused.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

__all__ = ["PMIError", "PMIUnsupported", "annotate", "camera", "coverage", "datum", "dimensional_location",
           "dimensional_size", "flatness_tolerance", "general_profile", "general_tolerance", "limits", "note",
           "otherwise_controlled", "place", "plus_minus_tolerance", "position_tolerance", "read", "section",
           "step_entries", "suggestions", "surface_profile_tolerance", "view"]

# The attribute an annotated shape holds its annotations in (a tuple of plain dicts), as a part's
# configurations are held (``kernel.memo`` keys it).
PMI = "xbf_pmi"
# The GUID of the cadgen attribute beside each XCAF GD&T object, and its JSON's schema (see the
# module): an attribute of another schema is not read.
EXTRA_GUID = "5d3a7c1e-9f42-4b86-a0e5-3c7b9d2f6e18"
SCHEMA = "cadgen.pmi/1"
# The GD&T tool's label under the main label (``XCAFDoc_DocumentTool::DimTolLabel``), the views
# tool's (``XCAFDoc_DocumentTool::ViewsLabel``) and the notes tool's (``XCAFDoc_DocumentTool::NotesLabel``).
DIMTOL_TAG = 4
VIEWS_TAG = 7
NOTES_TAG = 9
# A note is an XCAF comment by one fixed user with no timestamp: the same code makes the same bytes.
NOTE_USER = "cadgen"
NOTE_TYPE = "XCAFDoc_NoteComment"
STATUSES = ("ok", "missing", "ambiguous", "invalid")
# A basic dimension's mark in AP242 (CAx-IF PMI Recommended Practices 4.1, 5.3, Table 7): the
# descriptive item's name and description.
THEORETICAL = ("dimensional note", "theoretical")
UNIT = "mm"

# Every kind of face, as ``_surface`` names OCCT's surface types (``GeomAbs_SurfaceType``).
_EVERY_SURFACE = ("plane", "cylinder", "cone", "sphere", "torus", "beziersurface", "bsplinesurface",
                  "surfaceofrevolution", "surfaceofextrusion", "offsetsurface", "othersurface")
# The faces each annotation stands on.
# A basic dimension is a distance between planes, a plane and a hole's axis, or two axes.
_SURFACES = {"datum": ("plane", "cylinder"), "diameter": ("cylinder",), "distance": ("plane",),
             "basic": ("plane", "cylinder"),
             "flatness": ("plane",), "position": ("cylinder",), "surface_profile": _EVERY_SURFACE,
             "note": _EVERY_SURFACE}


class PMIError(ValueError):
    """An annotation the code gave wrongly: said by name, before anything is written."""


class PMIUnsupported(PMIError):
    """An annotation outside what this module writes and reads back verified: refused by name,
    never approximated."""


# --- authoring -------------------------------------------------------------------------------


def plus_minus_tolerance(upper: float, lower: float | None = None) -> dict[str, Any]:
    """A dimension's ``plus_minus_tolerance``: signed deviations from the nominal, ``lower`` below
    ``upper`` (``-upper`` when not given: ``plus_minus_tolerance(0.2)`` is ±0.2;
    ``plus_minus_tolerance(0.1, 0)`` is +0.1/0)."""
    upper = _number(upper, "a tolerance's upper deviation")
    lower = -upper if lower is None else _number(lower, "a tolerance's lower deviation")
    if not upper > lower:
        raise PMIError(f"a plus-minus tolerance's upper deviation is above its lower ({lower}), not {upper}")
    return {"type": "plus_minus", "upper": upper, "lower": lower}


def limits(lower: float, upper: float) -> dict[str, Any]:
    """Limits: the least and the greatest size, absolute millimetres, ``upper`` above ``lower``
    (``limits(10.0, 10.05)`` is 10.00–10.05). In place of deviations; the nominal is still
    measured. Written as the dimension's ``'lower limit'`` and ``'upper limit'`` values, no entity
    of their own."""
    lower = _number(lower, "a dimension's lower limit")
    upper = _number(upper, "a dimension's upper limit")
    if not lower > 0:
        raise PMIError(f"a dimension's lower limit is a size above 0, not {lower}")
    if not upper > lower:
        raise PMIError(f"a dimension's upper limit (the second) is above its lower, not {lower} and {upper}")
    return {"type": "limits", "lower": lower, "upper": upper}


def place(anchor: Iterable[float], offset: Iterable[float] = (0.0, 0.0, 0.0)) -> dict[str, Any]:
    """Where a viewer draws an annotation (provisional): ``anchor`` on or near its feature and the
    text ``offset`` from it, millimetres in the annotated part's frame. Not semantic: a STEP draws
    the callout there (``_present``), and moving it changes nothing the annotation means."""
    return _place(anchor, offset)


def _place(anchor: Any, offset: Any) -> dict[str, Any]:
    return {"anchor": _point(anchor, "an anchor"), "offset": _point(offset, "an offset")}


# The letters a datum is named by: A..Z but I, O and Q, which ASME Y14.5 sets aside (read as 1 and 0).
DATUM_LETTERS = frozenset("ABCDEFGHJKLMNPRSTUVWXYZ")


def _datum_letter(letter: Any, what: str) -> None:
    if not isinstance(letter, str) or len(letter) != 1 or not letter.isascii() or not letter.isupper():
        raise PMIError(f"{what} is one capital A..Z, not {letter!r}")
    if letter not in DATUM_LETTERS:
        raise PMIError(f"{what} is not {letter!r}: ASME Y14.5 sets I, O and Q aside, as they read as 1 and 0; "
                       "name the datum by another letter")


def datum(letter: str, ref: Any, *, label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """AP242's ``datum`` ``letter`` (``A``..``Z`` but ``I``, ``O`` and ``Q``: ``DATUM_LETTERS``)
    and its ``datum_feature``, on a planar or cylindrical face. Its id is its letter."""
    _datum_letter(letter, "a datum's letter")
    return _annotation(letter, "datum", [("feature", ref)], label, presentation, datum={"letter": letter})


def dimensional_size(id: str, ref: Any, *, tolerance: dict | None = None, label: str | None = None,
                     presentation: dict | None = None) -> dict[str, Any]:
    """AP242's ``dimensional_size`` named 'diameter': the diameter of a cylindrical face (a hole, a
    boss), measured from the geometry; ``tolerance`` given explicitly (``plus_minus_tolerance`` or
    ``limits``)."""
    return _annotation(id, "dimension", [("feature", ref)], label, presentation,
                       dimension={"type": "diameter", "basic": False, "tolerance": _tolerance(tolerance, id)})


def dimensional_location(id: str, ref_from: Any, ref_to: Any, *, tolerance: dict | None = None, basic: bool = False,
                         label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """AP242's ``dimensional_location``: the distance between two parallel planar faces, measured
    from the geometry; ``tolerance`` given explicitly (``plus_minus_tolerance`` or ``limits``).
    ``basic``: theoretically exact (ASME's basic, ISO's theoretical), with no tolerance -- between
    two parallel planes, from a plane to a hole's axis parallel to it, or between two parallel axes:
    what a position tolerance's true position is located by."""
    if basic and tolerance is not None:
        raise PMIError(f"dimensional_location({id!r}, basic=True): a basic dimension is theoretically exact: it "
                       "takes no tolerance")
    return _annotation(id, "dimension", [("from", ref_from), ("to", ref_to)], label, presentation,
                       dimension={"type": "distance", "basic": bool(basic), "tolerance": _tolerance(tolerance, id)})


def _geometric(id: str, characteristic: str, refs: list[Any], value: float, datums: Iterable[str],
               diameter_zone: bool, label: str | None, presentation: dict | None, *, general: bool) -> dict[str, Any]:
    """A geometric tolerance of ``characteristic`` (``flatness``, ``position``, ``surface_profile``)
    of ``value`` millimetres on ``refs``, referring to ``datums`` in order (primary first), a
    diametral zone with ``diameter_zone``: what ``flatness_tolerance``, ``position_tolerance`` and
    ``surface_profile_tolerance`` check alike. ``general``: the part's general profile, on no ref
    the code writes (``general_profile``)."""
    value = _number(value, f"tolerance {id!r}'s value")
    if not value > 0:
        raise PMIError(f"tolerance {id!r}: a tolerance zone is wider than 0, not {value}")
    letters = list(datums)
    for letter in letters:
        _datum_letter(letter, f"tolerance {id!r}: a datum's letter")
    if len(set(letters)) != len(letters):
        raise PMIError(f"tolerance {id!r}: a datum is named once in a frame, not {letters}")
    if len(letters) > 3:
        raise PMIError(f"tolerance {id!r}: a datum reference frame has three datums at most, not {len(letters)}")
    if characteristic == "position" and not letters:
        raise PMIUnsupported(f"tolerance {id!r}: a position with no datum is not written verified yet; name its datums")
    return _annotation(id, "geometric_tolerance", [("feature", given) for given in refs], label, presentation,
                       geometric_tolerance={"characteristic": characteristic, "value": value, "unit": UNIT,
                                            "zone": "diameter" if diameter_zone else None, "modifier": None,
                                            "datums": letters, "general": general})


def flatness_tolerance(id: str, ref: Any, value: float, *, label: str | None = None,
                       presentation: dict | None = None) -> dict[str, Any]:
    """AP242's ``flatness_tolerance``: flatness of ``value`` millimetres on a planar face, a form
    tolerance, with no datum."""
    return _geometric(id, "flatness", [ref], value, (), False, label, presentation, general=False)


def position_tolerance(id: str, ref: Any, value: float, *, datums: Iterable[str], diameter_zone: bool = True,
                       label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """AP242's ``position_tolerance``: the position of a cylindrical feature (a hole's axis),
    ``value`` millimetres, a diametral zone by default, relative to ``datums`` in order."""
    return _geometric(id, "position", [ref], value, datums, diameter_zone, label, presentation, general=False)


def surface_profile_tolerance(id: str, refs: Any, value: float, *, datums: Iterable[str] = (),
                              label: str | None = None, presentation: dict | None = None) -> dict[str, Any]:
    """AP242's ``surface_profile_tolerance``: the profile of a surface, ``value`` millimetres wide
    about its true profile: on a face, or on each of a list of faces of any kind (one requirement on
    all of them), relative to ``datums`` in order (none to three)."""
    found = list(refs) if isinstance(refs, (list, tuple)) else [refs]
    if not found:
        raise PMIError(f"tolerance {id!r}: a surface profile is on one face or more, not none")
    return _geometric(id, "surface_profile", found, value, datums, False, label, presentation, general=False)


def general_profile(id: str, value: float, *, datums: Iterable[str] = (), label: str | None = None) -> dict[str, Any]:
    """The part's general profile, ``value`` millimetres wide, relative to ``datums`` in order
    (none to three): ASME Y14.5's "unless otherwise noted, all surfaces", a surface profile of every
    face of the part that nothing else controls (``otherwise_controlled``), its faces computed by
    each build from that build's annotations and geometry. Not XCAF's ``All_Over`` modifier (every
    surface, beside any other requirement): it is written as a ``surface_profile_tolerance`` on
    exactly the faces it covers. One per part."""
    return _geometric(id, "surface_profile", [], value, datums, False, label, None, general=True)


# ISO 2768's general tolerances as a drawing states them: its class for linear and angular sizes
# (part 1: f, m, c or v), and for general geometrical tolerances its class (part 2: H, K or L) after it.
GENERAL_TOLERANCE = re.compile(r"ISO 2768-([fmcv])([HKL])?")


def general_tolerance(id: str, standard: str, *, label: str | None = None) -> dict[str, Any]:
    """The part's general tolerances, ``standard`` -- ISO 2768, as a drawing states it:
    ``"ISO 2768-m"``, or ``"ISO 2768-mK"`` with the general geometrical tolerances of its part 2 --
    the limits of every size and form nothing else tolerances. A general note saying so (numbered
    as any note is) that covers every face nothing else does (``coverage``), and the one note a STEP
    carries: CAx-IF's 'default tolerances' property of the part, its 'tolerance class' the standard
    (``export.step``). Another standard is refused by name, never approximated. One per part."""
    if not isinstance(standard, str) or not GENERAL_TOLERANCE.fullmatch(standard):
        raise PMIUnsupported(f"general tolerance {id!r}: ISO 2768 is written as 'ISO 2768-m' or 'ISO 2768-mK' (its "
                             f"class f, m, c or v; then H, K or L for general geometrical tolerances), not "
                             f"{standard!r}")
    return _annotation(id, "note", [], label, None,
                       note={"text": f"General tolerances {standard}", "annotations": [], "general_tolerance": standard})


def note(id: str, text: str, *, faces: Any = (), annotations: Iterable[str] = (), label: str | None = None,
         presentation: dict | None = None) -> dict[str, Any]:
    """A note of the part saying ``text``, the code's words: a general note where it names no face
    and no annotation; a flag note on ``faces`` (a face, or a list of faces of any kind) and on the
    ``annotations`` of the same ``annotate`` call it names by id. Numbered among its part's notes as
    the code gives them, after the part's general profile, which is Note 1 where it has one. Its id
    is one of the part's ids. Kept in the xbf, never in a STEP (AP242's writer here writes no
    notes)."""
    if not isinstance(text, str) or not text.strip():
        raise PMIError(f"note {id!r}: a note's text is a non-empty string, not {text!r}")
    refs = list(faces) if isinstance(faces, (list, tuple)) else [faces]
    named = [annotations] if isinstance(annotations, str) else list(annotations)
    for at, given in enumerate(named):
        if not isinstance(given, str) or not given.strip():
            raise PMIError(f"note {id!r}: an annotation is named by its id, not {given!r}")
        if given in named[:at]:
            raise PMIError(f"note {id!r}: names {given!r} twice; a note names each annotation once")
    return _annotation(id, "note", [("feature", face) for face in refs], label, presentation,
                       note={"text": text, "annotations": named, "general_tolerance": None})


def camera(direction: Iterable[float], up: Iterable[float]) -> dict[str, Any]:
    """A view's camera of the code's own: ``direction`` from the part toward the eye (as a
    preset's, ``cadgen snapshot --camera``'s: ``front`` is ``(0, -1, 0)``) and the camera's
    ``up``, in the part's frame, each made a unit vector. An ``up`` along the direction is refused."""
    found = [_unit(direction, "a camera's direction"), _unit(up, "a camera's up")]
    if _cross(*found) < 1e-9:
        raise PMIError(f"a camera's up is not along its direction, not {list(up)} with {list(direction)}")
    return {"direction": found[0], "up": found[1]}


def section(axis: str, at: float, *, invert: bool = False) -> dict[str, Any]:
    """A view's section: the viewer's Clip, one plane across ``axis`` (``x``, ``y`` or ``z``) at
    ``at`` millimetres in the part's frame, keeping the lower side (``invert``: the upper)."""
    return _section(axis, at, invert)


def _section(axis: Any, at: Any, invert: Any) -> dict[str, Any]:
    if axis not in ("x", "y", "z"):
        raise PMIError(f"a section's axis is x, y or z, not {axis!r}")
    if not isinstance(invert, bool):
        raise PMIError(f"a section's invert is True or False, not {invert!r}")
    return {"axis": axis, "at": _number(at, "a section's place"), "invert": invert}


def view(name: str, *, camera: str | dict, shows: Sequence[str] | None = None, section: dict | None = None,
         place: Mapping[str, dict] | None = None, label: str | None = None) -> dict[str, Any]:
    """A named view of the part, given to ``annotate`` among its annotations: seen down ``camera``
    (a preset's name, ``cadgen snapshot --camera``'s, or ``camera(direction, up)``), orthographic,
    cut by ``section`` (``section``) where it has one, showing the annotations and notes of the
    same call ``shows`` names by id (None: every one, as an iso view does), each it ``place``-s by
    id drawn there in this view (``place``) and elsewhere as its own presentation says. Its
    name is unique among its part's views. Kept in the xbf as an XCAF view, never in a STEP."""
    from cadgen.engine.render.presets import PRESETS

    if not isinstance(name, str) or not name.strip():
        raise PMIError(f"a view's name is a non-empty string, not {name!r}")
    if label is not None and not isinstance(label, str):
        raise PMIError(f"view {name!r}: a label is a string, not {label!r}")
    if not (camera in PRESETS if isinstance(camera, str) else _is_camera(camera)):
        raise PMIError(f"view {name!r}: a camera is a preset ({', '.join(sorted(PRESETS))}) or camera(direction, "
                       f"up), not {camera!r}")
    named = None if shows is None else [shows] if isinstance(shows, str) else list(shows)
    for at, given in enumerate(named or ()):
        if not isinstance(given, str) or not given.strip():
            raise PMIError(f"view {name!r}: an annotation is shown by its id, not {given!r}")
        if given in named[:at]:
            raise PMIError(f"view {name!r} shows {given!r} twice; a view shows each annotation once")
    if section is not None:
        if not isinstance(section, dict) or set(section) != {"axis", "at", "invert"}:
            raise PMIError(f"view {name!r}: a section is section(axis, at), not {section!r}")
        section = _section(section["axis"], section["at"], section["invert"])
    placed: dict[str, Any] = {}
    for id, given in (place or {}).items():
        if not isinstance(id, str) or not id.strip():
            raise PMIError(f"view {name!r}: an annotation is placed by its id, not {id!r}")
        if not isinstance(given, dict) or set(given) != {"anchor", "offset"}:
            raise PMIError(f"view {name!r}: a placement is place(anchor, offset), not {given!r}")
        placed[id] = _place(given["anchor"], given["offset"])
    return {"pmi": 1, "kind": "view", "name": name, "label": label,
            "camera": camera if isinstance(camera, str) else {"direction": list(camera["direction"]),
                                                              "up": list(camera["up"])},
            "shows": named, "section": section, "place": placed}


def _is_camera(given: Any) -> bool:
    """Whether ``given`` is a camera ``camera`` made: a unit direction and a unit up, not along it."""
    if not isinstance(given, dict) or set(given) != {"direction", "up"}:
        return False
    try:
        found = [_point(given[key], "a camera's " + key) for key in ("direction", "up")]
    except PMIError:
        return False
    return all(abs(math.sqrt(sum(c * c for c in v)) - 1.0) < 1e-9 for v in found) and _cross(*found) >= 1e-9


def _unit(value: Any, what: str) -> list[float]:
    found = _point(value, what)
    length = math.sqrt(sum(c * c for c in found))
    if not length > 0:
        raise PMIError(f"{what} is longer than 0, not {value!r}")
    return [c / length + 0.0 for c in found]


def _cross(first: list[float], second: list[float]) -> float:
    """The length of two vectors' cross product: 0 where they lie along one line."""
    (a, b, c), (d, e, f) = first, second
    return math.sqrt((b * f - c * e) ** 2 + (c * d - a * f) ** 2 + (a * e - b * d) ** 2)


def annotate(shape: Any, *annotations: dict[str, Any]) -> Any:
    """``shape`` given ``annotations`` (replacing any it held): the part a model returns, or
    one part of its assembly. A ``Face`` given as a ref is numbered against ``shape`` now (a face of
    another shape refused, by its annotation's id). Ids are
    unique on a part, a note's with the rest, as are datum letters; a note names annotations of
    this call; and a datum holds one place in every frame that names it (XCAF holds one position
    per datum). Its views (``view``) are among them, each name unique among its views, each
    showing and placing ids of this call (a view's placement of an id it does not show is
    refused). Each is a dict as its function makes it, its keys that function's alone (``_keys``).
    Returns ``shape``."""
    import build123d as bd

    if not isinstance(shape, bd.Shape) or getattr(shape, "wrapped", None) is None:
        raise PMIError(f"annotate() takes the part its annotations are on, not {type(shape).__name__}")
    if getattr(shape, "children", None):
        raise PMIUnsupported("annotate() is given one part: assembly-level PMI is not written yet; annotate "
                             "each part")
    held: list[dict[str, Any]] = []
    views: list[dict[str, Any]] = []
    ids: set[str] = set()
    places: dict[str, tuple[int, str]] = {}
    faces = None
    for given in annotations:
        _keys(given)
        if given["kind"] == "view":
            if any(other["name"] == given["name"] for other in views):
                raise PMIError(f"two views of one part are named {given['name']!r}: a view's name is unique")
            views.append(dict(given))
            continue
        if given["id"] in ids:
            raise PMIError(f"two annotations on one part are {given['id']!r}: an id is unique")
        ids.add(given["id"])
        refs = []
        for ref in given["refs"]:
            target = ref["target"]
            if isinstance(target, str):
                refs.append({"role": ref["role"], "written": target, "face": None})
                continue
            if faces is None:
                faces = _faces(shape.wrapped)
            ordinal = faces.FindIndex(target.wrapped)
            if not ordinal:
                raise PMIError(f"annotation {given['id']!r}: its {ref['role']} ref is a face of another shape, not of "
                               "the part annotated: give a face of the shape passed to annotate()")
            refs.append({"role": ref["role"], "written": f"face {ordinal}", "face": ordinal})
        entry = {key: value for key, value in given.items() if key != "refs"}
        entry["refs"] = refs
        for at, letter in enumerate((given.get("geometric_tolerance") or {}).get("datums") or (), 1):
            if letter in places and places[letter][0] != at:
                raise PMIUnsupported(f"datum {letter} is datum {places[letter][0]} of {places[letter][1]!r} and datum "
                                     f"{at} of {given['id']!r}: XCAF holds one position per datum")
            places.setdefault(letter, (at, given["id"]))
        held.append(entry)
    letters = [entry["datum"]["letter"] for entry in held if entry["kind"] == "datum"]
    if len(set(letters)) != len(letters):
        raise PMIError(f"a part defines each datum letter once, not {letters}")
    general = [entry["id"] for entry in held if _general(entry)]
    if len(general) > 1:
        raise PMIError(f"a part has one general profile, not {' and '.join(map(repr, general))}")
    stated = [entry["id"] for entry in held if (entry.get("note") or {}).get("general_tolerance")]
    if len(stated) > 1:
        raise PMIError(f"a part has one general tolerance, not {' and '.join(map(repr, stated))}")
    kinds = {entry["id"]: entry["kind"] for entry in held}
    for entry in held:
        for named in (entry.get("note") or {}).get("annotations") or ():
            if named not in kinds:
                raise PMIError(f"note {entry['id']!r} names {named!r}, which is no annotation of this annotate() "
                               f"call; its ids are {', '.join(map(repr, kinds))}")
            if kinds[named] == "note":
                raise PMIError(f"note {entry['id']!r} names note {named!r}: a note names annotations, not notes")
    for given in views:
        shown = given["shows"]
        for named in [*(shown or ()), *given["place"]]:
            if named not in kinds:
                raise PMIError(f"view {given['name']!r} {'shows' if named in (shown or ()) else 'places'} {named!r}, "
                               f"which is no annotation of this annotate() call; its ids are "
                               f"{', '.join(map(repr, kinds)) or 'none'}")
            if shown is not None and named not in shown:
                raise PMIError(f"view {given['name']!r} places {named!r}, which it does not show; its shows are "
                               f"{', '.join(map(repr, shown))}")
    from cadgen.engine.kernel import memo

    # Kept on the build's run under the model whose body gave them, directly or through a @memo
    # function it called; a replay of either gives them again.
    memo.annotated([_text(entry) for entry in held])
    held.extend(views)
    shape.__dict__[PMI] = tuple(held)
    return shape


# The keys of what each function makes, closed (law 16): every annotation's, then its kind's own block
# (``datum``, ``dimension``, ``geometric_tolerance``, ``note``), each ref's, a tolerance's by its type,
# and a view's.
_COMMON = ("pmi", "id", "kind", "label", "presentation", "refs")
_BLOCKS = {"datum": ("letter",), "dimension": ("type", "basic", "tolerance"),
           "geometric_tolerance": ("characteristic", "value", "unit", "zone", "modifier", "datums", "general"),
           "note": ("text", "annotations", "general_tolerance")}
_REF_KEYS = ("role", "target")
_TOLERANCES = {"plus_minus": ("type", "upper", "lower"), "limits": ("type", "lower", "upper")}
_VIEW = ("pmi", "kind", "name", "label", "camera", "shows", "section", "place")


def _closed(given: Any, keys: Sequence[str], what: str) -> None:
    """``given`` a dict of exactly ``keys``: one it lacks or one beyond them refused by name, with
    the set it is of."""
    if not isinstance(given, dict):
        raise PMIError(f"{what} is a dict of {', '.join(keys)}, not {type(given).__name__}")
    unknown = [key for key in given if key not in keys]
    missing = [key for key in keys if key not in given]
    if unknown or missing:
        said = (f"unknown key {', '.join(map(repr, unknown))}" if unknown
                else f"no key {', '.join(map(repr, missing))}")
        raise PMIError(f"{what}: {said}; its keys are {', '.join(keys)}")


def _keys(given: Any) -> None:
    """An annotation given to ``annotate`` as its function made it: of a kind it knows, each dict of
    it of its closed keys (``_COMMON`` and its kind's block, each ref's, a view's), its tolerance and
    its presentation as ``plus_minus_tolerance``/``limits`` and ``place`` make them; refused by
    name otherwise, never read in part."""
    if not isinstance(given, dict) or given.get("pmi") != 1:
        raise PMIError(f"annotate() takes annotations made by datum(), dimensional_size(), ...: not {given!r}")
    kind = given.get("kind")
    if kind == "view":
        _closed(given, _VIEW, f"view {given.get('name')!r}")
        # Its camera, section and placements as ``view`` checks them, each of its closed keys.
        view(given["name"], camera=given["camera"], shows=given["shows"], section=given["section"],
             place=given["place"], label=given["label"])
        return
    if kind not in _BLOCKS:
        raise PMIError(f"an annotation's kind is {', '.join(_BLOCKS)} or view, not {kind!r}")
    what = f"annotation {given.get('id')!r}"
    _closed(given, (*_COMMON, kind), what)
    _closed(given[kind], _BLOCKS[kind], f"{what}'s {kind}")
    if not isinstance(given["refs"], list):
        raise PMIError(f"{what}: its refs are a list, not {type(given['refs']).__name__}")
    for ref in given["refs"]:
        _closed(ref, _REF_KEYS, f"{what}'s ref")
    _presentation(given["presentation"], given["id"])
    if kind == "dimension":
        _tolerance(given["dimension"]["tolerance"], given["id"])


def _annotations(given: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """What ``annotate`` gave a part, its views apart: its annotations, notes among them."""
    return [entry for entry in given if entry["kind"] != "view"]


def _views(given: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """A part's views as ``annotate`` gave them (``view``), in the code's order."""
    return [entry for entry in given if entry["kind"] == "view"]


def _annotation(id: str, kind: str, refs: list[tuple[str, Any]], label: str | None, presentation: dict | None,
                **values: Any) -> dict[str, Any]:
    import build123d as bd

    if not isinstance(id, str) or not id.strip():
        raise PMIError(f"an annotation's id is a non-empty string, not {id!r}")
    if label is not None and not isinstance(label, str):
        raise PMIError(f"annotation {id!r}: a label is a string, not {label!r}")
    for _role, target in refs:
        if not isinstance(target, (str, bd.Face)):
            raise PMIError(f"annotation {id!r}: a ref is a face of the part -- a build123d Face, or a ref such as "
                           f"'f:plate.body.6' or 'face 7' -- not {type(target).__name__}")
    presentation = _presentation(presentation, id)
    return {"pmi": 1, "id": id, "kind": kind, "label": label, "presentation": presentation,
            "refs": [{"role": role, "target": target} for role, target in refs], **values}


def _general(spec: dict[str, Any]) -> bool:
    """Whether an annotation is its part's general profile (``general_profile``)."""
    return spec["kind"] == "geometric_tolerance" and bool(spec["geometric_tolerance"].get("general"))


def _presentation(presentation: Any, id: str) -> dict[str, Any] | None:
    """An annotation's presentation as ``place`` makes it, its anchor and offset checked as it checks
    them; None for none."""
    if presentation is None:
        return None
    if not isinstance(presentation, dict) or set(presentation) != {"anchor", "offset"}:
        raise PMIError(f"annotation {id!r}: a presentation is place(anchor, offset), not {presentation!r}")
    return _place(presentation["anchor"], presentation["offset"])


def _tolerance(tolerance: dict | None, id: str) -> dict | None:
    """A dimension's tolerance as ``plus_minus_tolerance`` or ``limits`` makes it: its closed keys,
    and its values checked again by the function of its type."""
    if tolerance is None:
        return None
    if not isinstance(tolerance, dict) or tolerance.get("type") not in _TOLERANCES:
        raise PMIUnsupported(f"dimension {id!r}: a tolerance is plus_minus_tolerance(...) or limits(...); fits and "
                             "general tolerances are not written yet")
    _closed(tolerance, _TOLERANCES[tolerance["type"]], f"dimension {id!r}'s tolerance")
    if tolerance["type"] == "plus_minus":
        return plus_minus_tolerance(tolerance["upper"], tolerance["lower"])
    return limits(tolerance["lower"], tolerance["upper"])


def _number(value: Any, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise PMIError(f"{what} is a finite number, not {value!r}")
    return float(value)


def _point(value: Any, what: str) -> list[float]:
    try:
        found = [_number(item, what) for item in value]
    except TypeError:
        found = []
    if len(found) != 3:
        raise PMIError(f"{what} is three numbers, millimetres, not {value!r}")
    return found




def unattached(run: Any, scope: str, tree: Any) -> list[str]:
    """The ids of the annotations the model ``scope``'s body, or a @memo function it called, gave to
    a shape its result does not hold (one a later operation replaced), each once."""
    held = {_text(entry) for _part, given in tree.pmi for entry in given}
    return sorted({json.loads(text)["id"] for text in run.pmi.get(scope, ()) if text not in held})


def _text(entry: dict[str, Any]) -> str:
    return json.dumps(entry, sort_keys=True, separators=(",", ":"))


# --- document time: harvest and resolve --------------------------------------------------------


def harvest(obj: Any, part: Any, held: dict[int, tuple[Any, tuple]], path: str) -> None:
    """The annotations ``obj`` holds, for the part prototype it is (``document.collect``): one
    geometry placed twice with two sets of annotations is refused by name."""
    given = obj.__dict__.get(PMI) if obj is not None else None
    if not given:
        return
    found = held.get(id(part))
    if found is not None and found[1] != given:
        raise PMIError(f"{path}: one part placed twice is given two sets of annotations; PMI is on the part, once")
    held[id(part)] = (part, given)


def refuse_assembly(obj: Any, path: str) -> None:
    if obj is not None and obj.__dict__.get(PMI):
        raise PMIUnsupported(f"{path}: an assembly is annotated; assembly-level PMI is not written yet: annotate "
                             "each part")


@dataclass
class Ref:
    role: str
    written: str | None  # None: a face a general profile covers, which the code does not write
    ordinal: int | None
    status: str
    candidates: list[int] = field(default_factory=list)
    problem: str | None = None


@dataclass
class Resolved:
    """One annotation as the part is built now: its refs resolved, its status, and its nominal."""

    spec: dict[str, Any]
    refs: list[Ref]
    status: str
    problem: str | None
    nominal: float | None = None


def resolve(tree: Any) -> list[tuple[Any, list[Resolved]]]:
    """Each annotated part of ``tree`` (named: ``Part.names``) with its annotations resolved
    against it, in the tree's order, made once per tree."""
    if tree.pmi_resolved is not None:
        return tree.pmi_resolved
    found = []
    for part, given in tree.pmi or ():
        names = list((part.names or {}).get("faces") or [])
        found.append((part, _resolved_part(_annotations(given), part.shape, names, {part.name, tree.root.name})))
    tree.pmi_resolved = found
    return found


def _resolved_part(given: Iterable[dict[str, Any]], shape: Any, names: list[str | None],
                   owners: set[str]) -> list[Resolved]:
    """A part's annotations (as the code gives them) resolved against its ``shape``, whose faces
    are named ``names`` by ordinal, in the document owned as ``owners`` name it; its general
    profile, where it is ``ok``, on every face the others leave (``_covered``). A tolerance whose
    frame names a datum that is not ``ok`` takes the worst such datum's status, and says which: it
    is measured from nothing the part has (``_from_datums``)."""
    given = list(given)
    faces = _faces(shape)
    letters = {entry["datum"]["letter"] for entry in given if entry["kind"] == "datum"}
    found = [_resolved(entry, faces, names, owners, letters) for entry in given]
    _from_datums(found)
    for item in found:
        if _general(item.spec) and item.status == "ok":
            item.refs = _covered(found, item.spec["geometric_tolerance"]["datums"], faces.Extent())
    return found


def _from_datums(items: list[Resolved]) -> None:
    """Each ``ok`` geometric tolerance of a part's resolved ``items`` whose frame names a datum not
    ``ok`` given the worst such datum's status, and a problem naming it: a frame is only as sound as
    its datums."""
    datums = {item.spec["datum"]["letter"]: item for item in items if item.spec["kind"] == "datum"}
    for item in items:
        if item.status != "ok" or item.spec["kind"] != "geometric_tolerance":
            continue
        broken = [datums[letter] for letter in item.spec["geometric_tolerance"]["datums"]
                  if letter in datums and datums[letter].status != "ok"]
        if broken:
            worst = max(broken, key=lambda datum: STATUSES.index(datum.status))
            item.status = worst.status
            item.problem = (f"datum {worst.spec['datum']['letter']} is {worst.status}: {worst.problem}"
                            if len(broken) == 1 else
                            f"datums {', '.join(datum.spec['datum']['letter'] for datum in broken)} are not ok "
                            f"(datum {worst.spec['datum']['letter']} is {worst.status}: {worst.problem})")


def _covered(items: list[Resolved], datums: list[str], count: int) -> list[Ref]:
    """The faces a part's general profile to ``datums`` covers, of the ``count`` it has: each that
    none of its resolved annotations ``items`` controls (``otherwise_controlled``, its faces spelled
    by ordinal) and that is no feature of a datum it names, which is controlled on its own (no
    face is profiled relative to itself), in the part's order. This build's annotations and
    geometry alone decide it."""
    controlled = otherwise_controlled([
        {"kind": item.spec["kind"], "status": item.status,
         **{key: item.spec[key] for key in ("dimension", "geometric_tolerance") if key in item.spec},
         "refs": [{"role": ref.role, "ref": f"face {ref.ordinal}"} for ref in item.refs]} for item in items])
    named = {f"face {ref.ordinal}" for item in items if item.spec["kind"] == "datum" and item.status == "ok"
             and item.spec["datum"]["letter"] in datums for ref in item.refs}
    left = controlled | named
    return [Ref("feature", None, at, "ok") for at in range(1, count + 1) if f"face {at}" not in left]


def otherwise_controlled(entries: list[dict[str, Any]]) -> set[str]:
    """The faces of ``entries`` (structure entries, ``entries``: their refs as they spell them,
    canonical where served) that have a size or location requirement of their own, which a general
    profile leaves to it: each ref of a plus-minus or limits dimension, and the feature of a
    position or of a profile not general. A basic dimension locates such a feature, counted as it
    is, and leaves the datum it starts from to that face's own control; a form control alone
    (flatness) or a datum leaves a face to the general profile; and an entry not ``ok`` controls
    nothing (it is linked to nothing). Pure: of ``entries`` alone."""
    controlled: set[str] = set()
    for entry in entries:
        if entry.get("status") != "ok":
            continue
        if entry["kind"] == "dimension":
            if (entry["dimension"].get("tolerance") or {}).get("type") in ("plus_minus", "limits"):
                controlled.update(ref["ref"] for ref in entry["refs"])
        elif entry["kind"] == "geometric_tolerance":
            given = entry["geometric_tolerance"]
            if given["characteristic"] == "position" or (given["characteristic"] == "surface_profile"
                                                         and not given.get("general")):
                controlled.update(ref["ref"] for ref in entry["refs"] if ref["role"] == "feature")
    return controlled


# The conflicts ``coverage`` says, in the order it says them.
CONFLICTS = ("unused_datum", "unlinked_note", "apart", "form_over_profile")
# Millimetres a measured size may pass a limit by, and two zones miss each other by: its own rounding.
_ROUNDING = 1e-6


def coverage(entries: list[dict[str, Any]], faces: Sequence[str]) -> dict[str, Any]:
    """One part's coverage, of its structure entries (``entries``, their refs canonical) and the
    canonical refs of every face it has (``faces``): ``uncovered``, the faces no requirement is on,
    sorted, and ``conflicts``, the requirements that cannot both hold or hold nothing, each
    ``{"kind", "ids", "problem"}``. A face is covered by a requirement that is ``ok`` and names it
    (``_requirement``): a toleranced dimension (plus-minus or limits) or a geometric tolerance, the
    general profile by the faces it covers (``otherwise_controlled`` leaves them to it), and every
    face by a general tolerance (``general_tolerance``: ISO 2768 holds every size and form nothing
    else tolerances); one another
    system wrote that this module does not hold whole (``unsupported``) covers its faces as any does,
    but a datum or a basic dimension. A basic dimension covers nothing: it locates the feature a
    position or a profile controls, and leaves the datum it starts from to that datum. A datum and a
    note cover nothing, and a general profile leaves out the datum features it names: give each its
    own control.
    The conflicts (``CONFLICTS``, in that order, each in the entries'): ``unused_datum``, a datum no
    tolerance's frame names; ``unlinked_note``, a flag note every face and annotation of which is
    broken (one link that holds keeps it linked; a general note names nothing to break); ``apart``, two
    toleranced dimensions of one type on the same faces whose zones do not meet; and
    ``form_over_profile``, a flatness wider than a surface profile on its face (its own, or the
    general one). Warned of, never failing a build. Pure: of its arguments alone."""
    ok = [entry for entry in entries if entry["status"] == "ok"]
    covered = {ref["ref"] for entry in ok if _requirement(entry) for ref in entry["refs"]}
    if any(_stated(entry) for entry in ok):
        covered = set(faces)  # ISO 2768: every size and form nothing else tolerances
    said: dict[str, list[dict[str, Any]]] = {kind: [] for kind in CONFLICTS}

    def say(kind: str, ids: list[str], problem: str) -> None:
        said[kind].append({"kind": kind, "ids": ids, "problem": problem})

    framed = {letter for entry in entries
              for letter in (entry.get("geometric_tolerance") or entry.get("values") or {}).get("datums") or ()}
    for entry in entries:
        if entry["kind"] == "datum" and entry["datum"]["letter"] not in framed:
            say("unused_datum", [entry["id"]], f"datum {entry['datum']['letter']} is in no tolerance's frame: name it "
                                               "where a requirement is measured from it, or remove it")
    statuses = {entry["id"]: entry["status"] for entry in entries if entry["kind"] != "note"}
    for entry in entries:
        if (entry["kind"] == "note" and not entry["note"]["general"]
                and all(ref["status"] != "ok" for ref in entry["refs"])
                and all(statuses.get(named) != "ok" for named in entry["note"]["annotations"])):
            say("unlinked_note", [entry["id"]], f"Note {entry['note']['number']} is linked to nothing: every face "
                                                "and annotation it names is broken; point it at what it is for, or "
                                                "remove it")
    zones = []
    for entry in ok:
        if entry["kind"] != "dimension":
            continue
        given = entry["dimension"]
        tolerance = given["tolerance"] or {}
        nominal = (given["nominal"] or {}).get("value")
        if tolerance.get("type") == "limits":
            zone = (tolerance["lower"], tolerance["upper"])
        elif tolerance.get("type") == "plus_minus" and nominal is not None:
            zone = (nominal + tolerance["lower"], nominal + tolerance["upper"])
        else:
            continue
        zones.append((entry, (given["type"], frozenset(ref["ref"] for ref in entry["refs"])), zone))
    for at, (first, key, zone) in enumerate(zones):
        for second, other, then in zones[at + 1:]:
            if other == key and max(zone[0], then[0]) > min(zone[1], then[1]) + _ROUNDING:
                say("apart", [first["id"], second["id"]],
                    f"two {key[0]}s of the same face{'s' if len(key[1]) > 1 else ''} whose zones do not meet, "
                    f"{_sizes(*zone)} and {_sizes(*then)}: no part holds both; keep the one meant")
    profiles = [entry for entry in ok if entry["kind"] == "geometric_tolerance"
                and entry["geometric_tolerance"]["characteristic"] == "surface_profile"]
    for entry in ok:
        if entry["kind"] != "geometric_tolerance" or entry["geometric_tolerance"]["characteristic"] != "flatness":
            continue
        value, on = entry["geometric_tolerance"]["value"], {ref["ref"] for ref in entry["refs"]}
        for profile in profiles:
            width = profile["geometric_tolerance"]["value"]
            if value > width and on & {ref["ref"] for ref in profile["refs"]}:
                say("form_over_profile", [entry["id"], profile["id"]],
                    f"flatness {_mm(value)} is wider than the surface profile {_mm(width)} on its face, which holds "
                    f"its form within {_mm(width)} already: make the flatness narrower than the profile, or remove it")
    return {"uncovered": sorted(set(faces) - covered),
            "conflicts": [found for kind in CONFLICTS for found in said[kind]]}


# What coverage suggests (``suggestions``) is read off these tables, millimetres, never invented.
# ISO 273: the clearance hole of each coarse metric fastener, its fine, medium and coarse series
# (their tolerance classes H12, H13 and H14).
CLEARANCE_HOLES = {1.6: (1.7, 1.8, 2.0), 2: (2.2, 2.4, 2.6), 2.5: (2.7, 2.9, 3.1), 3: (3.2, 3.4, 3.6),
                   4: (4.3, 4.5, 4.8), 5: (5.3, 5.5, 5.8), 6: (6.4, 6.6, 7.0), 8: (8.4, 9.0, 10.0),
                   10: (10.5, 11.0, 12.0), 12: (13.0, 13.5, 14.5), 16: (17.0, 17.5, 18.5), 20: (21.0, 22.0, 24.0),
                   24: (25.0, 26.0, 28.0)}
SERIES = (("fine", "H12"), ("medium", "H13"), ("coarse", "H14"))
# The coarse thread of each metric size (ISO 261): its pitch and the usual tap drill (ISO 2306).
TAP_DRILLS = {1.6: (0.35, 1.25), 2: (0.4, 1.6), 2.5: (0.45, 2.05), 3: (0.5, 2.5), 4: (0.7, 3.3), 5: (0.8, 4.2),
              6: (1.0, 5.0), 8: (1.25, 6.8), 10: (1.5, 8.5), 12: (1.75, 10.2), 16: (2.0, 14.0), 20: (2.5, 17.5),
              24: (3.0, 21.0)}
# ISO 286-1's standard tolerance grades, micrometres, for nominal sizes up to each bound (mm): a
# hole's H grade is +grade/0.
GRADE_BOUNDS = (3, 6, 10, 18, 30, 50, 80, 120, 180, 250)
GRADES = {"IT7": (10, 12, 15, 18, 21, 25, 30, 35, 40, 46), "IT12": (100, 120, 150, 180, 210, 250, 300, 350, 400, 460),
          "IT13": (140, 180, 220, 270, 330, 390, 460, 540, 630, 720),
          "IT14": (250, 300, 360, 430, 520, 620, 740, 870, 1000, 1150)}
# A size read off a table matches a measured one within this.
_TABLE = 0.005


def _grade(name: str, size: float) -> float | None:
    """ISO 286-1's grade ``name`` (``IT7``) for a nominal ``size``, mm; None beyond its table."""
    at = next((at for at, bound in enumerate(GRADE_BOUNDS) if size <= bound), None)
    return None if at is None else GRADES[name][at] / 1000


def suggestions(entries: list[dict[str, Any]], faces: Sequence[dict[str, Any]], *, material: bool) -> list[dict[str, Any]]:
    """What one part's requirements leave unsaid, each a question with a standard answer and why:
    the questions to put to the person who knows the part, never applied for them. Of its
    structure entries (``entries``), its faces (``faces``: each ``{"ref", "surface", "area"}`` and a
    cylinder's ``diameter`` and ``hole``, whether it bounds a hole) and whether it has a material.
    Each is ``{"kind", "faces", "question", "answer", "why"}``, the answer the call that says it
    (``material`` the part's attribute), in this order:

    - ``material``: a part with none (a shop makes it of something; it decides which tolerances
      are sensible);
    - ``datum``: a part with none, datum A on its largest flat face (the one it usually sits on);
    - ``general``: a part whose faces some requirement leaves uncovered and that has no general
      requirement, ISO 2768-mK (``general_tolerance``), the usual default for a machined part;
    - ``hole``: each hole no size requirement is on, by its diameter: an ISO 273 clearance hole
      (its series' H class; a position to the part's datums by the floating-fastener formula,
      hole less fastener), a coarse thread's tap drill (a note of the thread, 6H; a position by the
      fixed-fastener formula, half the mating medium clearance hole less the fastener), else a bore
      something fits in (H7, ISO 286).

    A default is a standard's, said with its standard: the answer is the person's. Pure."""
    found: list[dict[str, Any]] = []
    ok = [entry for entry in entries if entry["status"] == "ok"]

    def say(kind: str, on: list[str], question: str, answer: str, why: str) -> None:
        found.append({"kind": kind, "faces": on, "question": question, "answer": answer, "why": why})

    if not material:
        say("material", [], "What is the part made of?", "the part's material (bd_materials), before annotate()",
            "a shop makes and quotes it from its material, which also decides which tolerances are sensible")
    letters = sorted(entry["datum"]["letter"] for entry in ok if entry["kind"] == "datum")
    planes = [face for face in faces if face["surface"] == "plane"]
    if not letters and planes:
        largest = max(planes, key=lambda face: face["area"])
        say("datum", [largest["ref"]], "Which face is the part located and measured from?",
            f'datum("A", "{largest["ref"]}")',
            "the largest flat face is usually the one it sits or mounts on: primary datum A")
    frame = letters[:3] or ["A"]
    if coverage(entries, [face["ref"] for face in faces])["uncovered"] and not any(
            _stated(entry) or _general(entry) for entry in ok):
        say("general", [], "What holds the faces nothing else controls?",
            'general_tolerance("general", "ISO 2768-mK")',
            "ISO 2768-mK (medium sizes, K form) is the usual default for a machined part and holds every size "
            "and form nothing else tolerances; general_profile(...) says the same in ASME terms")
    sized = {ref["ref"] for entry in ok if entry["kind"] == "dimension" and entry["dimension"]["type"] == "diameter"
             for ref in entry["refs"]}
    datums = ", ".join(f'"{letter}"' for letter in frame)
    for number, face in enumerate((face for face in faces if face.get("hole") and face["ref"] not in sized), 1):
        ref, size, id = face["ref"], face["diameter"], f"hole-{number}"
        question = f"What is the {_mm(size)} mm hole for?"
        clearance = [(fastener, series, grade) for fastener, holes in CLEARANCE_HOLES.items()
                     for (series, grade), hole in zip(SERIES, holes) if abs(hole - size) <= _TABLE]
        tapped = [fastener for fastener, (_pitch, drill) in TAP_DRILLS.items() if abs(drill - size) <= _TABLE]
        if clearance:
            fastener, series, grade = clearance[0]
            upper, position = _grade("IT" + grade[1:], size), size - fastener
            others = "".join(f"; or the tap drill of M{_mm(other)}" for other in tapped)
            if (fit := _grade("IT7", size)) is not None:
                others += f"; or, where a pin or bearing fits in it, H7 +{_mm(fit)}/0"
            say("hole", [ref], question,
                f'dimensional_size("{id}-size", "{ref}", tolerance=plus_minus_tolerance({_mm(upper)}, 0)), '
                f'position_tolerance("{id}-position", "{ref}", {_mm(position)}, datums=[{datums}])',
                f"{_mm(size)} mm is ISO 273's {series} clearance hole for M{_mm(fastener)}: {grade} is "
                f"+{_mm(upper)}/0, and a floating M{_mm(fastener)} fastener assembles with a position of "
                f"{_mm(position)} (hole {_mm(size)} less fastener {_mm(fastener)}){others}")
        elif tapped:
            fastener = tapped[0]
            pitch, _drill = TAP_DRILLS[fastener]
            position = (CLEARANCE_HOLES[fastener][1] - fastener) / 2
            say("hole", [ref], question,
                f'note("{id}-thread", "M{_mm(fastener)}x{_mm(pitch)}-6H", faces=["{ref}"]), '
                f'position_tolerance("{id}-position", "{ref}", {_mm(position)}, datums=[{datums}])',
                f"{_mm(size)} mm is the tap drill of M{_mm(fastener)}x{_mm(pitch)}: a tapped hole, its thread "
                f"6H (ISO 965), and a fixed M{_mm(fastener)} fastener in it assembles with a position of "
                f"{_mm(position)} (half its medium clearance hole {_mm(CLEARANCE_HOLES[fastener][1])} less "
                f"{_mm(fastener)})")
        elif (upper := _grade("IT7", size)) is not None:
            say("hole", [ref], question,
                f'dimensional_size("{id}-size", "{ref}", tolerance=plus_minus_tolerance({_mm(upper)}, 0))',
                f"{_mm(size)} mm is no clearance hole or tap drill of ISO 273: a bore a pin or bearing fits in "
                f"is usually H7 (ISO 286), +{_mm(upper)}/0; a looser hole wants less")
    return found


def _requirement(entry: dict[str, Any]) -> bool:
    """Whether an entry is a requirement on the faces its refs name, which ``coverage`` counts them
    covered by: a dimension given a tolerance (plus-minus or limits), a geometric tolerance, or
    another system's annotation listed ``unsupported`` but a datum or a basic dimension. A basic
    dimension is none: it locates the feature a position or a profile controls, which covers it, and
    leaves the datum it starts from to that datum's own control; nor is a datum or a note."""
    if entry["kind"] == "dimension":
        return (entry["dimension"]["tolerance"] or {}).get("type") in ("plus_minus", "limits")
    if entry["kind"] == "unsupported":
        return (entry["xcaf_type"] != "XCAFDimTolObjects_DatumObject"
                and not (entry.get("values") or {}).get("basic"))
    return entry["kind"] == "geometric_tolerance"


def outside_limits(entries: list[dict[str, Any]]) -> list[str]:
    """Each ``ok`` limits dimension of a structure's ``pmi`` (``entries``) whose measured nominal lies
    outside its limits, said: a size the model does not have, which a build refuses (law 17), as a
    mechanism state outside its joint's range is."""
    found = []
    for entry in entries:
        given = entry.get("dimension") or {}
        tolerance, nominal = given.get("tolerance") or {}, (given.get("nominal") or {}).get("value")
        if (entry["status"] == "ok" and tolerance.get("type") == "limits" and nominal is not None
                and not tolerance["lower"] - _ROUNDING <= nominal <= tolerance["upper"] + _ROUNDING):
            found.append(f"{entry['id']}: the {given['type']} measures {_mm(nominal)} mm, outside its limits "
                         f"{_sizes(tolerance['lower'], tolerance['upper'])}: model it within them, or correct the "
                         "limits")
    return found


def _mm(value: float) -> str:
    """A length in millimetres as a problem says it: to four decimals at most (``10``, ``9.95``)."""
    return f"{value:.4f}".rstrip("0").rstrip(".")


def _sizes(lower: float, upper: float) -> str:
    """The least size and the greatest as the viewer writes limits (``pmiToleranceText``): at one
    number of places, what the more exact needs (four at most), an en dash between (``9.90–9.95``)."""
    places = max(len(_mm(value).partition(".")[2]) for value in (lower, upper))
    return f"{lower:.{places}f}–{upper:.{places}f}"


def _resolved(spec: dict[str, Any], faces: Any, names: list[str | None], owners: set[str],
              letters: set[str]) -> Resolved:
    """One annotation against the part as built: each ref, then the faces it names against the
    faces its kind stands on (``_SURFACES``), then its nominal measured."""
    refs = [_ref(given, faces, names, owners) for given in spec["refs"]]
    nominal = None
    problem = next((ref.problem for ref in refs if ref.status != "ok"), None)
    if all(ref.status == "ok" for ref in refs):
        surfaces = [_surface(faces.FindKey(ref.ordinal)) for ref in refs]
        what = _what(spec)
        wanted = _SURFACES[what]
        for ref, surface in zip(refs, surfaces):
            if surface[0] not in wanted:
                ref.status = "invalid"
                ref.problem = (f"{ref.written} is a {surface[0]} face; a {what.replace('_', ' ')} is on a "
                               f"{' or '.join(wanted)} face")
        if what in ("surface_profile", "note"):
            for at, ref in enumerate(refs):
                earlier = next((other for other in refs[:at] if other.ordinal == ref.ordinal), None)
                if earlier is not None:
                    ref.status = "invalid"
                    ref.problem = (f"{ref.written} names face {ref.ordinal}, as {earlier.written} does: a "
                                   f"{what.replace('_', ' ')} is on each face once")
        if all(ref.status == "ok" for ref in refs):
            if what == "diameter":
                nominal = 2.0 * surfaces[0][1]["radius"]
            elif what in ("distance", "basic"):
                nominal, why = _separation([faces.FindKey(ref.ordinal) for ref in refs], [ref.written for ref in refs])
                if why is not None:
                    refs[1].status, refs[1].problem = "invalid", why
        problem = next((ref.problem for ref in refs if ref.status != "ok"), None)
    status = _worst(ref.status for ref in refs)
    if status == "ok" and spec["kind"] == "geometric_tolerance":
        undefined = [letter for letter in spec["geometric_tolerance"]["datums"] if letter not in letters]
        if undefined:
            status, problem = "invalid", f"datum {', '.join(undefined)} is not defined on this part"
    return Resolved(spec, refs, status, problem, nominal)


def _what(spec: dict[str, Any]) -> str:
    """What an annotation is, as ``_SURFACES`` knows it: a datum, a note, a dimension's type
    (``basic`` for a basic one) or a tolerance's characteristic."""
    if spec["kind"] in ("datum", "note"):
        return spec["kind"]
    if spec["kind"] == "dimension":
        return "basic" if spec["dimension"].get("basic") else spec["dimension"]["type"]
    return spec["geometric_tolerance"]["characteristic"]


def _owner_label(segment: Any, owners: set[str]) -> str:
    """The label an owner's last segment names: ``LABEL.N`` is the N-th ``LABEL`` where no owner
    bears the text whole, as the grammar reads it (``refs._group``)."""
    from cadgen.engine import refs as grammar

    numbered = None if segment.quoted or segment.text in owners else grammar._INDEXED.fullmatch(segment.text)
    return numbered[1] if numbered else segment.text


def _ref(given: dict[str, Any], faces: Any, names: list[str | None], owners: set[str]) -> Ref:
    from cadgen.engine import refs as grammar

    role, written = given["role"], given["written"]
    count = faces.Extent()
    if given["face"] is not None:
        ordinal = given["face"]
        if not 1 <= ordinal <= count:
            return Ref(role, written, None, "missing", problem=f"{written} is not a face of the annotated part")
        return Ref(role, written, ordinal, "ok")
    try:
        file, selectors = grammar.parse(written)
    except grammar.RefError as error:
        return Ref(role, written, None, "invalid", problem=str(error))
    if file is not None or len(selectors) != 1 or selectors[0].element is None or selectors[0].kind != "face":
        return Ref(role, written, None, "invalid", problem=f"{written}: a PMI ref names one face of the annotated part")
    selector = selectors[0]
    if selector.owner:
        if _owner_label(selector.owner[-1], owners) not in owners:
            return Ref(role, written, None, "invalid", problem=f"{written}: {'/'.join(map(str, selector.owner))} is "
                                                               f"not the annotated part ({sorted(owners)[0]})")
    element = selector.element
    if isinstance(element, tuple):
        ordinal = element[1]
        if not 1 <= ordinal <= count:
            return Ref(role, written, None, "missing", problem=f"the part has no face {ordinal} (it has {count})")
        return Ref(role, written, ordinal, "ok")
    held = [at for at, text in enumerate(names, 1) if text == element and at <= count]
    if len(held) == 1:
        return Ref(role, written, held[0], "ok")
    if len(held) > 1:
        return Ref(role, written, None, "ambiguous", held,
                   f"{written} names {len(held)} faces: {', '.join(f'face {at}' for at in held)}")
    said = f"the part has no face {element}"
    atom = element.split(":", 1)[1].split(";", 1)[0]
    if "~" not in atom:  # a folded name: its digest says nothing of what it became (``refs._missing``)
        now = sorted({text for text in names if text and text.split(":", 1)[1].split(";", 1)[0] == atom})
        said += f": {atom} is now {', '.join(now)}" if now else f": no face is made of {atom} now"
    return Ref(role, written, None, "missing", problem=said)


def _datums_first(items: list[Resolved]) -> list[Resolved]:
    """A part's annotations in the order its document holds them: its datums, then the rest."""
    return [item for item in items if item.spec["kind"] == "datum"] + [item for item in items if item.spec["kind"] != "datum"]


def _separation(shapes: list[Any], written: list[str]) -> tuple[float | None, str | None]:
    """The distance between two faces as a location dimension measures it: between parallel
    planes, from a plane to a cylinder's axis parallel to it, or between parallel axes; or why
    there is none."""
    import numpy as np

    held = []
    for shape in shapes:
        kind, found = _surface(shape)
        held.append((kind, found if kind == "plane" else _axis(shape)))
    (first_kind, first), (second_kind, second) = held
    if first_kind == "plane" and second_kind == "plane":
        normal, other = np.array(first["normal"]), np.array(second["normal"])
        if abs(abs(float(normal @ other)) - 1.0) > 1e-9:
            return None, f"{written[0]} and {written[1]} are not parallel planes"
        found = abs(float((np.array(second["origin"]) - np.array(first["origin"])) @ normal))
        return (found, None) if found > 1e-9 else (None, f"{written[0]} and {written[1]} lie in one plane")
    if first_kind == "cylinder" and second_kind == "cylinder":
        point, direction = np.array(first["point"]), np.array(first["direction"])
        if abs(abs(float(direction @ np.array(second["direction"]))) - 1.0) > 1e-9:
            return None, f"the axes of {written[0]} and {written[1]} are not parallel"
        found = float(np.linalg.norm(np.cross(np.array(second["point"]) - point, direction)))
        return (found, None) if found > 1e-9 else (None, f"{written[0]} and {written[1]} share one axis")
    plane, axis = (first, second) if first_kind == "plane" else (second, first)
    normal = np.array(plane["normal"])
    if abs(float(normal @ np.array(axis["direction"]))) > 1e-9:
        axis_of, plane_of = (written[1], written[0]) if first_kind == "plane" else (written[0], written[1])
        return None, f"the axis of {axis_of} is not parallel to the plane {plane_of}"
    found = abs(float((np.array(axis["point"]) - np.array(plane["origin"])) @ normal))
    return (found, None) if found > 1e-9 else (None, f"the axis lies in the plane {written[0]}")


def _axis(face: Any) -> dict[str, Any]:
    """A cylindrical face's axis: a point on it and its unit direction."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.TopoDS import TopoDS

    axis = BRepAdaptor_Surface(TopoDS.Face(face)).Cylinder().Axis()
    point, direction = axis.Location(), axis.Direction()
    return {"point": (point.X(), point.Y(), point.Z()), "direction": (direction.X(), direction.Y(), direction.Z())}


def _worst(statuses: Iterable[str]) -> str:
    found = "ok"
    for status in statuses:
        if STATUSES.index(status) > STATUSES.index(found):
            found = status
    return found


def _faces(shape: Any) -> Any:
    """A part's faces by their ordinals, as the ref grammar numbers them (``_map``)."""
    return _map(shape, "face")


def _map(shape: Any, kind: str) -> Any:
    """A shape's elements of ``kind`` (``face``, ``edge``, ``vertex``) by their ordinals: the kernel's
    indexed map, as the ref grammar and the document's sub-shape labels number them."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.TopExp import TopExp
    from OCP.collections import IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher

    found = IndexedMap_TopoDS_Shape_TopTools_ShapeMapHasher()
    TopExp.MapShapes_s(shape, {"face": TopAbs_FACE, "edge": TopAbs_EDGE, "vertex": TopAbs_VERTEX}[kind], found)
    return found


def _surface(face: Any) -> tuple[str, dict[str, Any]]:
    """A face's surface: ``plane`` (origin, unit normal), ``cylinder`` (radius, axis), or another
    kind by name."""
    from OCP.BRepAdaptor import BRepAdaptor_Surface
    from OCP.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
    from OCP.TopoDS import TopoDS

    adaptor = BRepAdaptor_Surface(TopoDS.Face(face))
    kind = adaptor.GetType()
    if kind == GeomAbs_Plane:
        plane = adaptor.Plane()
        origin, normal = plane.Location(), plane.Axis().Direction()
        return "plane", {"origin": (origin.X(), origin.Y(), origin.Z()), "normal": (normal.X(), normal.Y(), normal.Z())}
    if kind == GeomAbs_Cylinder:
        return "cylinder", {"radius": adaptor.Cylinder().Radius()}
    return str(kind.name).replace("GeomAbs_", "").lower(), {}


def signature(tree: Any) -> tuple:
    """What a tree's annotations are, for the build's signature: a change to one remakes the document."""
    return tuple(_text({"part": part.name, "pmi": list(given)}) for part, given in tree.pmi or ())


def problems(tree: Any) -> list[dict[str, Any]]:
    """Every annotation of ``tree`` that is not ``ok``: its part, id, status and why."""
    return [{"part": part.name, "id": item.spec["id"], "status": item.status, "problem": item.problem}
            for part, items in resolve(tree) for item in items if item.status != "ok"]


# --- the XCAF document -------------------------------------------------------------------------


def write(doc: Any, tree: Any, label_of: Any) -> None:
    """The tree's annotations into ``doc``'s GD&T tool, each part's in its order, datums first
    (a tolerance's frame names them), then its notes into the notes tool, in the code's order
    (``_note``) and its views into the views tool, in the code's order (``_view``); and the GD&T
    of the document the tree was read from (``Tree.pmi_source``: ``copy``). ``label_of(part)`` is
    the part's shape label."""
    if tree.pmi_source is not None:
        loaded, parts = tree.pmi_source
        copy(doc, loaded, lambda index: label_of(parts[index]))
    if not tree.pmi:
        return
    from OCP.Standard import Standard_GUID
    from OCP.TCollection import TCollection_AsciiString
    from OCP.TDataStd import TDataStd_AsciiString
    from OCP.TDF import TDF_Label, TDF_Reference
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool

    tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    guid = Standard_GUID(EXTRA_GUID)
    for part, items in resolve(tree):
        label = label_of(part)
        faces = _faces(XCAFDoc_ShapeTool.GetShape_s(label))

        def sub(ordinal: int) -> Any:
            found = TDF_Label()
            face = faces.FindKey(ordinal)
            if not shapes.FindSubShape(label, face, found):
                shapes.AddSubShape(label, face, found)
            return found

        datums: dict[str, Any] = {}
        made: dict[str, Any] = {}  # each annotation's GD&T label, by id: what a note names
        positions = {letter: at for item in items if item.spec["kind"] == "geometric_tolerance"
                     for at, letter in enumerate(item.spec["geometric_tolerance"]["datums"], 1)}
        ordered = _datums_first(items)
        for item in ordered:
            spec = item.spec
            if spec["kind"] == "note":
                continue
            linked = _on_faces(item)
            refs = [sub(ref.ordinal) for ref in item.refs] if linked else []
            if spec["kind"] == "datum":
                at = tool.AddDatum()
                # Placed only where a frame names it: OCCT's writer writes a datum no frame names as
                # nothing, and fails the transfer on a callout of nothing.
                place = positions.get(spec["datum"]["letter"], 0)
                _datum(at, spec["datum"]["letter"], place, spec["id"], spec["presentation"] if linked and place else None)
                if linked:
                    sequence = Sequence_TDF_Label()
                    sequence.Append(refs[0])
                    tool.SetDatum(sequence, at)
                datums[spec["datum"]["letter"]] = at
            elif spec["kind"] == "dimension":
                at = tool.AddDimension()
                _dimension(at, spec, item.nominal, spec["presentation"] if linked else None)
                if linked and len(refs) == 1:
                    tool.SetDimension(refs[0], at)
                elif linked:
                    tool.SetDimension(refs[0], refs[1], at)
            else:
                at = tool.AddGeomTolerance()
                _tolerance_object(at, spec, spec["presentation"] if linked else None)
                if linked:
                    sequence = Sequence_TDF_Label()
                    for ref in refs:
                        sequence.Append(ref)
                    tool.SetGeomTolerance(sequence, at)
                    for letter in spec["geometric_tolerance"]["datums"]:
                        tool.SetDatumToGeomTol(datums[letter], at)
            TDataStd_AsciiString.Set_s(at, guid, TCollection_AsciiString(_text(_extra(item))))
            TDF_Reference.Set_s(at, label)
            made[spec["id"]] = at
        for item in items:
            if item.spec["kind"] == "note":
                at = _note(XCAFDoc_DocumentTool.NotesTool_s(doc.Main()), item, label, made)
                TDataStd_AsciiString.Set_s(at, guid, TCollection_AsciiString(_text(_extra(item))))
                TDF_Reference.Set_s(at, label)
        for given in _views(part.pmi):
            at = _view(doc, given, label, made)
            TDataStd_AsciiString.Set_s(at, guid, TCollection_AsciiString(_text(_view_extra(given))))
            TDF_Reference.Set_s(at, label)


def _note(notes: Any, item: Resolved, label: Any, made: dict[str, Any]) -> Any:
    """A note as an XCAF comment (``NOTE_USER``, no timestamp) in ``notes``, the notes tool; its
    label. A flag note is attached to each face it is on, where it is ``ok`` (the sub-shape index
    is the face's ordinal in its part's face map, as the ref grammar numbers faces), and to the
    GD&T label of each annotation it names (``made``, by id); a general note to its part's shape
    ``label``."""
    from OCP.TCollection import TCollection_ExtendedString

    spec = item.spec
    found = notes.CreateComment(TCollection_ExtendedString(NOTE_USER, True), TCollection_ExtendedString("", True),
                                TCollection_ExtendedString(spec["note"]["text"], True)).Label()
    if _on_faces(item):
        for ref in item.refs:
            notes.AddNoteToSubshape(found, label, ref.ordinal)
    for named in spec["note"]["annotations"]:
        notes.AddNote(found, made[named])
    if not spec["refs"] and not spec["note"]["annotations"]:
        notes.AddNote(found, label)
    return found


def _view(doc: Any, given: dict[str, Any], label: Any, made: dict[str, Any]) -> Any:
    """A view (``view``) as an XCAF view in ``doc``'s views tool; its label. Parallel, looking along
    the camera's direction reversed (XCAF's view direction is the one looked along; the code's, the
    way to the eye), its eye the part's box centre moved toward the eye by the box's diagonal, its
    window that diagonal each way and its zoom 1, each set (the same code makes the same bytes); on
    its part's shape ``label``, with the GD&T labels (``made``, by id) it shows, in its order (all
    of them, the document's order, where it names none), and its section as an XCAF clipping plane
    named for it, its normal into the half the Clip keeps, capped as the Clip caps. The notes it
    shows are its cadgen attribute's alone: OCCT's ``SetView`` files a view's notes under its
    clipping-plane link, where a reader would take them for planes."""
    from OCP.Bnd import Bnd_Box
    from OCP.BRepBndLib import BRepBndLib
    from OCP.gp import gp_Dir, gp_Pln, gp_Pnt
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ShapeTool, XCAFDoc_View
    from OCP.XCAFView import XCAFView_Object, XCAFView_ProjectionType_Parallel

    tool = XCAFDoc_DocumentTool.ViewTool_s(doc.Main())
    camera = _camera_of(given["camera"])
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(XCAFDoc_ShapeTool.GetShape_s(label), box, False, False)
    low, high = box.CornerMin(), box.CornerMax()
    low_at, high_at = (low.X(), low.Y(), low.Z()), (high.X(), high.Y(), high.Z())
    diagonal = math.sqrt(sum((b - a) ** 2 for a, b in zip(low_at, high_at)))
    eye = [(a + b) / 2 + side * diagonal for a, b, side in zip(low_at, high_at, camera["direction"])]
    found = XCAFView_Object()
    found.SetName(_ascii(given["name"]))
    found.SetType(XCAFView_ProjectionType_Parallel)
    found.SetProjectionPoint(gp_Pnt(*eye))
    found.SetViewDirection(gp_Dir(*(-side for side in camera["direction"])))
    found.SetUpDirection(gp_Dir(*camera["up"]))
    found.SetZoomFactor(1.0)
    found.SetWindowHorizontalSize(diagonal)
    found.SetWindowVerticalSize(diagonal)
    at = tool.AddView()
    XCAFDoc_View.Set_s(at).SetObject(found)
    sequences = {"shapes": Sequence_TDF_Label(), "gdts": Sequence_TDF_Label(), "planes": Sequence_TDF_Label()}
    sequences["shapes"].Append(label)
    for id in made if given["shows"] is None else given["shows"]:
        if id in made:
            sequences["gdts"].Append(made[id])
    cut = given["section"]
    if cut is not None:
        axis = "xyz".index(cut["axis"])
        point, normal = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]
        point[axis], normal[axis] = cut["at"], 1.0 if cut["invert"] else -1.0
        sequences["planes"].Append(XCAFDoc_DocumentTool.ClippingPlaneTool_s(doc.Main()).AddClippingPlane(
            gp_Pln(gp_Pnt(*point), gp_Dir(*normal)), TCollection_ExtendedString(given["name"], True), True))
    tool.SetView(sequences["shapes"], sequences["gdts"], sequences["planes"], at)
    return at


def _view_extra(given: dict[str, Any]) -> dict[str, Any]:
    """The cadgen attribute beside a view's XCAF view (see the module): the view as the code gave it,
    its camera as written (a preset's name, or ``camera``'s two unit vectors)."""
    return {"schema": SCHEMA, "kind": "view", **{key: given[key] for key in
                                                ("name", "label", "camera", "shows", "section", "place")}}


def _camera_of(written: Any) -> dict[str, Any]:
    """A view's camera as served: its preset's name or None, its direction (from the part toward the
    eye) and up, unit vectors in the part's frame (a preset's from the stills' own table,
    ``render/presets.py``), and its projection, orthographic."""
    from cadgen.engine.render.presets import PRESETS

    if isinstance(written, str):
        side, up = PRESETS[written]
        found = {"direction": _unit(side, "a preset's direction"), "up": _unit(up, "a preset's up")}
    else:
        found = {"direction": list(written["direction"]), "up": list(written["up"])}
    return {"preset": written if isinstance(written, str) else None, **found, "projection": "orthographic"}


def _on_faces(item: Resolved) -> bool:
    """Whether an annotation is linked to the faces it is on: ``ok``, and on one or more (a general
    profile covering none is linked to nothing, as one not ``ok`` is)."""
    return item.status == "ok" and bool(item.refs)


def _extra(item: Resolved) -> dict[str, Any]:
    """The cadgen attribute's JSON (see the module): what the code says that XCAF has no place for.
    A note's text is XCAF's (its comment), linked or not: beside it, what it names as written."""
    spec = item.spec
    if spec["kind"] == "note":
        return {"schema": SCHEMA, "id": spec["id"], "kind": "note", "label": spec["label"],
                "presentation": spec["presentation"], "refs": spec["refs"],
                "annotations": list(spec["note"]["annotations"]),
                "general_tolerance": spec["note"]["general_tolerance"]}
    found = {"schema": SCHEMA, "id": spec["id"], "kind": spec["kind"], "label": spec["label"],
             "presentation": spec["presentation"], "refs": spec["refs"],
             # What an unlinked annotation meant, for a reader: XCAF links values to geometry alone.
             "unlinked": None if _on_faces(item) else
             {key: spec[key] for key in ("dimension", "datum", "geometric_tolerance") if key in spec}}
    if _general(spec):
        found["general"] = True  # the part's general profile: its faces are computed, not written
    return found


def _ascii(text: str) -> Any:
    from OCP.TCollection import TCollection_HAsciiString

    return TCollection_HAsciiString(text)


def _datum(label: Any, letter: str, place: int, id: str, presentation: dict | None) -> None:
    from OCP.XCAFDimTolObjects import XCAFDimTolObjects_DatumObject
    from OCP.XCAFDoc import XCAFDoc_Datum

    found = XCAFDimTolObjects_DatumObject()
    found.SetName(_ascii(letter))
    found.SetSemanticName(_ascii(id))
    if place:
        # A datum's place in the frames that name it: the writer writes a datum system of the
        # datums with a place, in its order, and none without.
        found.SetPosition(place)
    _present(found, presentation, id)
    XCAFDoc_Datum.Set_s(label).SetObject(found)


def _dimension(label: Any, spec: dict[str, Any], nominal: float | None, presentation: dict | None) -> None:
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_DimensionObject,
                                        XCAFDimTolObjects_DimensionType_Location_LinearDistance,
                                        XCAFDimTolObjects_DimensionType_Size_Diameter)
    from OCP.XCAFDoc import XCAFDoc_Dimension

    found = XCAFDimTolObjects_DimensionObject()
    found.SetSemanticName(_ascii(spec["id"]))
    kind = spec["dimension"]["type"]
    found.SetType(XCAFDimTolObjects_DimensionType_Size_Diameter if kind == "diameter"
                  else XCAFDimTolObjects_DimensionType_Location_LinearDistance)
    found.SetValue(nominal if nominal is not None else 0.0)
    if spec["dimension"].get("basic"):
        # CAx-IF's type 1 dimension modifier: a descriptive item 'dimensional note' of description
        # 'theoretical' in the dimension's shape_dimension_representation, which is what the
        # writer makes of an XCAF description (and its reader makes one of again).
        found.AddDescription(_ascii(THEORETICAL[1]), _ascii(THEORETICAL[0]))
    tolerance = spec["dimension"]["tolerance"]
    if tolerance is not None and nominal is not None:
        if tolerance["type"] == "limits":
            # XCAF holds limits as the dimension's two values, in place of its nominal (see the module).
            found.SetLowerBound(tolerance["lower"])
            found.SetUpperBound(tolerance["upper"])
        else:
            # XCAF's lower deviation is a magnitude the writer negates (see the module): -lower.
            found.SetLowerTolValue(-tolerance["lower"])
            found.SetUpperTolValue(tolerance["upper"])
    _present(found, presentation, spec["id"])
    XCAFDoc_Dimension.Set_s(label).SetObject(found)


def _xcaf_characteristics() -> dict[str, Any]:
    """XCAF's type of each characteristic held (``flatness_tolerance``, ``position_tolerance``,
    ``surface_profile_tolerance``): what a tolerance is written as and read back by."""
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_GeomToleranceType_Flatness,
                                        XCAFDimTolObjects_GeomToleranceType_Position,
                                        XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface)

    return {"flatness": XCAFDimTolObjects_GeomToleranceType_Flatness,
            "position": XCAFDimTolObjects_GeomToleranceType_Position,
            "surface_profile": XCAFDimTolObjects_GeomToleranceType_ProfileOfSurface}


def _tolerance_object(label: Any, spec: dict[str, Any], presentation: dict | None) -> None:
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_GeomToleranceObject,
                                        XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
    from OCP.XCAFDoc import XCAFDoc_GeomTolerance

    given = spec["geometric_tolerance"]
    found = XCAFDimTolObjects_GeomToleranceObject()
    found.SetSemanticName(_ascii(spec["id"]))
    found.SetType(_xcaf_characteristics()[given["characteristic"]])
    found.SetValue(given["value"])
    if given["zone"] == "diameter":
        found.SetTypeOfValue(XCAFDimTolObjects_GeomToleranceTypeValue_Diameter)
    _present(found, presentation, spec["id"])
    XCAFDoc_GeomTolerance.Set_s(label).SetObject(found)


def _present(found: Any, presentation: dict | None, id: str) -> None:
    """An annotation's place (``place``) on its XCAF object, as AP242's presentation of it: its text
    point (the anchor moved by the offset), an annotation plane through that point, and a leader from
    the anchor to it, the callout named by the annotation's id. OCCT's STEP writer writes a callout
    only where an object has a presentation shape, so an annotation whose offset is nil (no leader to
    draw) is written with none, as one with no place is. Graphic, never semantic: a reader that draws
    PMI puts the annotation where the viewer does, and nothing it means changes."""
    if presentation is None:
        return
    from OCP.BRepBuilderAPI import BRepBuilderAPI_MakeEdge
    from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt

    anchor = presentation["anchor"]
    text = [at + by for at, by in zip(anchor, presentation["offset"])]
    if math.dist(anchor, text) <= _ROUNDING:
        return
    # The plane the text lies in: the leader in it, its normal the axis the leader is least along.
    leader = [by / math.dist(anchor, text) for by in presentation["offset"]]
    normal = min(((0.0, 0.0, 1.0), (0.0, 1.0, 0.0), (1.0, 0.0, 0.0)),
                 key=lambda axis: abs(sum(a * b for a, b in zip(axis, leader))))
    found.SetPointTextAttach(gp_Pnt(*text))
    found.SetPlane(gp_Ax2(gp_Pnt(*text), gp_Dir(*normal)))
    found.SetPresentation(BRepBuilderAPI_MakeEdge(gp_Pnt(*anchor), gp_Pnt(*text)).Edge(), _ascii(id))


def _presentation_of(found: Any) -> dict[str, Any] | None:
    """An XCAF object's place as ``place`` makes one, where a file gives its text a point: a callout
    drawn as one straight line (a leader, as ``_present`` writes it) from its end away from the text,
    any other (another system's lettering) at its text point, with no offset. None where none is given."""
    # XCAF's dimension says it as HasTextPoint, its datum and tolerance as HasPointText.
    if not (found.HasTextPoint() if hasattr(found, "HasTextPoint") else found.HasPointText()):
        return None
    from OCP.BRep import BRep_Tool
    from OCP.BRepAdaptor import BRepAdaptor_Curve
    from OCP.GeomAbs import GeomAbs_Line
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp, TopExp_Explorer
    from OCP.TopoDS import TopoDS

    point = found.GetPointTextAttach()
    text = [_as_held(point.X()), _as_held(point.Y()), _as_held(point.Z())]
    drawn, edges = found.GetPresentation(), []
    explorer = TopExp_Explorer() if drawn.IsNull() else TopExp_Explorer(drawn, TopAbs_EDGE)
    while explorer.More():
        edges.append(TopoDS.Edge(explorer.Current()))
        explorer.Next()
    if len(edges) != 1 or BRepAdaptor_Curve(edges[0]).GetType() != GeomAbs_Line:
        return _place(text, (0.0, 0.0, 0.0))
    ends = [BRep_Tool.Pnt_s(TopExp.FirstVertex_s(edges[0])), BRep_Tool.Pnt_s(TopExp.LastVertex_s(edges[0]))]
    far = max(ends, key=lambda end: math.dist((end.X(), end.Y(), end.Z()), text))
    anchor = [_as_held(far.X()), _as_held(far.Y()), _as_held(far.Z())]
    return _place(anchor, [_as_held(at - by) for at, by in zip(text, anchor)])


def copy(doc: Any, loaded: Any, label_of: Callable[[int], Any]) -> None:
    """The GD&T of a document read from a file another system wrote (``loaded``, a
    ``document.Loaded``) copied as read into ``doc``, the document made of it again (an xbf of a
    STEP): every datum, dimension and geometric tolerance as XCAF holds it, each linked to the same
    faces, edges and points of the same parts (``label_of(index)``: prototype ``index``'s label in
    ``doc``), a tolerance to the same datums. One the file links to anything else (an occurrence's
    face, a whole part) is copied linked to nothing, as reading the file says it is (``missing``):
    its values kept, nothing approximated."""
    from OCP.TDF import TDF_Label
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_DatumObject, XCAFDimTolObjects_DimensionObject,
                                        XCAFDimTolObjects_GeomToleranceObject)
    from OCP.XCAFDoc import (XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_DocumentTool, XCAFDoc_GeomTolerance,
                             XCAFDoc_ShapeTool)

    from cadgen.engine.document import _entry

    source = _tool(loaded.doc)
    if source is None:
        return
    tool = XCAFDoc_DocumentTool.DimTolTool_s(doc.Main())
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    by_entry = {prototype.entry: prototype for prototype in loaded.prototypes}
    theirs: dict[tuple[int, str], Any] = {}  # each prototype's elements, in the file's document and in ``doc``
    ours: dict[tuple[int, str], Any] = {}

    def placed(label: Any) -> Any:
        """A ref label's element as ``doc`` holds it, a sub-shape label of its part; None for none."""
        hit = _element(label, by_entry, theirs)
        if hit is None:
            return None
        index, kind, ordinal = hit
        part = label_of(index)
        if (index, kind) not in ours:
            ours[(index, kind)] = _map(XCAFDoc_ShapeTool.GetShape_s(part), kind)
        element = ours[(index, kind)].FindKey(ordinal)
        found = TDF_Label()
        if not shapes.FindSubShape(part, element, found):
            shapes.AddSubShape(part, element, found)
        return found

    def linked(label: Any) -> list[Any]:
        """The elements a label links to, first and second, as ``doc``'s labels: none where one of
        them has no place there."""
        found = []
        for sequence in _linked(source, label):
            labels = Sequence_TDF_Label()
            for at in range(1, sequence.Length() + 1):
                hit = placed(sequence.Value(at))
                if hit is None:
                    return [Sequence_TDF_Label(), Sequence_TDF_Label()]
                labels.Append(hit)
            found.append(labels)
        return found

    datums: dict[str, Any] = {}
    for label in _labels(source, "datum"):
        at = tool.AddDatum()
        XCAFDoc_Datum.Set_s(at).SetObject(XCAFDimTolObjects_DatumObject(XCAFDoc_Datum.Set_s(label).GetObject()))
        first, _second = linked(label)
        if first.Length():
            tool.SetDatum(first, at)
        datums[_entry(label)] = at
    for label in _labels(source, "dimension"):
        at = tool.AddDimension()
        XCAFDoc_Dimension.Set_s(at).SetObject(
            XCAFDimTolObjects_DimensionObject(XCAFDoc_Dimension.Set_s(label).GetObject()))
        first, second = linked(label)
        if first.Length():
            tool.SetDimension(first, second, at)
    for label in _labels(source, "geometric_tolerance"):
        at = tool.AddGeomTolerance()
        XCAFDoc_GeomTolerance.Set_s(at).SetObject(
            XCAFDimTolObjects_GeomToleranceObject(XCAFDoc_GeomTolerance.Set_s(label).GetObject()))
        first, _second = linked(label)
        if first.Length():
            tool.SetGeomTolerance(first, at)
        for datum in _datums_of(label):
            tool.SetDatumToGeomTol(datums[_entry(datum)], at)


def _tool(doc: Any) -> Any:
    """A document's GD&T tool (``XCAFDoc_DimTolTool``), or None where it has none."""
    from OCP.XCAFDoc import XCAFDoc_DimTolTool

    label = doc.Main().FindChild(DIMTOL_TAG, False)
    if label.IsNull() or not label.IsAttribute(XCAFDoc_DimTolTool.GetID_s()):
        return None
    return XCAFDoc_DimTolTool.Set_s(label)


def _notes_tool(doc: Any) -> Any:
    """A document's notes tool (``XCAFDoc_NotesTool``), or None where it has none."""
    from OCP.XCAFDoc import XCAFDoc_NotesTool

    label = doc.Main().FindChild(NOTES_TAG, False)
    if label.IsNull() or not label.IsAttribute(XCAFDoc_NotesTool.GetID_s()):
        return None
    return XCAFDoc_NotesTool.Set_s(label)


def _labels(tool: Any, kind: str) -> list[Any]:
    """The GD&T tool's labels of ``kind`` (``datum``, ``dimension``, ``geometric_tolerance``) that hold
    their object, in the tool's order; none where the document has no GD&T tool (``tool`` None)."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_GeomTolerance

    if tool is None:
        return []
    listed, attribute = {"datum": (tool.GetDatumLabels, XCAFDoc_Datum),
                         "dimension": (tool.GetDimensionLabels, XCAFDoc_Dimension),
                         "geometric_tolerance": (tool.GetGeomToleranceLabels, XCAFDoc_GeomTolerance)}[kind]
    sequence = Sequence_TDF_Label()
    listed(sequence)
    return [sequence.Value(at) for at in range(1, sequence.Length() + 1)
            if sequence.Value(at).IsAttribute(attribute.GetID_s())]


def _linked(tool: Any, label: Any) -> tuple[Any, Any]:
    """The shape labels a GD&T label is linked to: its first and its second (a dimension's ``to``)."""
    from OCP.collections import Sequence_TDF_Label

    first, second = Sequence_TDF_Label(), Sequence_TDF_Label()
    tool.GetRefShapeLabel_s(label, first, second)
    return first, second


def _datums_of(label: Any) -> list[Any]:
    """The datum labels a geometric tolerance's frame names."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_DimTolTool

    named = Sequence_TDF_Label()
    XCAFDoc_DimTolTool.GetDatumWithObjectOfTolerLabels_s(label, named)
    return [named.Value(at) for at in range(1, named.Length() + 1)]


def _element(label: Any, by_entry: dict[str, Any], maps: dict[tuple[int, str], Any]) -> tuple[int, str, int] | None:
    """The element a ref label is -- its prototype's index, its kind (``face``, ``edge``, ``vertex``)
    and its ordinal there -- or None where it is no element of a prototype (``by_entry``: the
    document's prototypes by their labels' entries; ``maps``: each prototype's elements, made once)."""
    from OCP.TopAbs import TopAbs_EDGE, TopAbs_FACE, TopAbs_VERTEX
    from OCP.XCAFDoc import XCAFDoc_ShapeTool

    from cadgen.engine.document import _entry

    shape = XCAFDoc_ShapeTool.GetShape_s(label)
    kinds = {TopAbs_FACE: "face", TopAbs_EDGE: "edge", TopAbs_VERTEX: "vertex"}
    kind = None if shape.IsNull() else kinds.get(shape.ShapeType())
    owner = label.Father()
    prototype = by_entry.get(_entry(owner))
    if kind is None or prototype is None:
        return None
    if (prototype.index, kind) not in maps:
        maps[(prototype.index, kind)] = _map(XCAFDoc_ShapeTool.GetShape_s(owner), kind)
    ordinal = maps[(prototype.index, kind)].FindIndex(shape)
    return (prototype.index, kind, ordinal) if ordinal else None


# --- read back ---------------------------------------------------------------------------------

# Why a ref of a document another system wrote resolves to nothing.
_NOT_LINKED = "the file links it to no face, edge or point of a part"


def records_of_document(doc: Any, prototypes: list[Any], root: str) -> list[dict[str, Any]]:
    """A document's annotations as records (``entries``' input): every GD&T object its tool holds,
    datums, dimensions and geometric tolerances in the tool's order, then the notes the code made
    in the notes tool's (a note another system wrote is not read), each resolved as the document
    is now. One the code made (its cadgen attribute) is resolved as its build resolved it
    (``_resolved``, against its part's faces and their names): its status is derived, never read.
    One another system wrote is resolved by the elements the file links it to, and what this module
    does not hold whole is ``unsupported``, with why (``_beyond_*``). ``prototypes`` are the document's
    (``document.Prototype``: each its label's entry and shape), ``root`` the name of its root."""
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_DimensionType_Location_LinearDistance,
                                        XCAFDimTolObjects_DimensionType_Size_Diameter,
                                        XCAFDimTolObjects_GeomToleranceTypeValue_Diameter,
                                        XCAFDimTolObjects_GeomToleranceTypeValue_None)
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_Datum, XCAFDoc_Dimension, XCAFDoc_GeomTolerance, XCAFDoc_NoteComment

    from cadgen.engine.document import _entry

    dimensions = {XCAFDimTolObjects_DimensionType_Size_Diameter: "diameter",
                  XCAFDimTolObjects_DimensionType_Location_LinearDistance: "distance"}
    characteristics = {xcaf: name for name, xcaf in _xcaf_characteristics().items()}
    tool, notes_tool = _tool(doc), _notes_tool(doc)
    if tool is None and notes_tool is None:
        return []
    by_entry = {prototype.entry: prototype for prototype in prototypes}
    maps: dict[tuple[int, str], Any] = {}
    records: list[dict[str, Any]] = []

    def add(label: Any, kind: str, values: dict[str, Any], beyond: list[str], xcaf_type: str | None,
            given: Any) -> None:
        """The record of a GD&T label holding ``given``, an XCAF object of ``kind``."""
        held = _held_extra(label)
        first, second = ([_element(sequence.Value(at), by_entry, maps) for at in range(1, sequence.Length() + 1)]
                         for sequence in _linked(tool, label))
        if kind == "dimension" and second:
            targets = [("from", hit) for hit in first] + [("to", hit) for hit in second]
        else:
            targets = [("feature", hit) for hit in first]
        found = {"values": values, "targets": targets, "extra": held, "entry": _entry(label),
                 "presentation": _presentation_of(given)}
        if held is not None:
            found.update(kind=held["kind"], xcaf_type=None, reason=None, part=_part_of(label, by_entry))
            records.append(found)
            return
        # Linked to an edge or a point: no annotation on faces, kept and listed, never drawn.
        beyond = beyond + [f"linked to {'an edge' if element == 'edge' else 'a point'}"
                           for element in sorted({hit[1] for _role, hit in targets if hit is not None} - {"face"})]
        refs = [{"role": role, "written": None, "status": "missing" if hit is None else "ok",
                 "ordinal": None if hit is None else hit[2], "candidates": [],
                 "problem": _NOT_LINKED if hit is None else None} for role, hit in targets]
        status = _worst(ref["status"] for ref in refs) if refs else "missing"
        parts = {hit[0] for _role, hit in targets if hit is not None}
        found.update(kind="unsupported" if beyond else kind, xcaf_type=xcaf_type if beyond else None,
                     reason="; ".join(beyond) or None, part=min(parts) if parts else None, status=status,
                     problem=None if status == "ok" else _NOT_LINKED, refs=refs)
        records.append(found)

    modified: set[str] = set()  # the datums a tolerance cannot be read with: modified, or targets
    # Each datum once, by its letter and the shapes it is linked to: OCCT's STEP reader gives each
    # frame that names a datum a label of its own, so a STEP's datum A named by three frames is three
    # labels, where the file holds one DATUM.
    datums: set[tuple[str, tuple[str, ...]]] = set()
    for label in _labels(tool, "datum"):
        found = XCAFDoc_Datum.Set_s(label).GetObject()
        beyond = _beyond_datum(found)
        if beyond:
            modified.add(_entry(label))
        first, _second = _linked(tool, label)
        datum = (_name_of(found), tuple(_entry(first.Value(at)) for at in range(1, first.Length() + 1)))
        if datum in datums:
            continue
        datums.add(datum)
        add(label, "datum", {"letter": _name_of(found)}, beyond, "XCAFDimTolObjects_DatumObject", found)
    for label in _labels(tool, "dimension"):
        found = XCAFDoc_Dimension.Set_s(label).GetObject()
        kind = dimensions.get(found.GetType())
        tolerance = None
        if found.IsDimWithPlusMinusTolerance():
            tolerance = {"type": "plus_minus", "upper": _as_held(found.GetUpperTolValue()),
                         "lower": _as_held(-found.GetLowerTolValue())}
        elif found.IsDimWithRange():
            tolerance = {"type": "limits", "lower": _as_held(found.GetLowerBound()),
                         "upper": _as_held(found.GetUpperBound())}
        notes = [(found.GetDescriptionName(at).ToCString(), found.GetDescription(at).ToCString())
                 for at in range(found.NbDescriptions())] if found.HasDescriptions() else []
        # A file's limits come with no nominal: XCAF's value is then their midpoint, no fact of the
        # file (one the code made is measured, below).
        nominal = None if found.IsDimWithRange() else _as_held(found.GetValue())
        values = {"type": kind, "basic": THEORETICAL in notes, "nominal": nominal, "tolerance": tolerance}
        if notes:
            values["notes"] = [list(note) for note in notes]
        add(label, "dimension", values, _beyond_dimension(found, kind, notes), found.GetType().name, found)
    for label in _labels(tool, "geometric_tolerance"):
        found = XCAFDoc_GeomTolerance.Set_s(label).GetObject()
        datums = _datums_of(label)
        letters = sorted((datum.GetPosition(), _name_of(datum))
                         for datum in (XCAFDoc_Datum.Set_s(named).GetObject() for named in datums))
        value_type = found.GetTypeOfValue()
        if value_type == XCAFDimTolObjects_GeomToleranceTypeValue_Diameter:
            zone = "diameter"
        elif value_type == XCAFDimTolObjects_GeomToleranceTypeValue_None:
            zone = None
        else:
            zone = "other"
        characteristic = characteristics.get(found.GetType())
        values = {"characteristic": characteristic, "value": _as_held(found.GetValue()), "unit": UNIT, "zone": zone,
                  "modifier": None, "datums": [letter for _place, letter in letters], "general": False}
        beyond = _beyond_tolerance(found, characteristic, zone)
        if any(_entry(named) in modified for named in datums):
            beyond.append("a datum it names has modifiers or is a datum target")
        add(label, "geometric_tolerance", values, beyond, found.GetType().name, found)
    labels = Sequence_TDF_Label()
    if notes_tool is not None:
        notes_tool.GetNotes(labels)
    for label in (labels.Value(at) for at in range(1, labels.Length() + 1)):
        held = _held_extra(label)
        if held is None or held.get("kind") != "note" or not label.IsAttribute(XCAFDoc_NoteComment.GetID_s()):
            continue
        # Its text is XCAF's comment; its faces are resolved with its part's annotations, below.
        text = XCAFDoc_NoteComment.Get_s(label).Comment().ToExtString()
        records.append({"kind": "note", "values": {"text": text, "annotations": list(held["annotations"]),
                                                   "general_tolerance": held.get("general_tolerance")},
                        "targets": [], "extra": held, "entry": _entry(label), "xcaf_type": NOTE_TYPE,
                        "reason": None, "part": _part_of(label, by_entry)})
    # The code's annotations resolved as their build resolved them, each part's together (its general
    # profile covers what the others leave): the same faces again, from the document alone.
    of_part: dict[int, list[dict[str, Any]]] = {}
    for record in records:
        if record["extra"] is not None:
            if record["extra"].get("general"):
                record["values"]["general"] = True  # the cadgen attribute's: XCAF has no place for it
            of_part.setdefault(record["part"], []).append(record)
    for index, held in of_part.items():
        prototype = prototypes[index]
        names = [prototype.face_names.get(at) for at in range(1, _faces(prototype.shape).Extent() + 1)]
        specs = [{"kind": record["extra"]["kind"], "refs": record["extra"]["refs"],
                  **(record["extra"].get("unlinked") or {record["extra"]["kind"]: record["values"]})} for record in held]
        for record, resolved in zip(held, _resolved_part(specs, prototype.shape, names, {prototype.name, root})):
            record.update(status=resolved.status, problem=resolved.problem, refs=_refs(resolved))
            if record["kind"] == "note":
                # A note's faces as resolved now (XCAF's links to them are for another reader, ``_note``).
                record["targets"] = ([(ref.role, (index, "face", ref.ordinal)) for ref in resolved.refs]
                                     if _on_faces(resolved) else [])
            if (record["values"].get("tolerance") or {}).get("type") == "limits":
                record["values"]["nominal"] = _as_held(resolved.nominal or 0.0)  # measured, as its build did
    return records


def _words(name: str) -> str:
    """An XCAF enumerator's name as words: ``..._Location_LinearDistance`` is ``location linear distance``."""
    tail = name.split("_", 2)[-1]
    return re.sub(r"(?<=[a-z])(?=[A-Z])", " ", tail).replace("_", " ").lower()


def _beyond_datum(found: Any) -> list[str]:
    """What a datum of a file says that this module does not hold: modifiers, or a datum target."""
    from OCP.XCAFDimTolObjects import XCAFDimTolObjects_DatumModifWithValue_None

    beyond = []
    # The binding hands back a modifier-with-value's value alone (its kind is an out-parameter it
    # cannot fill): a value says one is set.
    if found.GetModifiers().Length() or found.GetModifierWithValue(XCAFDimTolObjects_DatumModifWithValue_None)[0]:
        beyond.append("it has modifiers")
    if found.IsDatumTarget():
        beyond.append("it is a datum target")
    return beyond


def _beyond_dimension(found: Any, kind: str | None, notes: list[tuple[str, str]]) -> list[str]:
    """What a dimension of a file says that this module does not hold: another type, a fit, a
    qualifier, modifiers, a note other than a basic one's, a basic dimension other than a distance;
    and limits beside any of them or on a basic dimension (limits are held alone). XCAF holds limits
    or deviations, never both."""
    beyond = []
    if kind is None:
        beyond.append(f"a {_words(found.GetType().name)} dimension is not one this holds")
    if found.IsDimWithClassOfTolerance():
        beyond.append("it has a class of tolerance (a fit)")
    if found.HasQualifier():
        beyond.append(f"it has a qualifier ({_words(found.GetQualifier().name)})")
    if found.GetModifiers().Length():
        beyond.append("it has modifiers")
    other = [list(note) for note in notes if note != THEORETICAL]
    if other:
        beyond.append(f"it has notes {other}")
    if THEORETICAL in notes and kind not in (None, "distance"):
        beyond.append(f"a basic {kind} is not one this holds")
    if found.IsDimWithRange() and (beyond or THEORETICAL in notes):
        beyond.append("it has limits (a range), held only on a dimension that says nothing more")
    return beyond


def _beyond_tolerance(found: Any, characteristic: str | None, zone: str | None) -> list[str]:
    """What a geometric tolerance of a file says that this module does not hold: another
    characteristic, modifiers, a material requirement, a zone modifier, a maximum value, a zone
    other than a width's or a diameter's, a diameter's on a surface profile."""
    from OCP.XCAFDimTolObjects import (XCAFDimTolObjects_GeomToleranceMatReqModif_None,
                                        XCAFDimTolObjects_GeomToleranceZoneModif_None)

    beyond = []
    if characteristic is None:
        beyond.append(f"{_words(found.GetType().name)} is not a characteristic this holds")
    if found.GetModifiers().Length():
        beyond.append("it has modifiers")
    if found.GetMaterialRequirementModifier() != XCAFDimTolObjects_GeomToleranceMatReqModif_None:
        beyond.append(f"it has a material requirement ({_words(found.GetMaterialRequirementModifier().name)})")
    if found.GetZoneModifier() != XCAFDimTolObjects_GeomToleranceZoneModif_None:
        beyond.append(f"it has a {_words(found.GetZoneModifier().name)} zone")
    if found.GetMaxValueModifier() > 0:
        beyond.append("it has a maximum value")
    if zone == "other":
        beyond.append(f"its zone is {_words(found.GetTypeOfValue().name)}")
    if zone == "diameter" and characteristic == "surface_profile":
        beyond.append("a surface profile with a diametral zone is not one this holds")
    return beyond


def _refs(item: Resolved) -> list[dict[str, Any]]:
    """An annotation's refs as a record holds them (``records_of_document``, ``records_of_tree``)."""
    return [{"role": ref.role, "written": ref.written, "status": ref.status, "ordinal": ref.ordinal,
             "candidates": list(ref.candidates), "problem": ref.problem} for ref in item.refs]


def _name_of(datum: Any) -> str:
    """A datum object's letter; the empty string for none (a null handle reads as None)."""
    name = datum.GetName()
    return name.ToCString() if name is not None else ""


def records_of_tree(tree: Any, index_of: dict[int, int]) -> list[dict[str, Any]]:
    """A built tree's annotations as the records ``records_of_document`` reads back from its
    document: the same order (each part's datums, then the rest, its notes last), the same values,
    as XCAF holds them (``_as_held``), the same refs resolved."""
    records = []
    for part, items in resolve(tree):
        index = index_of[id(part)]
        ordered = _datums_first(items)
        by_kind: dict[str, list] = {"datum": [], "dimension": [], "geometric_tolerance": [], "note": []}
        for item in ordered:
            spec = item.spec
            linked = _on_faces(item)
            targets = [(ref.role, (index, "face", ref.ordinal)) for ref in item.refs] if linked else []
            if spec["kind"] == "datum":
                values = {"letter": spec["datum"]["letter"]}
            elif spec["kind"] == "dimension":
                tolerance = spec["dimension"]["tolerance"] if item.nominal is not None else None
                values = {"type": spec["dimension"]["type"], "basic": bool(spec["dimension"].get("basic")),
                          "nominal": _as_held(item.nominal or 0.0),
                          "tolerance": None if tolerance is None else
                          {key: given if key == "type" else _as_held(given) for key, given in tolerance.items()}}
            elif spec["kind"] == "note":
                values = {"text": spec["note"]["text"], "annotations": list(spec["note"]["annotations"]),
                          "general_tolerance": spec["note"]["general_tolerance"]}
            else:
                given = spec["geometric_tolerance"]
                values = {"characteristic": given["characteristic"], "value": _as_held(given["value"]), "unit": UNIT,
                          "zone": given["zone"], "modifier": None, "datums": list(given["datums"]) if linked else [],
                          "general": given["general"]}
            by_kind[spec["kind"]].append({
                "kind": spec["kind"], "values": values, "xcaf_type": NOTE_TYPE if spec["kind"] == "note" else None,
                "reason": None, "part": index,
                "targets": targets, "extra": json.loads(_text(_extra(item))), "entry": None, "status": item.status,
                "problem": item.problem, "refs": _refs(item)})
        records.extend(by_kind["datum"] + by_kind["dimension"] + by_kind["geometric_tolerance"] + by_kind["note"])
    # The document's GD&T tool lists datums, then dimensions, then tolerances, of every part; its
    # notes tool the notes after them.
    return sorted(records, key=lambda record: _KINDS.index(record["kind"]))


# The kinds of the code's records, in the order its document lists them.
_KINDS = ("datum", "dimension", "geometric_tolerance", "note")


def views_of_tree(tree: Any, index_of: dict[int, int]) -> list[dict[str, Any]]:
    """A built tree's views as ``views_of_document`` reads them back from its document, by part, in
    the code's order."""
    found = [_view_entry(index_of[id(part)], json.loads(_text(_view_extra(given))))
             for part, held in tree.pmi or () for given in _views(held)]
    return sorted(found, key=lambda given: given["part"])


def views_of_document(doc: Any, prototypes: list[Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi_views``: each view the code gave a part of a document (``view``), served
    from its cadgen attribute (the XCAF view beside it is for another reader), by part, in the code's
    order: its ``part`` (a prototype index), ``name``, ``label``, ``camera`` (``_camera_of``),
    ``section`` (``{axis, at, invert}``, the Clip's, or None), ``shows`` (ids, or None for every
    annotation and note) and ``place`` (each placed id's ``{anchor, offset}``), in the part's frame.
    A view another system wrote (no cadgen attribute) is not read; none where there are none."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.XCAFDoc import XCAFDoc_ViewTool

    label = doc.Main().FindChild(VIEWS_TAG, False)
    if label.IsNull() or not label.IsAttribute(XCAFDoc_ViewTool.GetID_s()):
        return []
    by_entry = {prototype.entry: prototype for prototype in prototypes}
    labels = Sequence_TDF_Label()
    XCAFDoc_ViewTool.Set_s(label).GetViewLabels(labels)
    found = []
    for at in range(1, labels.Length() + 1):
        held = _held_extra(labels.Value(at))
        part = _part_of(labels.Value(at), by_entry)
        if held is not None and held.get("kind") == "view" and part is not None:
            found.append(_view_entry(part, held))
    return sorted(found, key=lambda given: given["part"])


def _view_entry(part: int, held: dict[str, Any]) -> dict[str, Any]:
    """A ``pmi_views`` entry of part ``part`` from the view's cadgen attribute (``_view_extra``)."""
    return {"part": part, "name": held["name"], "label": held["label"], "camera": _camera_of(held["camera"]),
            "section": held["section"], "shows": held["shows"], "place": held["place"]}


def _held_extra(label: Any) -> dict[str, Any] | None:
    """The cadgen attribute a label holds (``EXTRA_GUID``), or None where it holds none of ``SCHEMA``."""
    from OCP.Standard import Standard_GUID
    from OCP.TDataStd import TDataStd_AsciiString

    guid, found = Standard_GUID(EXTRA_GUID), TDataStd_AsciiString()
    if label.IsAttribute(guid) and label.FindAttribute(guid, found):
        held = json.loads(found.Get().ToCString())
        return held if held.get("schema") == SCHEMA else None
    return None


def _part_of(label: Any, by_entry: dict[str, Any]) -> int | None:
    """The prototype index of what the code gave a part: its label's ``TDF_Reference``'s."""
    from OCP.TDF import TDF_Reference

    from cadgen.engine.document import _entry

    found = TDF_Reference()
    if not label.FindAttribute(TDF_Reference.GetID_s(), found):
        return None
    prototype = by_entry.get(_entry(found.Get()))
    return None if prototype is None else prototype.index


def _as_held(value: float) -> float:
    """A real as XCAF holds and reads it back: a double, its zero unsigned (a deviation of 0 is
    held as the magnitude -0)."""
    return float(value) + 0.0


def entries(records: list[dict[str, Any]], structure: dict[str, Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi``: one JSON-plain entry per record -- ``id``, ``kind`` (``dimension``,
    ``datum``, ``geometric_tolerance``, ``note``, ``unsupported``), ``label``, ``status``,
    ``problem``, ``part`` (a prototype index), ``refs`` (each ``role``, ``ref`` --
    canonical as ``refs`` spells it for this document --, ``written``, ``status``, ``candidates``,
    ``problem``), ``presentation``, ``xcaf_type``, an unsupported one's ``reason``, and the kind's
    own block of values. A note's (``note``) is its ``number`` (its part's general profile Note 1
    where it has one, then each note in the code's order), ``text``, ``general`` (it names no face
    and no annotation) and the ``annotations`` it names, as written."""
    canonical = _canonical(structure)
    found = []
    counters: dict[str, int] = {}
    # Each part's notes are numbered after its general profile, Note 1 where it has one.
    numbers = {record["part"]: 1 for record in records if (record["extra"] or {}).get("general")}
    for record in records:
        extra, kind = record["extra"], record["kind"]
        targets = list(record["targets"])
        refs = []
        for at, ref in enumerate(record["refs"]):
            hit = targets[at][1] if at < len(targets) else None
            refs.append({"role": ref["role"], "written": ref["written"], "status": ref["status"],
                         "ref": canonical(*hit) if hit is not None else ref["written"],
                         "candidates": [canonical(record["part"], "face", ordinal)
                                        for ordinal in ref["candidates"]] or None,
                         "problem": ref["problem"]})
        if extra is not None:
            ident, label, presentation = extra["id"], extra["label"], extra["presentation"]
            unlinked = extra.get("unlinked")
        else:
            counters[kind] = counters.get(kind, 0) + 1
            ident = (record["values"].get("letter") or kind) if kind == "datum" else f"{kind}-{counters[kind]}"
            label, presentation, unlinked = None, record.get("presentation"), None
        entry = {"id": ident, "kind": kind, "label": label, "status": record["status"], "problem": record["problem"],
                 "part": record["part"], "refs": refs,
                 "presentation": presentation, "xcaf_type": record["xcaf_type"]}
        values = record["values"]
        if kind == "datum":
            entry["datum"] = {"letter": values["letter"]}
        elif kind == "dimension":
            if unlinked is not None:
                entry["dimension"] = {"type": unlinked["dimension"]["type"],
                                      "basic": bool(unlinked["dimension"].get("basic")), "nominal": None,
                                      "tolerance": unlinked["dimension"]["tolerance"]}
            else:
                # Measured from the geometry where the code made it; as the file says, where another
                # system did, and none where the file states limits alone.
                entry["dimension"] = {"type": values["type"], "basic": bool(values.get("basic")),
                                      "nominal": None if values["nominal"] is None else
                                      {"value": values["nominal"], "unit": UNIT,
                                       "source": "geometry" if extra is not None else "file"},
                                      "tolerance": values["tolerance"]}
        elif kind == "geometric_tolerance":
            entry["geometric_tolerance"] = dict(unlinked["geometric_tolerance"] if unlinked is not None else values)
        elif kind == "note":
            numbers[record["part"]] = numbers.get(record["part"], 0) + 1
            entry["note"] = {"number": numbers[record["part"]], "text": values["text"],
                             "general": not extra["refs"] and not values["annotations"],
                             "annotations": list(values["annotations"]),
                             "general_tolerance": values.get("general_tolerance")}
        else:
            entry["reason"] = record["reason"]
            entry["values"] = values
        found.append(entry)
    return found


def _canonical(structure: dict[str, Any]) -> Callable[[int, str, int], str]:
    """How ``structure`` spells an element of a prototype -- by its index, the element's kind and
    its ordinal -- canonically, as ``refs`` spells it for that document: under the prototype's first
    placement, by its name where it has one."""
    from cadgen.engine import refs as grammar

    root = grammar.structure_tree(structure)
    first_node: dict[int, Any] = {}
    for node in root.parts():
        first_node.setdefault(node.payload["prototype"], node)
    one_part = len(root.parts()) == 1
    prototypes = structure["prototypes"]
    named = {"face": "faceNames", "edge": "edgeNames", "vertex": "vertexNames"}

    def canonical(index: int, kind: str, ordinal: int) -> str:
        name = (prototypes[index].get(named[kind]) or {}).get(str(ordinal))
        node = first_node.get(index)
        if node is None:
            return name or f"{kind} {ordinal}"
        return grammar._element_ref(root, node, kind, ordinal, name, one_part)

    return canonical


def coverage_of(structure: dict[str, Any], shapes: Mapping[int, Any]) -> list[dict[str, Any]]:
    """The structure's ``pmi_coverage``: ``coverage`` of each part its ``pmi`` has an entry on, and
    what its requirements leave unsaid (``suggestions``), as ``{"part", "uncovered", "conflicts",
    "suggestions"}``, by part (a prototype index), its faces every face of its shape (``shapes``, by
    prototype index) as the structure spells them, each measured (``_measured``). A part with no
    entry says nothing. Derived where the structure is served, the build's report read from the same."""
    entries = structure.get("pmi") or []
    canonical = _canonical(structure)
    prototypes = structure.get("prototypes") or []
    found = []
    for index in sorted({entry["part"] for entry in entries if entry["part"] is not None}):
        faces = _faces(shapes[index])
        measured = [{"ref": canonical(index, "face", at), **_measured(faces.FindKey(at))}
                    for at in range(1, faces.Extent() + 1)]
        mine = [entry for entry in entries if entry["part"] == index]
        material = index < len(prototypes) and prototypes[index].get("material") is not None
        found.append({"part": index, **coverage(mine, [face["ref"] for face in measured]),
                      "suggestions": suggestions(mine, measured, material=material)})
    return found


def _measured(face: Any) -> dict[str, Any]:
    """What ``suggestions`` reads of a face: its surface's kind (``_surface``) and area, and a
    cylinder's diameter and whether it bounds a hole (its material outside it: the face's outward
    normal toward its axis)."""
    from OCP.BRepGProp import BRepGProp, BRepGProp_Face
    from OCP.GProp import GProp_GProps
    from OCP.gp import gp_Pnt, gp_Vec
    from OCP.TopoDS import TopoDS

    kind, values = _surface(face)
    props = GProp_GProps()
    BRepGProp.SurfaceProperties_s(face, props)
    found = {"surface": kind, "area": props.Mass()}
    if kind == "cylinder":
        side = BRepGProp_Face(TopoDS.Face(face))
        low_u, high_u, low_v, high_v = side.Bounds()
        point, normal = gp_Pnt(), gp_Vec()
        side.Normal((low_u + high_u) / 2, (low_v + high_v) / 2, point, normal)
        axis = _axis(face)
        along = gp_Vec(*axis["direction"])
        out = gp_Vec(gp_Pnt(*axis["point"]), point)
        out.Subtract(along.Multiplied(out.Dot(along)))
        found.update(diameter=_as_held(round(2 * values["radius"], 6)), hole=normal.Dot(out) < 0)
    return found


def read(source: Any) -> list[dict[str, Any]]:
    """The annotations a document holds (``entries``): an ``.xbf`` or a ``.step`` by its path,
    read as the viewer reads it (``document.Loaded``)."""
    from pathlib import Path

    from cadgen.engine import document

    return list(document.Loaded(Path(source)).structure().get("pmi") or [])


# --- exports -----------------------------------------------------------------------------------


def step_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The entries of a document's PMI (``entries``) a STEP carries: every one but its notes, which
    are the xbf's alone (OCCT's STEP writer writes no notes), but a general tolerance
    (``general_tolerance``), which the engine writes itself (``export.step``)."""
    return [entry for entry in entries if entry.get("kind") != "note" or _stated(entry)]


def _stated(entry: dict[str, Any]) -> str | None:
    """The general tolerance an entry states (``general_tolerance``), or None."""
    return (entry.get("note") or {}).get("general_tolerance") if entry.get("kind") == "note" else None


def general_tolerances(doc: Any) -> list[tuple[str, str]]:
    """Each general tolerance a document holds (``general_tolerance``), as its STEP writes it: its
    part's name (the ``PRODUCT`` the writer makes of the part's shape label) and the standard."""
    from OCP.collections import Sequence_TDF_Label
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Reference

    tool = _notes_tool(doc)
    if tool is None:
        return []
    labels, found = Sequence_TDF_Label(), []
    tool.GetNotes(labels)
    for label in (labels.Value(at) for at in range(1, labels.Length() + 1)):
        held = _held_extra(label) or {}
        reference = TDF_Reference()
        if held.get("general_tolerance") and label.FindAttribute(TDF_Reference.GetID_s(), reference):
            name = TDataStd_Name()
            if reference.Get().FindAttribute(TDataStd_Name.GetID_s(), name):
                found.append((name.Get().ToExtString(), held["general_tolerance"]))
    return found


def dropped(view: Any, kind: str) -> list[tuple[dict[str, Any], str]]:
    """Each annotation of a document that a ``kind`` file written from ``view`` does not carry whole,
    and why: an xbf of a document this engine wrote held without its XCAF document is a document
    made again from the view (``tree.tree_of``), which carries no PMI (one held with it is its own
    bytes, ``tree.write_xbf``, which carry it all); and a STEP drops one linked to no geometry, as an
    xbf of a STEP (which copies its GD&T as read, ``copy``) keeps one the file links to no element of
    a part linked to nothing. A STEP carries no note, whole or not, and is never refused for one
    (``step_entries``). A mesh carries no B-rep, so no PMI."""
    entries = view.source.structure.get("pmi") or []
    if kind == "step":
        entries = step_entries(entries)
    if kind not in ("step", "xbf") or not entries:
        return []
    if kind == "xbf" and not view.source.foreign:
        if view.source.xcaf is not None:
            return []
        return [(entry, "an xbf written from it is a document made again, which carries no PMI") for entry in entries]
    return [(entry, f"{entry['status']}: {entry['problem']}") for entry in entries if entry["status"] != "ok"]


def refuse_dropped(view: Any, kind: str) -> None:
    """A ``kind`` file of ``view`` that would not carry whole an annotation the code made
    (``dropped``), refused by name: it would be no translation of the model's document; so is an
    xbf made again of one holding the code's views (``pmi_views``), which it would lose as it would
    annotations, named. One of a document another
    system wrote is written: ``export.translate`` says what it leaves out."""
    from cadgen.engine.export import ExportRefused

    lost = [(entry, why) for entry, why in dropped(view, kind) if _from_code(entry)]
    structure = view.source.structure
    if kind == "xbf":
        again = not view.source.foreign and view.source.xcaf is None
        views = [given["name"] for given in structure.get("pmi_views") or []] if again else []
        held = [f"{len(structure['pmi'])} PMI annotation(s)"] if lost else []
        if views:
            held.append(f"{len(views)} named view(s) ({', '.join(views)})")
        if held:
            said = held[0] if len(held) == 1 else f"{', '.join(held[:-1])} and {held[-1]}"
            raise ExportRefused(f"{view.source.name} holds {said}, and an xbf written from it is a document made "
                                "again, which carries none yet: declare the model's xbf (@xbf), its own document")
        return
    if not lost:
        return

    def named(entry: dict[str, Any], why: str) -> str:
        broken = [repr(ref.get("written") or ref.get("ref")) for ref in entry.get("refs") or ()
                  if ref.get("status", "ok") != "ok"]
        return f"{entry['id']} ({'ref ' + ', '.join(broken) + ': ' if broken else ''}{why})"

    raise ExportRefused("a STEP would drop PMI linked to no geometry: "
                        + "; ".join(named(entry, why) for entry, why in lost)
                        + ". Fix the refs in the model, or remove the annotations")


def checked(source: Any, entries: list[dict[str, Any]], target: Any,
            log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """The check of a STEP written of ``source`` (``ap242.check``) of the PMI it carries
    (``entries``: ``step_entries``), against the source's faces (``step_surfaces``), each part held
    to its own product (by its name): what every STEP write of a document with PMI answers with, a
    build's declared one, an export's and the viewer's alike, ``target`` the file staged before it
    lands (``export.translate``'s ``check``). For a document the code made, a check that found any
    problem -- a record that does not match, or one it could not be made of (a file the reader
    cannot read, a name it cannot tell apart) -- refuses the file, so none is written and an
    earlier one keeps its bytes (law 17). So does one of a document another system wrote, of what
    its STEP carries (each annotation ``ok``: ``dropped`` says the rest), where every face those are
    on carries a name the file is held to (a STEP this engine wrote, read back). One whose faces
    carry no names (``face 7``) verifies nothing: what the check found is said to ``log``, the file
    written."""
    from pathlib import Path

    from cadgen.engine import refs as grammar
    from cadgen.engine.export import ExportRefused
    from cadgen.engine.export.ap242 import check

    target = Path(target)
    binding = not source.foreign
    if source.foreign:
        entries = [entry for entry in entries if entry["status"] == "ok"]
        binding = all(isinstance(ref.get("ref"), str) and isinstance(grammar.parse(ref["ref"])[1][-1].element, str)
                      for entry in entries for ref in entry.get("refs") or ())
    parts = {prototype["index"]: prototype["name"] for prototype in source.structure.get("prototypes") or []
             if "index" in prototype and "name" in prototype}
    found = check(entries, target, step_surfaces(source, entries), parts)
    if not found.get("problems"):
        return found
    said = f"({found['matched']} of {found['total']} matched): {' '.join(found['problems'])}"
    if binding:
        raise ExportRefused(f"{target.name} not written: the PMI in the STEP written does not match the model's "
                            f"document, or could not be checked against it {said}")
    if log is not None:
        log(f"warning: pmi: {target.name}: the PMI in the written file is not verified {said}")
    return found


def step_surfaces(source: Any, entries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """The surface of each face the entries' refs name, by canonical ref, as ``source``'s shapes
    hold it in its part's own frame (where a STEP writes it): a ``plane`` (origin, unit normal), a
    ``cylinder`` (radius, a point on its axis and its direction), another kind by name. What the
    check of a written STEP holds each face it reads against (``ap242.compare``); a ref it cannot
    find on the shape is left out, so its face matches nothing."""
    from cadgen.engine import refs as grammar

    prototypes = source.structure.get("prototypes") or []
    maps: dict[int, Any] = {}
    found: dict[str, dict[str, Any]] = {}
    for entry in entries:
        index = entry.get("part")
        if index is None or not 0 <= index < len(prototypes) or prototypes[index].get("key") not in source.shapes:
            continue
        shape = source.shapes[prototypes[index]["key"]]
        if isinstance(shape, (bytes, bytearray)):
            continue
        faces = maps.get(index)
        if faces is None:
            faces = maps[index] = _faces(shape)
        names = prototypes[index].get("faceNames") or {}
        for ref in entry.get("refs") or ():
            text = ref.get("ref")
            if not isinstance(text, str) or text in found:
                continue
            element = grammar.parse(text)[1][-1].element
            if isinstance(element, tuple):
                ordinals = [element[1]] if element[0] == "face" else []
            else:
                ordinals = [int(at) for at, name in names.items() if name == element]
            if len(ordinals) != 1 or not 1 <= ordinals[0] <= faces.Extent():
                continue
            face = faces.FindKey(ordinals[0])
            kind, held = _surface(face)
            if kind == "cylinder":
                axis = _axis(face)
                held = {**held, "origin": list(axis["point"]), "axis": list(axis["direction"])}
            found[text] = {"type": kind, **{key: list(value) if isinstance(value, tuple) else value
                                            for key, value in held.items()}}
    return found


def _from_code(entry: dict[str, Any]) -> bool:
    """Whether an entry is an annotation a model's code made (its refs as the code wrote them, a
    general profile, whose faces none writes, or a note, which only the code's are read as), not one
    read from a file another system wrote."""
    return (any(ref.get("written") is not None for ref in entry.get("refs") or ())
            or bool((entry.get("geometric_tolerance") or {}).get("general")) or entry.get("kind") == "note")
