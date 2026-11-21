"""``cad.quiddity``: the quiddity integration -- our code that asks quiddity, Paul Fremantle's feature recogniser, about
one part of a document (its extra, ``cad[quiddity]``: the ``quiddity`` wheel, a Rust library with no dependency
of its own, Apache-2.0).

quiddity reads a STEP and says the features it finds -- holes, pockets, slots, fillets and the rest -- each with
the faces it is made of, and where every face went: into a feature, into the body's own stock, into a refusal,
or unexplained. That is quiddity's, and stays quiddity's: a script that wants it imports ``quiddity`` and reads
its documentation. What is missing without us is the tie to a document, and four things come of it. Nothing
here is a person's to call (``__all__`` is empty): it backs the CNC check's holes
(``cad.build123d._dfm_cnc_recognised``), as the coacd integration backs ``cad.mujoco.decompose``. And it runs in
two places: ``features`` in the process that holds the part, whose environment holds the kernel's integration
(it reads the part through ``cad.build123d._dfm_brep`` and writes its STEP with the engine's writer, the
kernel's), and the recogniser in quiddity's own environment, which holds quiddity and no kernel.

- **A part, not a file.** ``features(part)`` takes one part as the library holds it (a build123d shape), writes
  its STEP in memory and hands quiddity that part alone: quiddity reads every face of a file together, so a
  whole assembly as one file may pair faces of different parts, and costs what all its faces cost at once.
- **Our faces.** Every face in a result is the ordinal the part's refs say (``<owner>/face N``), so a feature's
  faces are the ones ``cad <type> inspect`` names and a check measures. That quiddity's numbering is ours is
  checked against the kernel on every call, face by face, and a part whose faces cannot be shown to be the
  same has no features at all rather than some (``_features``, the gate).
- **A run that ends.** quiddity runs in a process of its own (``_process``, ``_recogniser``, ``_frames``): a part
  it has not answered in ``timeout_s`` is given up and its process stopped, as is one its process holds too much
  memory with, and nothing it does reaches the process that holds the kernel. A part of more faces than
  ``_features.FACES`` is not handed over at all: quiddity's time grows faster than a part's faces, and whether a
  part is read is the part's own, never the speed of the computer that reads it.
- **An honest absence.** A result says ``available``. Where it is False nothing was measured, and ``reason``
  says why (``REASONS``): no wheel for this platform, no environment that holds quiddity (or none in time: no
  part waits on the network for one), a part of too many faces, an input quiddity refused, a run that failed,
  stopped or ran out of time or of memory, an answer this code does not read, a document of another schema, a
  mapping the kernel did not confirm. No call raises for any of these. And an available result is not a
  complete one: quiddity leaves faces ``unexplained`` and says so, so "no hole found" never means "no hole
  there".

**A result** is plain data, JSON-safe, the same for the same part, lengths in millimetres, points and
directions in the coordinates of the shape handed over:

- ``available`` (True), ``version`` (``VERSION``, this shape's own), ``quiddity`` (its release) and ``schema``
  (its recognition document's, ``SCHEMA``);
- ``face_count``; ``run_mode``, ``input_repairs``, ``bodies`` (None for one solid of one shell; else ``solids``,
  ``void_shells`` and ``solid_faces``, each solid's ordinals) and ``frame``, quiddity's own provenance;
  ``unanchored_faces``, the ordinals of the faces quiddity proves no point on, which the gate could not place by
  geometry;
- ``records``: every record quiddity published, in its order, each ``id``, ``family``, ``record_type``,
  ``faces`` (ordinals), ``evidence_status`` (``verified`` or ``unproved``) and ``parameters``, quiddity's own
  and untouched -- so a face index inside ``parameters`` is quiddity's, the ordinal less one;
- ``holes``: the records of the ``holes`` family again, in the words a check reads first: ``id``,
  ``evidence_status``, ``diameter_mm``, ``depth_mm`` (the bore's own length, as quiddity measures it: its
  cylinder's, below a counterbore or a countersink and short of a floor's fillet), ``through`` and ``bottom``
  (quiddity's word: ``through``, ``flat`` and its others), ``point_mm`` (a point on the axis, quiddity's
  ``location``: the mouth of the hole or of its counterbore, and under a countersink or a mouth's chamfer where
  the bore begins), ``axis`` (a unit vector, from that point into the hole), ``counterbore`` and ``spotface``
  (each None, or ``diameter_mm``, ``depth_mm``, its own, and ``faces``), ``outer_counterbores`` (the larger
  steps outside the counterbore, outermost first), ``countersink`` (None, or ``diameter_mm``, ``angle_deg``,
  the cone's included angle, ``depth_mm`` and ``faces``, its cone's), ``mouth_chamfers`` (the small breaks of a
  mouth's edge, which quiddity keeps apart from a countersink: each ``diameter_mm``, the mouth's, ``size_mm``
  across and ``depth_mm`` along the axis, ``angle_deg`` from the face it opens in, and ``faces``) and ``faces``
  (the record's own: the bore's and its steps' cylinders, and the floor of a blind hole where quiddity claims
  it; a countersink's and a chamfer's cones are in theirs);
- ``accounting``: one entry for each face, in ordinal order: ``face``, ``group`` (``GROUPS``) and what quiddity
  says with that group (``record_ids``, ``reason`` or ``refusals``).

A result that is not available is ``available`` (False), ``version``, ``quiddity`` (its release where its
process said it, else None), ``reason`` and ``detail``, one line.

Everything loads on first use: ``import cad.quiddity`` imports no quiddity and no kernel.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from cad.quiddity._features import GROUPS, REASONS, SCHEMA, VERSION
from cad.quiddity._process import TIMEOUT_S

#: Nothing here is public: this is the library's own, for its manufacturing check's holes
#: (``cad.build123d._dfm_cnc_recognised``), as the coacd integration backs ``cad.mujoco.decompose``. Its names
#: may change in any release.
__all__: list[str] = []


def features(part: Any, *, timeout_s: float = TIMEOUT_S) -> dict[str, Any]:
    """The features quiddity finds on one part: ``part`` a build123d shape (one solid, or a compound of them),
    read alone and as it stands. The result is plain data (this module's docstring): ``available`` True with
    the ``records``, the ``holes`` and the ``accounting`` of every face, each face its ordinal on the part; or
    ``available`` False with the ``reason`` nothing was measured. A part quiddity has not answered in
    ``timeout_s`` seconds is ``timed_out``; a ``timeout_s`` that is no positive, finite number is refused
    (``ValueError``)."""
    return features_of([part], timeout_s=timeout_s)[0]


def features_of(parts: Iterable[Any], *, timeout_s: float = TIMEOUT_S) -> list[dict[str, Any]]:
    """``features`` of each of ``parts``, in order, each part read alone: one recogniser process for them all,
    so a document's parts cost one start. ``timeout_s`` is each part's own."""
    from cad.quiddity import _features

    return _features.features_of(parts, timeout_s)
