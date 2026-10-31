"""PMI in the stills is the viewer's: `engine/render/pmi.py` ports what a callout says and where it
stands, and is held to the constructions the viewer's own layout made
(`packages/core/src/lib/xbf/__fixtures__/pmi_plate/constructions.json`, which `xbfPmiLayout.test.js`
holds the viewer to), over the plate the engine served (`__fixtures__/pmi_plate`): as its code
placed its PMI, with no placement at all, after the edit that left the hole's callouts invalid, and
with every kind (v4: limits, a surface profile, the general profile, a general and a flag note),
placed, unplaced and as its view A-A places and shows it, to 1e-6. Its words are the viewer's to
the rounding (JavaScript's `toFixed`); a part placed twice has its PMI drawn at its first placement
shown, and its views seen from there; what is not drawn is said, and why (a note: listed, not
drawn). Painted onto a frame of numpy bytes, every label is over every line and a broken reference
is dashed in its status's red. No node runs, and none of this needs OpenGL.

And a still of a document carrying PMI draws it -- by default, as the viewer shows it, and not with
`display.pmi` false -- every callout inside the picture, as its golden (`render_golden/pmi.png`,
held, written and printed on a miss in CI as `test_render.py` holds its own), and reports what it
left out (`pmiLeftOut`); asking for it where it cannot be drawn (a document with none, the parts
exploded, posed or in Preview) is refused by name. A view's still (`--view`) is drawn down its
camera, cut by its section, its PMI alone at its placements (`render_golden/pmi-view.png`); an
unknown view, a view with a camera of its own or a clip, a view with a section on an exploded
picture, and a view whose section its placement turns off the world's axes are refused by name. Drawing needs an OpenGL context
(`tests/python/support/opengl.py`): skipped, saying why, where none can be made."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from cadgen.engine.mesh import Mesh
from cadgen.engine.render import pmi
from cadgen.engine.snapshot import SnapshotRefused, Still, draws_pmi, job_pictures, parse_display
from tests.python.packages.cadgen.engine.test_render import GOLDEN, PLATFORM, WRITE, build, gl, mismatch, pixels, served

FIXTURES = Path(__file__).resolve().parents[5] / "packages" / "core" / "src" / "lib" / "xbf" / "__fixtures__" / "pmi_plate"
TOLERANCE = 1e-6


def fixture(version: str) -> tuple[dict, dict]:
    """The plate as the engine served it to the viewer: its structure and each part's mesh."""
    structure = json.loads((FIXTURES / version / "structure.json").read_text(encoding="utf-8"))
    meshes = {p["key"]: Mesh.from_bytes((FIXTURES / version / f"{p['key']}.xbm").read_bytes()) for p in structure["prototypes"]}
    return structure, meshes


def reversed_basic(item: dict) -> dict:
    """A basic dimension the other way round, from the hole's axis to its side, placed nowhere; any
    other entry as it is."""
    if not (item.get("dimension") or {}).get("basic"):
        return item
    refs = [{**ref, "role": "to" if ref["role"] == "from" else "from"} for ref in reversed(item["refs"])]
    return {**item, "presentation": None, "refs": refs}


class PmiParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.golden = json.loads((FIXTURES / "constructions.json").read_text(encoding="utf-8"))

    def assert_near(self, found, expected, where: str) -> None:
        if isinstance(expected, list):
            self.assertEqual(len(found), len(expected), where)
            for at, (value, want) in enumerate(zip(found, expected)):
                self.assert_near(value, want, f"{where}[{at}]")
        elif isinstance(expected, dict):
            self.assertEqual(sorted(found), sorted(expected), where)
            for key, want in expected.items():
                self.assert_near(found[key], want, f"{where}.{key}")
        elif isinstance(expected, float) or (isinstance(expected, int) and not isinstance(expected, bool)):
            self.assertLessEqual(abs(found - expected), TOLERANCE, f"{where}: {found} is not {expected}")
        else:
            self.assertEqual(found, expected, where)

    def test_each_callout_stands_where_the_viewer_puts_it(self) -> None:
        self.assertEqual(sorted(self.golden), ["v1", "v1-reversed", "v1-unplaced", "v3", "v4", "v4-A-A", "v4-unplaced"])
        for name, expected in self.golden.items():
            version, _sep, variant = name.partition("-")
            structure, meshes = fixture(version)
            view = None
            if variant == "unplaced":
                structure = {**structure, "pmi": [{**item, "presentation": None} for item in structure["pmi"]]}
            elif variant == "reversed":
                structure = {**structure, "pmi": [reversed_basic(item) for item in structure["pmi"]]}
            elif variant:
                # A view (v4's A-A): the golden its placements made of every callout, of which it shows its own.
                view = next(item for item in pmi.views(structure) if item["name"] == variant)
                expected = [item for item in expected if item["id"] in view["shows"]]
            made = pmi.constructions(structure, meshes, pmi.rest_bounds(structure, meshes), view=view)
            # What it draws, as the viewer's loop lists it; in JSON's own spelling: no tuples, no NaN.
            found = [{"id": entry["id"], "construction": construction} for entry, construction in made
                     if construction is not None]
            self.assert_near(json.loads(json.dumps(found)), expected, name)

    def test_what_a_callout_says_is_what_the_viewer_says(self) -> None:
        structure, _meshes = fixture("v1")
        said = {entry["id"]: pmi.callout(entry) for entry in pmi.entries(structure)}
        self.assertEqual([item["kind"] for item in said.values()], ["datum", "dimension", "dimension", "dimension", "dimension", "frame", "frame"])
        self.assertEqual(said["A"]["letter"], "A")
        self.assertEqual([said["thickness"]["nominal"], said["thickness"]["tolerance"]["text"], said["thickness"]["basic"]], ["10.0", "±0.2", False])
        hole = said["hole-diameter"]
        self.assertEqual([hole["diameter"], hole["nominal"], hole["tolerance"]["upper"], hole["tolerance"]["lower"]], [True, "10.0", "+0.1", "0"])
        # Exact: boxed, no tolerance.
        self.assertEqual([said["hole-from-front"][key] for key in ("basic", "nominal", "tolerance")], [True, "30", None])
        position = said["hole-position"]
        self.assertEqual([position["characteristic"], position["diameter"], position["value"], position["datums"]], ["position", True, "0.1", ["A"]])
        broken, _ = fixture("v3")
        hole = next(entry for entry in pmi.entries(broken) if entry["id"] == "hole-diameter")
        self.assertEqual([hole["status"], hole["supported"], pmi.callout(hole)["nominal"]], ["invalid", True, "?"])

    def test_limits_profiles_and_notes_say_what_the_viewer_says(self) -> None:
        structure, _meshes = fixture("v4")
        said = {entry["id"]: pmi.callout(entry) for entry in pmi.entries(structure)}
        # Limits in place of a nominal: the least size and the greatest at one places count, the upper over the lower.
        thickness = said["thickness"]
        self.assertEqual([thickness["nominal"], thickness["text"], thickness["tolerance"]["upper"],
                          thickness["tolerance"]["lower"]], [None, "9.8–10.2", "10.2", "9.8"])
        profile = said["hole-profile"]
        self.assertEqual([profile[key] for key in ("kind", "characteristic", "value", "datums", "title", "text")],
                         ["frame", "surface_profile", "0.2", ["A"], "Surface profile", "Surface profile 0.2 | A"])
        # The general profile is the part's Note 1, said as a drawing's notes say it; then its notes in their numbers.
        self.assertEqual(said["general"], {"kind": "general_profile", "number": 1, "title": "Note 1",
                                           "text": "Unless otherwise noted, all surfaces profile 0.5 to A"})
        self.assertEqual(said["edges"], {"kind": "note", "number": 2, "flag": False, "title": "Note 2",
                                         "text": "Break all sharp edges 0.2 max"})
        self.assertEqual([said["mask"][key] for key in ("kind", "number", "flag", "title")], ["note", 3, True, "Note 3"])
        # A limits dimension needs no nominal (a file states limits alone); one with deviations does.
        found = pmi.entries({"pmi": [
            {"id": "limits", "kind": "dimension", "status": "ok",
             "dimension": {"type": "distance", "tolerance": {"type": "limits", "lower": 9.8, "upper": 10.2}}},
            {"id": "deviations", "kind": "dimension", "status": "ok",
             "dimension": {"type": "distance", "tolerance": {"type": "plus_minus", "lower": -0.1, "upper": 0.1}}},
            {"id": "general-flat", "kind": "geometric_tolerance", "status": "ok",
             "geometric_tolerance": {"characteristic": "flatness", "value": 0.1, "general": True}},
            {"id": "blank", "kind": "note", "status": "ok", "note": {"number": 2, "text": " "}},
            {"id": "unnumbered", "kind": "note", "status": "ok", "note": {"text": "Deburr"}}]})
        self.assertEqual([entry["unsupported"] for entry in found], [
            "", "it has no nominal", "a general flatness is not one the viewer draws", "it has no text", "it has no number"])

    def test_a_basic_dimension_between_two_holes_is_measured_square_to_both(self) -> None:
        # The bracket's hole (r 4, its axis z through the origin) and a peg (r 3, its axis z through x 12).
        hole = {"surface": {"type": "cylinder", "axis": [0, 0, 1], "origin": [0, 0, 0], "radius": 4},
                "points": [[4, 0, 2], [-4, 0, 2], [0, 4, -2]]}
        peg = {"surface": {"type": "cylinder", "axis": [0, 0, -1], "origin": [12, 0, 8], "radius": 3}, "points": [[15, 0, 2]]}
        entry = {"id": "peg-from-hole", "kind": "dimension", "presentation": {"anchor": [0, 0, 2], "offset": [6, -8, 0]},
                 "dimension": {"type": "distance", "basic": True, "nominal": 12.0, "tolerance": None}}
        made = pmi.construction(entry, {"from": hole, "to": peg}, ([-20, -10, -2], [20, 10, 14]))
        self.assert_near(made["label"], [6, -8, 2], "the label")
        self.assert_near(made["dimension"]["from"], [0, -8, 2], "at the hole's axis, level with the label")
        self.assert_near(made["dimension"]["to"], [12, -8, 2], "at the peg's")
        self.assert_near(made["dimension"]["extensions"][0][0], [0, 0, 2], "from the hole's centre line")
        self.assert_near(made["dimension"]["extensions"][1][0], [12, 0, 2], "from the peg's centre line")
        # Axes that are not parallel measure nothing.
        crossed = {"surface": {"type": "cylinder", "axis": [1, 0, 0], "origin": [0, 5, 0], "radius": 1}, "points": [[0, 6, 0]]}
        self.assertTrue(pmi.construction(entry, {"from": hole, "to": crossed}, None)["broken"])

    def test_numbers_are_written_as_the_viewer_writes_them(self) -> None:
        self.assertEqual(pmi.number(-0.0000001, 2), "0.00")
        self.assertEqual(pmi.number(12.5), "12.5")
        self.assertEqual(pmi.number(-0.05, 2), "−0.05")
        # JavaScript's toFixed rounds the double itself, a tie to the larger: 0.125 is one, and 8.35
        # is a little under 8.35, so it is 8.3 (what node says of each).
        self.assertEqual(pmi.number(0.125, 2), "0.13")
        for value, places, said in ((8.35, 1, "8.3"), (2.675, 2, "2.67"), (1.45, 1, "1.4"), (0.045, 2, "0.04"),
                                    (0.075, 2, "0.07"), (0.15, 1, "0.1"), (-8.35, 1, "−8.3")):
            self.assertEqual(pmi.number(value, places), said, value)
        self.assertEqual(pmi.tolerance_text({"upper": 0.05, "lower": -0.1})["text"], "+0.05/−0.10")

    def test_a_nominal_is_written_at_its_tolerance_s_places_or_its_own_if_more(self) -> None:
        def said(kind: str, nominal: float, within: float | None = None, basic: bool = False) -> list:
            tolerance = {"type": "plus_minus", "upper": within, "lower": -within} if within else None
            dimension = {"type": kind, "basic": basic, "nominal": {"value": nominal}, "tolerance": tolerance}
            entry = {"id": "d", "kind": "dimension", "status": "ok", "dimension": dimension}
            found = pmi.callout(pmi.entries({"pmi": [entry]})[0])
            return [found["nominal"], (found["tolerance"] or {}).get("text")]

        self.assertEqual(said("diameter", 6.35, 0.1), ["6.35", "±0.1"])
        self.assertEqual(said("distance", 25.4, 0.05), ["25.40", "±0.05"])
        self.assertEqual(said("distance", 3.175, basic=True), ["3.175", None])
        self.assertEqual(said("distance", 12.0625), ["12.0625", None])

    def test_a_part_s_pmi_is_drawn_at_its_first_placement_shown(self) -> None:
        structure, meshes = fixture("v1")
        built = pmi.constructions(structure, meshes, pmi.rest_bounds(structure, meshes))
        placed = twice(structure)
        bounds = pmi.rest_bounds(placed, meshes)
        for hidden, matrix in ((frozenset(), TURNED), (frozenset({0}), FLIPPED)):
            made = pmi.constructions(placed, meshes, bounds, hidden)
            found = [{"id": entry["id"], "construction": construction} for entry, construction in made]
            expected = [{"id": entry["id"], "construction": moved(made, matrix)} for entry, made in built]
            self.assert_near(json.loads(json.dumps(found)), expected, f"hidden {sorted(hidden)}")
        # Neither placement shown: none drawn.
        made = pmi.constructions(placed, meshes, bounds, frozenset({0, 1}))
        self.assertEqual([construction for _entry, construction in made], [None] * len(built))

    def test_what_a_still_leaves_out_is_said_with_why(self) -> None:
        structure, meshes = fixture("v3")
        # The hole's callouts the edit broke, placed nowhere; and one the viewer does not draw.
        broken = [item if item["status"] == "ok" else {**item, "presentation": None} for item in structure["pmi"]]
        square = {"id": "square", "kind": "geometric_tolerance", "status": "ok", "part": 0,
                  "geometric_tolerance": {"characteristic": "perpendicularity", "value": 0.1}}
        structure = {**structure, "pmi": [*broken, square]}
        found = pmi.constructions(structure, meshes, pmi.rest_bounds(structure, meshes))
        nowhere = "no feature to stand it on and no placement in its code"
        self.assertEqual(pmi.left_out(structure, found), [
            *({"id": ident, "part": "plate", "status": "invalid", "reason": nowhere}
              for ident in ("hole-diameter", "hole-from-front", "hole-position")),
            {"id": "square", "part": "plate", "status": "ok",
             "reason": "perpendicularity is not one the viewer draws"}])
        # A part no placement of which is shown: each of its annotations left out, saying so.
        built, meshes = fixture("v1")
        placed, hidden = twice(built), frozenset({0, 1})
        found = pmi.constructions(placed, meshes, pmi.rest_bounds(placed, meshes), hidden)
        self.assertEqual({(item["part"], item["reason"]) for item in pmi.left_out(placed, found, hidden)},
                         {("plate", "no placement of its part is shown")})
        self.assertEqual(len(pmi.left_out(placed, found, hidden)), len(found))

    def test_notes_are_left_out_with_why_and_a_view_leaves_out_none_of_another_s(self) -> None:
        structure, meshes = fixture("v4")
        # A flag note naming annotations alone stands on no face: listed, as a general note is.
        inspect = {"id": "inspect", "kind": "note", "status": "ok", "part": 0, "refs": [],
                   "note": {"number": 4, "text": "Inspect every part", "general": False, "annotations": ["thickness"]}}
        structure = {**structure, "pmi": [*structure["pmi"], inspect]}
        bounds = pmi.rest_bounds(structure, meshes)
        found = pmi.constructions(structure, meshes, bounds)
        note = "a note: the viewer lists it, a still does not draw it"
        self.assertEqual(pmi.left_out(structure, found), [
            {"id": ident, "part": "plate", "status": "ok", "reason": note} for ident in ("general", "edges", "inspect")])
        # In a view what it does not show is no part of it: drawn nowhere, and not left out of it.
        view = next(item for item in pmi.views(structure) if item["name"] == "A-A")
        found = pmi.constructions(structure, meshes, bounds, view=view)
        self.assertEqual([entry["id"] for entry, made in found if made is not None], view["shows"])
        self.assertEqual(pmi.left_out(structure, found, view=view), [])

    def test_a_view_is_seen_from_its_part_s_first_placement_shown(self) -> None:
        structure, _meshes = fixture("v4")
        views = pmi.views(structure)
        self.assertEqual([(view["key"], view["supported"]) for view in views], [("0:A-A", True), ("0:iso", True)])
        a = views[0]
        self.assertEqual((a["camera"]["direction"], a["section"], a["shows"]),
                         ([0.0, -1.0, 0.0], {"axis": "y", "at": 0.0, "invert": True},
                          ["hole-diameter", "hole-position", "hole-profile", "mask"]))
        self.assertEqual(pmi.view_at(a, structure), {"instance": 0, "direction": [0.0, -1.0, 0.0], "up": [0.0, 0.0, 1.0],
                                                     "section": {"axis": "y", "at": 0.0, "invert": True}, "section_off": False})
        # Placed elsewhere, its camera turns with the placement and its section is the Clip's along the
        # world axis its own now is, keeping the side it kept: TURNED takes y to -x, FLIPPED to -y.
        placed = twice(structure)
        turned, flipped = pmi.view_at(a, placed), pmi.view_at(a, placed, frozenset({0}))
        self.assert_near([turned["direction"], turned["up"]], [[1, 0, 0], [0, 0, 1]], "turned")
        self.assertEqual(turned["section"], {"axis": "x", "at": 100.0, "invert": False})
        self.assert_near([flipped["direction"], flipped["up"]], [[0, 1, 0], [0, 0, -1]], "flipped")
        self.assertEqual((flipped["instance"], flipped["section"]), (1, {"axis": "y", "at": 0.0, "invert": False}))
        # Turned off every world axis, it is not cut along another: no section, and said.
        eighth = {**structure, "instances": [{**structure["instances"][0], "matrix": EIGHTH}]}
        self.assertEqual([pmi.view_at(a, eighth)[key] for key in ("section", "section_off")], [None, True])
        self.assertIsNone(pmi.view_at(a, placed, frozenset({0, 1})), "its part shown nowhere")
        # One the viewer cannot apply says why.
        found = pmi.views({"pmi_views": [{"part": 0, "name": "bare"}, {"part": 0, "name": "cut", "camera": a["camera"],
                                                                         "section": {"axis": "w", "at": 0, "invert": True}},
                                         {"part": 0, "name": "some", "camera": a["camera"], "shows": "mask"}]})
        self.assertEqual([view["unsupported"] for view in found], [
            "it has no camera", "its section is not one the viewer applies", "what it shows is not a list of ids"])

    def test_an_annotation_is_known_by_its_part_and_its_id(self) -> None:
        # An id is unique only on its part (`readXbfPmi`'s `key`): kept as written, one repeated on a
        # part or lacking kept apart by its place.
        datum = {"kind": "datum", "status": "ok", "datum": {"letter": "A"}}
        found = pmi.entries({"pmi": [{**datum, "id": "A", "part": 0}, {**datum, "id": "A", "part": 1},
                                     {**datum, "id": "A", "part": 0}, datum]})
        self.assertEqual([(entry["id"], entry["key"]) for entry in found],
                         [("A", "0:A"), ("A", "1:A"), ("A", "0:A#3"), ("#4", ":#4")])
        # The plate's datum A drawn, and a lid's datum A, the lid placed nowhere, left out: each its own.
        structure, meshes = fixture("v1")
        lid = {**datum, "id": "A", "part": 1, "presentation": {"anchor": [0, 0, 0], "offset": [0, 0, 5]}}
        structure = {**structure, "prototypes": [*structure["prototypes"], {**structure["prototypes"][0], "name": "lid"}],
                     "pmi": [*structure["pmi"], lid]}
        found = pmi.constructions(structure, meshes, pmi.rest_bounds(structure, meshes))
        self.assertEqual([(entry["key"], made is not None) for entry, made in found if entry["id"] == "A"],
                         [("0:A", True), ("1:A", False)])
        self.assertEqual(pmi.left_out(structure, found),
                         [{"id": "A", "part": "lid", "status": "ok", "reason": "no placement of its part is shown"}])

    def test_what_the_viewer_does_not_draw_says_why_in_the_document_s_words_where_it_has_them(self) -> None:
        found = pmi.entries({"pmi": [
            {"id": "edge", "kind": "unsupported", "status": "ok", "part": 0, "xcaf_type": "DatumObject",
             "reason": "linked to an edge"},
            {"id": "bare", "kind": "unsupported", "status": "ok", "part": 0, "xcaf_type": "DatumObject"},
            {"id": "square", "kind": "geometric_tolerance", "status": "ok", "part": 0,
             "geometric_tolerance": {"characteristic": "perpendicularity", "value": 0.1}}]})
        self.assertEqual([entry["unsupported"] for entry in found], [
            "linked to an edge", "DatumObject is not one the viewer draws", "perpendicularity is not one the viewer draws"])


# The plate placed twice, neither where it was built (column-major): turned a quarter about Z and
# moved, then turned over about X and moved; and turned an eighth about Z, off every world axis.
TURNED = [0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1, 0, 100, 20, 5, 1]
FLIPPED = [1, 0, 0, 0, 0, -1, 0, 0, 0, 0, -1, 0, -50, 0, 10, 1]
EIGHTH = [0.5 ** 0.5, 0.5 ** 0.5, 0, 0, -(0.5 ** 0.5), 0.5 ** 0.5, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]


def twice(structure: dict) -> dict:
    """The plate placed at ``TURNED`` and at ``FLIPPED``, its PMI's references naming the first, as
    the engine names a part's first occurrence."""
    instance = structure["instances"][0]
    first = [{**item, "refs": [{**ref, "ref": ref["ref"].replace("plate/", "plate/plate.1/", 1)}
                               for ref in item["refs"]]} for item in structure["pmi"]]
    return {**structure, "pmi": first,
            "instances": [{**instance, "matrix": TURNED}, {**instance, "path": "plate/plate.2", "matrix": FLIPPED}],
            "tree": {"name": "plate", "children": [{"name": "plate", "prototype": 0, "instance": 0},
                                                   {"name": "plate", "prototype": 0, "instance": 1}]}}


def moved(construction: dict, matrix: list) -> dict:
    """A construction made at rest, where ``matrix`` (column-major) places its part: its points
    placed, its offset turned."""
    m = np.array(matrix, float).reshape(4, 4).T

    def point(p: list) -> list:
        return (m[:3, :3] @ p + m[:3, 3]).tolist()

    dimension = construction["dimension"]
    return {**construction, "anchor": point(construction["anchor"]), "label": point(construction["label"]),
            "presentation": {"anchor": point(construction["presentation"]["anchor"]),
                             "offset": (m[:3, :3] @ construction["presentation"]["offset"]).tolist()},
            "dimension": dimension and {"from": point(dimension["from"]), "to": point(dimension["to"]),
                                        "extensions": [[point(a), point(b)] for a, b in dimension["extensions"]]}}


def top(points: np.ndarray) -> np.ndarray:
    """The plate fixture from above, onto a 1200 x 900 frame: x right, y up, 6 pixels a millimetre."""
    return np.stack([(points[:, 0] + 100) * 6, (60 - points[:, 1]) * 6], 1)


class PmiPaintTest(unittest.TestCase):
    """The callouts painted over a picture as the viewer's overlay paints them: onto a frame of
    numpy bytes, from above, no OpenGL."""

    def paint(self, drawn: list, project=top) -> np.ndarray:
        # As tall as the viewer (`overlay.REFERENCE_HEIGHT`), so a viewer pixel is one of the frame's.
        frame = np.full((900, 1200, 3), 255, np.uint8)
        pmi.paint(frame, drawn, project, lambda _point: False)
        return frame.astype(np.int16)

    def test_every_label_is_painted_over_every_line(self) -> None:
        # Datum B's leader runs from (200, 300) to its label at (420, 300), under datum A's label at (300, 300).
        a, b = pmi.entries({"pmi": [{"id": letter, "kind": "datum", "status": "ok", "datum": {"letter": letter}}
                                    for letter in "AB"]})
        given = {"dimension": None, "placed": "given"}
        frame = self.paint([(a, {**given, "anchor": [300, 340, 0], "label": [300, 300, 0]}),
                            (b, {**given, "anchor": [200, 300, 0], "label": [420, 300, 0]})], lambda points: points[:, :2])
        self.assertLess(int(frame[300, 250].min()), 200, "B's leader is drawn")
        # Inside A's label, clear of its letter, on the row B's leader takes: A's paper over it.
        self.assertGreater(int(frame[300, 292].min()), 230, "B's leader is over A's label")

    def test_limits_stack_a_profile_takes_its_glyph_and_a_flag_note_its_flag_and_number(self) -> None:
        structure, _meshes = fixture("v4")
        cells = {entry["id"]: pmi._cells(pmi.callout(entry)) for entry in pmi.entries(structure)
                 if entry["supported"] and pmi.drawn_on_part(entry)}
        # Limits alone, the upper over the lower, no nominal beside them.
        [limits] = cells["thickness"]
        self.assertEqual((limits["glyphs"], limits["words"], limits["small"]), ([], "", ("10.2", "9.8")))
        self.assertEqual([cell["glyphs"] for cell in cells["hole-profile"]], [["surface_profile"], [], []])
        [flag] = cells["mask"]
        self.assertEqual((flag["glyphs"], flag["words"]), (["flag"], "3"))
        # Each glyph drawn: ink in its 12 px square.
        for name in ("surface_profile", "flag"):
            frame = np.full((40, 40, 3), 255, np.uint8)
            from cadgen.engine.render.overlay import Painter

            pmi._glyph(Painter(frame, 1.0), name, 10, 20, pmi.INK, 1.0)
            inked = frame.min(axis=2) < 128
            self.assertTrue(inked[14:26, 10:22].any() and not inked[:, :9].any() and not inked[:, 23:].any(), name)

    def test_a_broken_reference_is_dashed_in_its_status_s_colour_round_an_open_ring(self) -> None:
        structure, meshes = fixture("v3")
        made = {entry["id"]: (entry, construction) for entry, construction in
                pmi.constructions(structure, meshes, pmi.rest_bounds(structure, meshes))}
        entry, construction = made["hole-diameter"]  # invalid: the edit left its name on a flat face
        frame = self.paint([(entry, construction)])
        red = (frame[..., 0] - frame[..., 1]) > 60  # the status's red (239, 68, 68) over white
        anchor, label = top(np.array([construction["anchor"], construction["label"]], float))
        way = (label - anchor) / np.linalg.norm(label - anchor)
        across = np.array([-way[1], way[0]])

        def reddened(point: np.ndarray) -> bool:
            x, y = np.floor(point).astype(int)
            return bool(red[y - 1:y + 2, x - 1:x + 2].any())

        # An open ring where it was anchored: red round it, not inside it behind the leader.
        ring = pmi.ARROW_HALF + 1
        for side in (across, -way, -across):
            self.assertTrue(reddened(anchor + side * ring), side)
        x, y = np.floor(anchor - way * 1.5).astype(int)
        self.assertFalse(red[y, x], "the ring is open")
        # Its leader dashed: red, then white, then red again along it.
        steps = np.floor([anchor + way * at for at in np.arange(ring + 2, 40, 0.5)]).astype(int)
        along = [bool(red[y, x]) for x, y in steps]
        self.assertTrue(any(along) and not all(along), along)
        # Its label ruled in dashes of the same red.
        box = pmi._box(entry, construction, lambda point: tuple(top(np.array([point], float))[0]))
        row, left, right = round(box["y"] - box["h"] / 2), round(box["x"] - box["w"] / 2), round(box["x"] + box["w"] / 2)
        rule = red[row - 1:row + 2, left + 3:right - 3].any(0)
        self.assertTrue(rule.any() and not rule.all(), "its label's rule dashed")


# A plate with a hole, its PMI on its own faces: a datum on the bottom, the thickness given its
# limits, a flatness on the top, the hole located by a basic distance from the left side and its
# surface profiled, the general profile (Note 1), a general note and a flag note on the hole; and
# its view A-A, from the front cut through the hole's axis, showing the hole's. Tolerance values and
# note words are illustrative.
PLATE = """
import build123d as bd
from cadgen.ap242 import (annotate, datum, dimensional_location, flatness_tolerance, general_profile, limits, note,
                          place, section, surface_profile_tolerance, view)
from cadgen.engine import xbf

@xbf(out="XBF/plate.xbf")
def plate():
    body = bd.Box(60, 40, 8) - bd.Cylinder(4, 8)
    body.label = "plate"
    bottom, top = body.faces().sort_by(bd.Axis.Z)[0], body.faces().sort_by(bd.Axis.Z)[-1]
    left, hole = body.faces().sort_by(bd.Axis.X)[0], body.faces().filter_by(bd.GeomType.CYLINDER)[0]
    return annotate(body, datum("A", bottom), dimensional_location("thickness", bottom, top, tolerance=limits(7.9, 8.1)),
                    flatness_tolerance("top-flat", top, 0.05), dimensional_location("hole-from-left", left, hole, basic=True),
                    surface_profile_tolerance("hole-profile", hole, 0.1, datums=["A"]),
                    general_profile("general", 0.5, datums=["A"]),
                    note("edges", "Break sharp edges"), note("mask", "Mask before coating", faces=hole),
                    view("A-A", camera="front", shows=["hole-from-left", "hole-profile", "mask"],
                         section=section("y", 0, invert=True),
                         place={"mask": place((0, 4, 0), (10, 0, 10))}))

if __name__ == "__main__":
    plate()
"""


class PmiAskedTest(unittest.TestCase):
    """What a still is asked to draw of the PMI, checked before anything renders: no OpenGL."""

    def test_pmi_is_drawn_by_default_at_rest_and_refused_by_name_where_it_cannot_be(self) -> None:
        carried, bare = {"pmi": [{"id": "A"}]}, {"name": "box"}
        self.assertTrue(draws_pmi(Still(), carried, "plate.xbf"))
        self.assertFalse(draws_pmi(Still(), bare, "box.xbf"), "a document with none draws none, asked for nothing")
        self.assertFalse(draws_pmi(Still(display={"pmi": False}), carried, "plate.xbf"))
        # Moved parts draw none by default, as the viewer shows none; asked for, it is refused.
        self.assertFalse(draws_pmi(Still(display={"exploded": {"enabled": True, "amount": 0.5}}), carried, "plate.xbf"))
        with self.assertRaisesRegex(SnapshotRefused, "on the parts as made; display.exploded moves or restages them"):
            draws_pmi(Still(display={"pmi": True, "exploded": {"enabled": True, "amount": 0.5}}), carried, "plate.xbf")
        with self.assertRaisesRegex(SnapshotRefused, "on the parts as made; --preview moves or restages them"):
            draws_pmi(Still(display={"pmi": True}, preview=True), carried, "plate.xbf")
        with self.assertRaisesRegex(SnapshotRefused, "display.pmi draws a document's PMI; box.xbf carries none"):
            draws_pmi(Still(display={"pmi": True}), bare, "box.xbf")

    def test_a_still_says_what_it_left_out_and_why_beside_its_other_warnings(self) -> None:
        import contextlib
        import io
        import time

        from cadgen.engine import snapshot

        folder = Path(tempfile.mkdtemp(prefix="engine-render-pmi-said-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        nowhere = "no feature to stand it on and no placement in its code"
        report = {"pmi": 1, "timings": {}, "unmeshed": {"plate": [3]}, "pmiLeftOut": [
            {"id": "hole-diameter", "part": "plate", "status": "invalid", "reason": nowhere},
            {"id": "datum-1", "part": None, "status": "ok", "reason": "linked to an edge"},
            {"id": "edges", "part": "plate", "status": "ok", "reason": "a note: the viewer lists it, a still does not draw it"}]}
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            snapshot._written(Path("plate.xbf"), folder / "plate.png", b"png", report, time.perf_counter())
        self.assertEqual(said.getvalue().splitlines()[1:], [
            f"warning: plate: the picture does not draw PMI hole-diameter (invalid): {nowhere}",
            "warning: plate.xbf: the picture does not draw PMI datum-1: linked to an edge",
            "warning: plate: the picture does not draw PMI edges: a note: the viewer lists it, a still does not draw it"])

    def test_display_takes_pmi_as_a_word_or_a_boolean_and_nothing_else(self) -> None:
        self.assertEqual(parse_display("pmi", False), {"pmi": True})
        self.assertEqual(parse_display("hidden-line,pmi=off", False), {"mode": "hidden-line", "pmi": False})
        self.assertEqual(parse_display('{"pmi": false}', False), {"pmi": False})
        with self.assertRaisesRegex(SnapshotRefused, "display.pmi is true or false"):
            parse_display('{"pmi": "yes"}', False)
        with self.assertRaisesRegex(SnapshotRefused, "pmi or pmi=off"):
            parse_display("pmi=maybe", False)

    def test_a_view_is_asked_for_by_name_and_refused_with_a_camera_of_its_own(self) -> None:
        import contextlib
        import io

        from cadgen.engine import snapshot

        # A view is --view's alone: a display object names none.
        with self.assertRaisesRegex(SnapshotRefused, "display has no view; an engine document's display takes"):
            parse_display('{"view": "A-A"}', False)
        folder = Path(tempfile.mkdtemp(prefix="engine-render-pmi-view-")).resolve()
        self.addCleanup(shutil.rmtree, folder, ignore_errors=True)
        document = folder / "plate.xbf"
        document.write_bytes(b"refused before it is read")
        for camera in ("front", "authored"):
            with self.assertRaisesRegex(SnapshotRefused, "--view A-A is seen down its own camera; remove --camera"):
                snapshot.snapshot(document, folder / "out.png", camera=camera, view="A-A", daemon=False)
        said = io.StringIO()
        with contextlib.redirect_stderr(said):
            code = snapshot.main([str(document), str(folder / "out.png"), "--view", "A-A", "--camera", "top"])
        self.assertEqual(code, 2)
        self.assertIn("its own camera", said.getvalue())
        self.assertFalse((folder / "out.png").exists())
        # A job's display names no view; the flag stands in for every job's camera.
        job = {"input": str(document), "outputs": [str(folder / "a.png")]}
        with self.assertRaisesRegex(SnapshotRefused, "display has no view"):
            job_pictures({**job, "display": {"view": "A-A"}})
        [(_document, _out, still)] = job_pictures({**job, "camera": "front"}, view="A-A")
        self.assertEqual((still.view, still.camera), ("A-A", None))

    def test_a_view_the_document_cannot_show_is_refused_by_name_before_anything_renders(self) -> None:
        from cadgen.engine.render.service import Held

        structure = json.loads((FIXTURES / "v4" / "structure.json").read_text(encoding="utf-8"))
        buffers = {p["key"]: (FIXTURES / "v4" / f"{p['key']}.xbm").read_bytes() for p in structure["prototypes"]}
        held = Held(FIXTURES / "v4" / "plate.xbf")
        self.addCleanup(held.close)
        held.hold(structure, buffers)
        for still, said in (
                (Still(view="B-B"), r"plate.xbf has no view 'B-B'; its views are plate/A-A and plate/iso"),
                (Still(view="lid/A-A"), r"plate.xbf has no view 'lid/A-A'"),
                (Still(view="A-A", display={"clip": {"enabled": True, "axis": "x"}}),
                 "view A-A is cut by its own section; remove display.clip"),
                (Still(view="A-A", preview=True), "--view A-A draws its PMI on the parts as made; --preview"),
        ):
            with self.assertRaisesRegex(SnapshotRefused, said):
                held.draw(still)
        self.assertFalse(held.scenes, "nothing was drawn")
        # Its part placed at an angle: a still cuts only square to a world axis, and never along another.
        held.hold({**structure, "version": "eighth", "instances": [{**structure["instances"][0], "matrix": EIGHTH}]}, buffers)
        with self.assertRaisesRegex(SnapshotRefused, "view A-A's section is not on the axes of plate's placement"):
            held.draw(Still(view="A-A"))
        self.assertFalse(held.scenes, "nothing was drawn")

    def test_a_sectioned_view_is_refused_on_an_exploded_picture_whatever_its_pmi(self) -> None:
        """A section is placed on the parts as made, and Explode then moves them: it would cut them in
        the wrong place (law 17), so it is refused by name, its PMI drawn or not; a view of no section
        is its camera alone there."""
        from cadgen.engine.render.service import Held
        from cadgen.engine.snapshot import view_of

        structure = json.loads((FIXTURES / "v4" / "structure.json").read_text(encoding="utf-8"))
        buffers = {p["key"]: (FIXTURES / "v4" / f"{p['key']}.xbm").read_bytes() for p in structure["prototypes"]}
        # The plate placed twice, so Explode has parts to move apart.
        placed = structure["instances"][0]
        twice = {**structure, "version": "twice",
                 "instances": [placed, {**placed, "path": "plate/plate.2", "matrix": [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                                                                                      150, 0, 0, 1]}],
                 "tree": {**structure["tree"], "children": [*structure["tree"]["children"],
                                                            {"name": "plate.2", "prototype": 0, "instance": 1}]}}
        held = Held(FIXTURES / "v4" / "plate.xbf")
        self.addCleanup(held.close)
        held.hold(twice, buffers)
        exploded = {"enabled": True, "amount": 0.5}
        for display, said in (({"pmi": False, "exploded": exploded},
                               "view A-A is cut by its section on the parts as made; display.exploded moves them "
                               "apart. Remove one or the other."),
                              ({"exploded": exploded}, "--view A-A draws its PMI on the parts as made; "
                                                       "display.exploded moves or restages them")):
            with self.assertRaisesRegex(SnapshotRefused, said):
                held.draw(Still(view="A-A", display=display))
        self.assertFalse(held.scenes, "nothing was drawn")
        found = view_of(Still(view="iso", display={"pmi": False, "exploded": exploded}), twice, "plate.xbf", frozenset())
        self.assertEqual((found["view"]["name"], found["at"]["section"]), ("iso", None))


class PmiStillTest(unittest.TestCase):
    """A document carrying PMI, built, served and held by a renderer, drawn."""

    @classmethod
    def setUpClass(cls) -> None:
        gl()
        from cadgen.engine.render.service import Held

        cls.folder = Path(tempfile.mkdtemp(prefix="engine-render-pmi-")).resolve()
        # The engine's own state, should anything here reach for it, is the test's: never the person's.
        cls.state = mock.patch.dict(os.environ, {"CADGEN_ENGINE_DIR": str(cls.folder / "engine"),
                                                 "CADGEN_STATE_DIR": str(cls.folder / "state"),
                                                 "CADGEN_CACHE_DIR": str(cls.folder / "cache")})
        cls.state.start()
        cls.document = build(cls.folder, PLATE, "plate")
        cls.structure, cls.buffers = served(cls.document)
        cls.held = Held(cls.document)
        cls.held.hold(cls.structure, cls.buffers)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.held.close()
        cls.state.stop()
        shutil.rmtree(cls.folder, ignore_errors=True)

    def golden(self, row: str, drawn: bytes) -> None:
        """``drawn`` held to its golden (``render_golden/<row>.png``, a platform's own where it has one)."""
        own = GOLDEN / PLATFORM / f"{row}.png"
        golden = own if own.is_file() else GOLDEN / f"{row}.png"
        if WRITE:
            golden.write_bytes(drawn)
            return
        share = mismatch(pixels(drawn), pixels(golden.read_bytes()))
        if share > 0.015 and os.environ.get("GITHUB_ACTIONS") == "true":
            import base64

            print(f"GOLDEN {PLATFORM}/{row} {base64.b64encode(drawn).decode()}")
        self.assertLessEqual(share, 0.015, f"{row}: {share:.1%} of its pixels are not the golden's")

    def test_a_still_draws_the_document_s_pmi_unless_asked_not_to(self) -> None:
        self.assertEqual([entry["id"] for entry in self.structure["pmi"]], [
            "A", "thickness", "hole-from-left", "top-flat", "hole-profile", "general", "edges", "mask"])
        # As tall as the viewer the callouts are drawn for (`overlay.REFERENCE_HEIGHT`): their words full size.
        drawn, report = self.held.draw(Still(size=(1200, 900)))
        note = "a note: the viewer lists it, a still does not draw it"
        self.assertEqual((report["pmi"], report["pmiLeftOut"]), (6, [
            {"id": ident, "part": "plate", "status": "ok", "reason": note} for ident in ("general", "edges")]), report)
        self.golden("pmi", drawn)
        bare, report_bare = self.held.draw(Still(size=(1200, 900), display={"pmi": False}))
        self.assertNotIn("pmi", report_bare)
        # The callouts' words are the ink, near black: nothing of the model is as dark. The fit takes
        # the callouts in, so the two pictures are framed apart and only the ink is compared.
        inked, inked_bare = pixels(drawn).max(axis=2) < 40, pixels(bare).max(axis=2) < 40
        self.assertEqual(int(inked_bare.sum()), 0)
        self.assertGreater(int(inked.sum()), 60, "the callouts' words are drawn")
        # Every callout inside the picture, clear of its edge.
        rim = np.ones_like(inked)
        rim[3:-3, 3:-3] = False
        self.assertFalse((inked & rim).any(), "a callout runs off the picture")

    def test_a_view_s_still_draws_its_camera_its_section_and_its_pmi(self) -> None:
        drawn, report = self.held.draw(Still(size=(1200, 900), view="A-A"))
        self.assertEqual((report["view"], report["camera"], report["pmi"], report["pmiLeftOut"]), ("A-A", "view", 3, []), report)
        scene = self.held.scenes[False]
        # Down its camera, cut by its section (the Clip's), its PMI alone, the flag note where the view places it.
        self.assert_near(list(scene.camera["direction"]), [0, -1, 0])
        self.assertEqual(scene.display["clip"], {"enabled": True, "axis": "y", "at": 0.0, "invert": True})
        drawn_ids = {entry["id"]: made for entry, made in scene.pmi_drawn}
        self.assertEqual(sorted(drawn_ids), ["hole-from-left", "hole-profile", "mask"])
        self.assert_near(drawn_ids["mask"]["label"], [10, 4, 10])
        self.golden("pmi-view", drawn)
        # What it cuts away hides nothing behind it, as the viewer's pick takes nothing the Clip cut
        # away: the mask's leader, from the hole's far wall, is drawn full.
        from cadgen.engine.render.pmi import Hidden

        self.assertFalse(Hidden(scene, scene.pmi_bounds)(drawn_ids["mask"]["anchor"]))

    def assert_near(self, found: list, expected: list) -> None:
        self.assertLessEqual(max(abs(a - b) for a, b in zip(found, expected)), 1e-6, f"{found} is not {expected}")

    def test_what_a_still_leaves_out_is_reported_with_why(self) -> None:
        # Asked for, and none of it drawable: a datum whose face is gone, placed nowhere, and a
        # characteristic the viewer does not draw.
        from cadgen.engine.render.service import Held

        lost = {"id": "B", "kind": "datum", "status": "missing", "part": 0, "datum": {"letter": "B"},
                "refs": [{"role": "feature", "written": "f:gone", "status": "missing"}]}
        square = {"id": "square", "kind": "geometric_tolerance", "status": "ok", "part": 0,
                  "geometric_tolerance": {"characteristic": "perpendicularity", "value": 0.1}}
        held = Held(self.document)
        self.addCleanup(held.close)
        held.hold({**self.structure, "version": "left-out", "pmi": [lost, square]}, self.buffers)
        _drawn, report = held.draw(Still(size=(320, 240), display={"pmi": True}))
        self.assertEqual(report["pmi"], 0)
        self.assertEqual(report["pmiLeftOut"], [
            {"id": "B", "part": "plate", "status": "missing",
             "reason": "no feature to stand it on and no placement in its code"},
            {"id": "square", "part": "plate", "status": "ok", "reason": "perpendicularity is not one the viewer draws"}])

    def test_a_part_placed_twice_has_its_pmi_drawn_and_framed_where_it_is_shown(self) -> None:
        from cadgen.engine.render.service import Held

        held = Held(self.document)
        self.addCleanup(held.close)
        held.hold({**twice(self.structure), "version": "twice"}, self.buffers)
        # TURNED stands the plate at x 80 to 120, FLIPPED at x -80 to -20: its callouts beside it.
        for hide, side in (("plate/plate.2", 1), ("plate/plate.1", -1)):
            _drawn, report = held.draw(Still(size=(320, 240), display={"hidden": [hide]}))
            self.assertEqual((report["pmi"], len(report["pmiLeftOut"])), (6, 2), hide)
            fitted = held.scenes[False].pmi_points[:, 0] * side
            self.assertGreater(float(fitted.min()), 0, f"{hide} hidden: the callouts and the fit at the other")
        # Its view is seen from there too: TURNED takes the front to +x, and the cut across y to one across x.
        _drawn, report = held.draw(Still(size=(320, 240), view="A-A", display={"hidden": ["plate/plate.2"]}))
        scene = held.scenes[False]
        self.assertEqual((report["view"], report["pmi"]), ("A-A", 3))
        self.assert_near(list(scene.camera["direction"]), [1, 0, 0])
        self.assertEqual(scene.display["clip"], {"enabled": True, "axis": "x", "at": 100.0, "invert": False})
        self.assertGreater(float(scene.pmi_points[:, 0].min()), 0, "its callouts at the plate it is seen from")

    def test_asking_for_pmi_on_moved_parts_is_refused_before_anything_renders(self) -> None:
        with self.assertRaisesRegex(SnapshotRefused, "on the parts as made; --preview moves or restages them"):
            self.held.draw(Still(size=(160, 120), display={"pmi": True}, preview=True))


if __name__ == "__main__":
    unittest.main()
