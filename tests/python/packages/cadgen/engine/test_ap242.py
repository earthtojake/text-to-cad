"""An exported file's requirements must match its source, without guessing identities
(``export/ap242.py``): the AP242 reader of no OCCT, and ``compare``/``check`` of a document's PMI
against the file it wrote, each part against its own product's records."""

from __future__ import annotations

import copy
import hashlib
import re
import shutil
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from cadgen.engine.export.ap242 import Report, check, parse, report
from cadgen.engine.export.ap242 import compare as _compare

# The one part of the fixtures' document, by its index, as the file names its product.
PARTS = {0: "part"}


def compare(entries: list[dict], found: dict, surfaces: dict | None = None, parts: dict | None = None) -> dict:
    """``ap242.compare`` of the fixtures' document: its part named ``part``, unless ``parts`` say."""
    return _compare(entries, found, surfaces, PARTS if parts is None else parts)


def fixtures(part: int = 0, product: str = "part") -> tuple[list[dict], dict]:
    """Three entries as a document serves them, of its part ``part``, and the report of a file that
    holds them, in its product ``product``."""
    entries = [
        {"id": "A", "kind": "datum", "status": "ok", "part": part, "refs": [{"ref": f"{product}/f:base.1"}],
         "datum": {"letter": "A"}},
        {"id": "bore", "kind": "dimension", "status": "ok", "part": part, "refs": [{"ref": f"{product}/f:bore.1"}],
         "dimension": {"type": "diameter", "nominal": {"value": 10, "unit": "mm"},
                       "tolerance": {"type": "plus_minus", "lower": 0, "upper": 0.05}}},
        {"id": "position", "kind": "geometric_tolerance", "status": "ok", "part": part,
         "refs": [{"ref": f"{product}/f:bore.1"}],
         "geometric_tolerance": {"characteristic": "position", "value": 0.1, "unit": "mm", "zone": "diameter",
                                 "datums": ["A"]}},
    ]
    found = {"schema": "AP242_TEST", "problems": [], "products": [product], "ambiguousFaceNames": {product: []},
             "datums": [{"identification": "A", "features": [{"name": "f:base.1"}], "product": product}],
             "dimensions": [{"name": "diameter", "features": [{"name": "f:bore.1"}], "product": product,
                             "nominal": {"value": 10, "unit": "mm"},
                             "tolerance": {"lower": 0, "upper": 0.05, "unit": "mm"}}],
             "tolerances": [{"entity": "POSITION_TOLERANCE", "features": [{"name": "f:bore.1"}], "product": product,
                             "magnitude": {"value": 0.1, "unit": "mm"}, "zone": "cylindrical or circular",
                             "datums": ["A"]}]}
    return entries, found


class VerificationTest(unittest.TestCase):
    def test_matches_and_detects_changed_values_units_faces_datums_and_extras(self) -> None:
        entries, found = fixtures()
        self.assertEqual(compare(entries, found), {"matched": 3, "total": 3, "problems": []})
        for collection, key, value in [("dimensions", "tolerance", {"lower": 0, "upper": 0.5, "unit": "mm"}),
                                       ("tolerances", "magnitude", {"value": 0.1, "unit": "m"}),
                                       ("datums", "features", [{"name": "f:wrong.1"}]),
                                       ("tolerances", "datums", ["B"])]:
            changed = copy.deepcopy(found)
            changed[collection][0][key] = value
            self.assertTrue(compare(entries, changed)["problems"])
        found["dimensions"] *= 2
        self.assertTrue(compare(entries, found)["problems"])

    def test_a_check_that_could_not_be_made_fails_as_a_mismatch_does(self) -> None:
        """An entry held to the file and not matched is a problem; so is a file that cannot be
        checked at all (no AP242, a record the reader does not read, a face name it cannot tell
        apart): each refuses the STEP of a document the code made (``pmi.checked``), never a
        warning beside a file written unverified."""
        entries, found = fixtures()
        self.assertEqual(compare(entries, found), {"matched": 3, "total": 3, "problems": []})
        changed = copy.deepcopy(found)
        changed["dimensions"][0]["nominal"]["value"] = 11
        self.assertTrue(compare(entries, changed)["problems"])
        for unverifiable in ({**found, "schema": "AP214"}, {**found, "problems": ["#9 is not read here"]},
                             {**found, "ambiguousFaceNames": {"part": ["f:bore.1"]}}):
            result = compare(entries, unverifiable)
            self.assertEqual(result["matched"], 0, unverifiable)
            self.assertTrue(result["problems"])

    def test_each_part_is_matched_within_its_own_product(self) -> None:
        """Two parts of one document made by one function reuse every face name and datum letter:
        each part's entries are held to its own product's records alone, so all six match, where a
        check across the file would verify none. A record of one part on another's faces, or measured
        from another's datum (its ``product`` None), matches nothing; two products of one name verify
        neither part's."""
        first, found = fixtures(0, "a")
        second, other = fixtures(1, "b")
        both = {**found, "products": ["a", "b"], "ambiguousFaceNames": {"a": [], "b": []},
                **{key: found[key] + other[key] for key in ("datums", "dimensions", "tolerances")}}
        parts = {0: "a", 1: "b"}
        self.assertEqual(compare(first + second, both, parts=parts), {"matched": 6, "total": 6, "problems": []})
        # b's position measured from a's datum A (OCCT's writer writes one DATUM per letter in a file).
        crossed = copy.deepcopy(both)
        crossed["tolerances"][1]["product"] = None
        crossed["datums"].pop(1)
        result = compare(first + second, crossed, parts=parts)
        self.assertEqual(result["matched"], 4)
        self.assertIn("b/A: values, units, datum order or face association could not be verified.", result["problems"])
        self.assertIn("Datum A is defined on 2 parts: the STEP writer writes one datum of a letter per file; give "
                      "each part's datums letters of their own.", result["problems"])
        self.assertIn("1 exported annotations did not match the model.", result["problems"])
        # A face name ambiguous in b's product, or two products named b: b's entries verify nothing.
        for altered, said in (({**both, "ambiguousFaceNames": {"a": [], "b": ["f:bore.1"]}},
                               "part b: an exported face name is ambiguous across its geometry"),
                              ({**both, "products": ["a", "b", "b"]}, "part b: 2 products of the file are named 'b'"),
                              ({**both, "datums": both["datums"] + [other["datums"][0]]},
                               "part b: its exported datum letters are repeated")):
            result = compare(first + second, altered, parts=parts)
            self.assertEqual(result["matched"], 3, said)
            self.assertTrue(any(problem.startswith(said) for problem in result["problems"]), result["problems"])
        # Two parts of one name: neither is told apart.
        result = compare(first + second, both, parts={0: "a", 1: "a"})
        self.assertEqual(result["matched"], 0)

    def test_given_the_models_faces_each_face_is_held_to_its_geometry(self) -> None:
        """A face of the right name on another surface matches nothing: a plane's normal and offset,
        a cylinder's radius and axis, each against the model's face (``pmi.step_surfaces``)."""
        entries, found = fixtures()
        base = {"type": "plane", "origin": [0, 0, -5], "normal": [0, 0, 1]}
        bore = {"type": "cylinder", "radius": 5.0, "origin": [10, 0, 0], "axis": [0, 0, 1]}
        surfaces = {"part/f:base.1": base, "part/f:bore.1": bore}
        found["datums"][0]["features"][0]["surface"] = {"type": "plane", "origin": [7, 3, -5], "normal": [0, 0, -1]}
        for row in found["dimensions"] + found["tolerances"]:
            row["features"][0]["surface"] = {**bore, "origin": [10, 0, 40]}
        self.assertEqual(compare(entries, found, surfaces), {"matched": 3, "total": 3, "problems": []})
        for collection, surface in [("datums", {**base, "origin": [0, 0, 5]}),
                                    ("datums", {**base, "normal": [0, 1, 0]}),
                                    ("datums", {**bore}),
                                    ("dimensions", {**bore, "radius": 5.1}),
                                    ("dimensions", {**bore, "origin": [10, 1, 0]}),
                                    ("dimensions", {**bore, "axis": [0, 1, 1]})]:
            changed = copy.deepcopy(found)
            changed[collection][0]["features"][0]["surface"] = surface
            result = compare(entries, changed, surfaces)
            self.assertEqual(result["matched"], 2, (collection, surface))
            self.assertTrue(any("is not the model's face" in problem for problem in result["problems"]), result)
        # A face the model's faces do not hold matches nothing; without them the names alone are checked.
        self.assertEqual(compare(entries, found, {"part/f:base.1": base})["matched"], 1)
        self.assertEqual(compare(entries, found)["matched"], 3)

    def test_ambiguous_associations_fail_closed(self) -> None:
        entries, found = fixtures()
        for altered in [{**found, "ambiguousFaceNames": {"part": ["f:bore.1"]}},
                        {key: value for key, value in found.items() if key != "ambiguousFaceNames"},
                        {**found, "datums": found["datums"] * 2},
                        {**found, "problems": ["Mixed deviation units"]},
                        {**found, "schema": "AUTOMOTIVE_DESIGN"}]:
            self.assertEqual(compare(entries, altered)["matched"], 0)
        # Two faces of the part share a name; a part the document names no product for.
        other = copy.deepcopy(entries[1])
        other["refs"][0]["ref"] = "other/f:bore.1"
        self.assertEqual(compare(entries + [other], found)["matched"], 0)
        self.assertEqual(compare(entries, found, parts={})["matched"], 0)

    def test_unsupported_modifiers_and_empty_pmi_never_claim_success(self) -> None:
        entries, found = fixtures()
        entries[2]["geometric_tolerance"]["modifier"] = "maximum_material_condition"
        self.assertEqual(compare(entries, found)["matched"], 2)
        self.assertTrue(compare([], {**found, "datums": [], "dimensions": [], "tolerances": []})["problems"])

    def test_checks_the_provided_export_and_binds_result_to_its_bytes(self) -> None:
        entries, found = fixtures()
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "export.step"
            target.write_bytes(b"exported bytes")
            with patch("cadgen.engine.export.ap242.report", return_value=found) as reader:
                result = check(entries, target, None, PARTS)
            reader.assert_called_once_with(target, b"exported bytes")
            self.assertEqual(result["matched"], 3)
            self.assertEqual(result["sha256"], hashlib.sha256(b"exported bytes").hexdigest())
            with patch("cadgen.engine.export.ap242.report", side_effect=ValueError("unsupported syntax")):
                self.assertTrue(check(entries, target, None, PARTS)["problems"])

    def test_a_note_is_never_counted_even_where_the_check_fails(self) -> None:
        """A STEP carries no note: a failed check counts the GD&T alone, as a completed one does."""
        entries, _found = fixtures()
        note = {"id": "deburr", "kind": "note", "status": "ok", "refs": [],
                "note": {"number": 1, "text": "Break all sharp edges 0.2 max", "general": True, "annotations": []}}
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "export.step"
            target.write_bytes(b"exported bytes")
            with patch("cadgen.engine.export.ap242.report", side_effect=ValueError("unsupported syntax")):
                result = check([entries[0], note], target, None, PARTS)
        self.assertEqual((result["matched"], result["total"]), (0, 1))
        self.assertEqual(result["problems"], ["The STEP reader could not complete the check: unsupported syntax"])

    def test_a_basic_flag_the_file_does_not_carry_is_not_verified(self) -> None:
        entries, found = fixtures()
        entries.append({"id": "hole-from-B", "kind": "dimension", "status": "ok", "part": 0,
                        "refs": [{"ref": "part/f:front.1"}, {"ref": "part/f:bore.1"}],
                        "dimension": {"type": "distance", "basic": True, "nominal": {"value": 30, "unit": "mm"},
                                      "tolerance": None}})
        row = {"name": "linear distance", "features": [{"name": "f:front.1"}, {"name": "f:bore.1"}], "product": "part",
               "nominal": {"value": 30, "unit": "mm"}, "tolerance": None, "notes": [["dimensional note", "theoretical"]]}
        self.assertEqual(compare(entries, {**found, "dimensions": found["dimensions"] + [row]})["matched"], 4)
        bare = {**row, "notes": []}  # the same distance with no 'theoretical' note: not the basic one modelled
        self.assertEqual(compare(entries, {**found, "dimensions": found["dimensions"] + [bare]})["matched"], 3)

    def test_limits_match_by_value_and_unit_and_never_as_a_plus_minus(self) -> None:
        """A dimension given limits matches a row of the same two limits in the nominal's unit, its
        nominal value their midpoint (XCAF holds the limits alone), and no plus-minus tolerance."""
        entries, found = fixtures()
        entries[1]["dimension"]["tolerance"] = {"type": "limits", "lower": 10.0, "upper": 10.05}
        row = found["dimensions"][0]
        row.update(tolerance=None, nominal={"value": 10.025, "unit": "mm"},
                   limits=({"value": 10.0, "unit": "mm"}, {"value": 10.05, "unit": "mm"}))
        self.assertEqual(compare(entries, found), {"matched": 3, "total": 3, "problems": []})
        for change in ({"limits": ({"value": 10.0, "unit": "mm"}, {"value": 10.1, "unit": "mm"})},
                       {"limits": ({"value": 10.0, "unit": "m"}, {"value": 10.05, "unit": "m"})},
                       {"limits": None, "tolerance": {"lower": 0, "upper": 0.05, "unit": "mm"}},
                       {"nominal": {"value": 10.0, "unit": "mm"}}):
            changed = copy.deepcopy(found)
            changed["dimensions"][0].update(change)
            self.assertEqual(compare(entries, changed)["matched"], 2, change)
        entries[1]["dimension"]["tolerance"] = {"type": "plus_minus", "lower": 0, "upper": 0.05}
        self.assertEqual(compare(entries, {**found, "dimensions": [{**row, "tolerance": {
            "lower": 0, "upper": 0.05, "unit": "mm"}, "nominal": {"value": 10, "unit": "mm"}}]})["matched"], 2)

    def test_reader_reads_a_dimensions_limits_beside_its_nominal(self) -> None:
        reader = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=DIMENSIONAL_SIZE($,'diameter');
          #2=DIMENSIONAL_CHARACTERISTIC_REPRESENTATION(#1,#3);
          #3=SHAPE_DIMENSION_REPRESENTATION('',(#5,#4,#6),$);
          #4=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
              MEASURE_WITH_UNIT(POSITIVE_LENGTH_MEASURE(10.),#7) REPRESENTATION_ITEM('lower limit'));
          #5=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
              MEASURE_WITH_UNIT(POSITIVE_LENGTH_MEASURE(10.05),#7) REPRESENTATION_ITEM('upper limit'));
          #6=(LENGTH_MEASURE_WITH_UNIT() MEASURE_REPRESENTATION_ITEM()
              MEASURE_WITH_UNIT(POSITIVE_LENGTH_MEASURE(10.025),#7) REPRESENTATION_ITEM('nominal value'));
          #7=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
          ENDSEC; END-ISO-10303-21;"""))
        self.assertEqual((reader.nominal(1)["value"], reader.nominal(1)["role"]), (10.025, "nominal value"))
        self.assertEqual([(bound["value"], bound["unit"]) for bound in reader.limits(1)], [(10.0, "mm"), (10.05, "mm")])
        self.assertEqual(reader.problems, [])

    def test_a_profile_matches_on_its_faces_in_any_order_and_on_no_other(self) -> None:
        entries, found = fixtures()
        entries.append({"id": "sides", "kind": "geometric_tolerance", "status": "ok", "part": 0,
                        "refs": [{"ref": "part/f:front.1"}, {"ref": "part/f:left.1"}, {"ref": "part/f:bore.1"}],
                        "geometric_tolerance": {"characteristic": "surface_profile", "value": 0.5, "unit": "mm",
                                                "zone": None, "datums": ["A"], "general": False}})
        row = {"entity": "SURFACE_PROFILE_TOLERANCE", "magnitude": {"value": 0.5, "unit": "mm"}, "zone": None,
               "product": "part",
               "datums": ["A"], "features": [{"name": "f:bore.1"}, {"name": "f:front.1"}, {"name": "f:left.1"}]}
        self.assertEqual(compare(entries, {**found, "tolerances": found["tolerances"] + [row]}),
                         {"matched": 4, "total": 4, "problems": []})
        for change in ({"features": row["features"][:2]}, {"features": row["features"] + [{"name": "f:top.1"}]},
                       {"entity": "FLATNESS_TOLERANCE"}, {"datums": []}, {"zone": "cylindrical or circular"}):
            self.assertEqual(compare(entries, {**found, "tolerances": found["tolerances"] + [{**row, **change}]})["matched"],
                             3, change)

    def test_reader_reads_each_face_of_a_composite_shape_aspect(self) -> None:
        """A tolerance on several faces is on a COMPOSITE_SHAPE_ASPECT, each face's own aspect related
        to it, as OCCT's writer writes it: every face read, in order."""
        reader = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=SURFACE_PROFILE_TOLERANCE('','',#2,#3);
          #2=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.5),#4);
          #3=COMPOSITE_SHAPE_ASPECT('','',#9,.T.);
          #4=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
          #5=SHAPE_ASPECT('','',#9,.T.);
          #6=SHAPE_ASPECT_RELATIONSHIP('',$,#3,#5);
          #7=GEOMETRIC_ITEM_SPECIFIC_USAGE('','',#5,#9,#20);
          #8=SHAPE_ASPECT('','',#9,.T.);
          #10=SHAPE_ASPECT_RELATIONSHIP('',$,#3,#8);
          #11=GEOMETRIC_ITEM_SPECIFIC_USAGE('','',#8,#9,#21);
          #9=PRODUCT_DEFINITION_SHAPE('','',$);
          #20=ADVANCED_FACE('f:front.1',(),#22,.T.);
          #21=ADVANCED_FACE('f:left.1',(),#22,.T.);
          #22=CONICAL_SURFACE('',$,1.,0.5);
          ENDSEC; END-ISO-10303-21;"""))
        [tolerance] = reader.tolerances()
        self.assertEqual(tolerance["entity"], "SURFACE_PROFILE_TOLERANCE")
        self.assertEqual([feature["name"] for feature in tolerance["features"]], ["f:front.1", "f:left.1"])
        self.assertEqual(reader.problems, [])
        empty = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=SURFACE_PROFILE_TOLERANCE('','',#2,#3);
          #2=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.5),#4);
          #3=COMPOSITE_SHAPE_ASPECT('','',$,.T.);
          #4=(LENGTH_UNIT() NAMED_UNIT(*) SI_UNIT(.MILLI.,.METRE.));
          ENDSEC; END-ISO-10303-21;"""))
        self.assertEqual(empty.tolerances()[0]["features"], [])
        self.assertTrue(any("relates no shape aspect" in problem for problem in empty.problems), empty.problems)

    def test_reader_checks_unannotated_face_names_within_each_product(self) -> None:
        """A face name a product's geometry holds twice is ambiguous in that product, annotated or
        not; another product holding it once more makes no name of its ambiguous. An assembly's
        product, which holds no face, is no product a part is matched in."""
        with tempfile.TemporaryDirectory() as temp:
            step = Path(temp) / "duplicate.step"
            products = "".join(f"#{at}=PRODUCT('{name}','{name}','',());\n"
                               f"#{at + 1}=PRODUCT_DEFINITION_FORMATION('','',#{at});\n"
                               f"#{at + 2}=PRODUCT_DEFINITION('design','',#{at + 1},$);\n"
                               f"#{at + 3}=PRODUCT_DEFINITION_SHAPE('','',#{at + 2});\n"
                               f"#{at + 4}=SHAPE_DEFINITION_REPRESENTATION(#{at + 3},#{representation});\n"
                               for at, name, representation in ((20, "a", 10), (30, "b", 11), (40, "asm", 12)))
            step.write_text("ISO-10303-21; HEADER; FILE_SCHEMA(('AP242_TEST')); ENDSEC; DATA;\n"
                            "#1=ADVANCED_FACE('f:bore.1',(),$,.T.);\n"
                            "#2=ADVANCED_FACE('f:bore.1',(),$,.T.);\n"
                            "#3=ADVANCED_FACE('f:bore.1',(),$,.T.);\n"
                            "#10=ADVANCED_BREP_SHAPE_REPRESENTATION('',(#1,#2),$);\n"
                            "#11=ADVANCED_BREP_SHAPE_REPRESENTATION('',(#3),$);\n"
                            "#12=SHAPE_REPRESENTATION('',(),$);\n"
                            + products + "ENDSEC; END-ISO-10303-21;", encoding="utf-8")
            found = report(step)
            self.assertEqual(found["ambiguousFaceNames"], {"a": ["f:bore.1"], "b": []})
            self.assertEqual(found["products"], ["a", "b"])

    def test_reader_checks_both_deviation_units(self) -> None:
        reader = Report(parse("""ISO-10303-21; HEADER; ENDSEC; DATA;
          #1=PLUS_MINUS_TOLERANCE(#2,#3,$);
          #2=TOLERANCE_VALUE(#4,#5);
          #3=DIMENSIONAL_SIZE($,'diameter');
          #4=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(-0.2),#6);
          #5=LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.2),#7);
          #6=SI_UNIT($,.METRE.);
          #7=SI_UNIT(.MILLI.,.METRE.);
          ENDSEC; END-ISO-10303-21;"""))
        reader.plus_minus(3)
        self.assertTrue(any("unit" in problem.lower() for problem in reader.problems))


class BuiltPlateTest(unittest.TestCase):
    """The plate of ``test_pmi`` built once, its xbf and its AP242 STEP written by the engine into a
    temporary folder (Git holds no CAD file), read back by the reader of no OCCT."""

    xbf: Path
    step: Path

    @classmethod
    def setUpClass(cls) -> None:
        from cadgen.engine import build
        from tests.python.packages.cadgen.engine.test_pmi import plate

        folder = Path(tempfile.mkdtemp(prefix="engine-ap242-")).resolve()
        cls.addClassCleanup(shutil.rmtree, folder, ignore_errors=True)
        script = folder / "pmi_plate.py"
        script.write_text(textwrap.dedent(plate()), encoding="utf-8")
        report = build.build(script, ["pmi_plate"], cwd=folder, log=[].append)[0]
        assert report["ok"], report
        cls.xbf, cls.step = folder / "XBF" / "pmi_plate.xbf", folder / "pmi_plate.step"

    def test_reader_refuses_unchecked_exported_tolerance_extensions(self) -> None:
        records = parse(self.step.read_text(encoding="utf-8"))
        number = next(number for number, parts in records.items() if any(name == "POSITION_TOLERANCE" for name, _ in parts))
        for extension in ("GEOMETRIC_TOLERANCE_WITH_MODIFIERS", "GEOMETRIC_TOLERANCE_WITH_MAXIMUM_TOLERANCE"):
            altered = copy.deepcopy(records)
            altered[number].append((extension, (("MAXIMUM_MATERIAL_REQUIREMENT",),)))
            reader = Report(altered)
            reader.tolerances()
            self.assertTrue(any(extension in problem for problem in reader.problems), reader.problems)

    def test_the_plates_pmi_verifies_whole_basic_dimensions_included(self) -> None:
        """The plate's served PMI against its own exported STEP: every annotation, its two basic
        dimensions too (their 'theoretical' note), matched one to one."""
        from cadgen.engine.pmi import read

        entries = read(self.xbf)
        self.assertEqual(sum(1 for entry in entries if (entry.get("dimension") or {}).get("basic")), 2)
        result = check(entries, self.step, None, {0: "plate"})
        self.assertEqual((result["matched"], result["total"], result["problems"]), (9, 9, []))

    def test_a_file_whose_faces_are_named_right_on_the_wrong_geometry_fails(self) -> None:
        """The plate's STEP with its hole's cylinder widened, and again with its bottom plane moved:
        every face keeps its name, so a check of names alone passes; against the model's faces each
        annotation on the altered face fails, named."""
        from cadgen.engine import pmi
        from cadgen.engine.export import Source

        source = Source.read(self.xbf)
        entries = pmi.step_entries(source.structure["pmi"])
        surfaces = pmi.step_surfaces(source, entries)
        parts = {0: "plate"}
        self.assertEqual(check(entries, self.step, surfaces, parts)["problems"], [])
        text = self.step.read_text(encoding="utf-8")
        records = parse(text)
        [cylinder] = [number for number, parts in records.items() if parts[0][0] == "CYLINDRICAL_SURFACE"]
        [bottom] = [number for number, parts in records.items() if parts[0][0] == "PLANE"
                    and Report(records).surface(number)["origin"][2] == -5.0
                    and Report(records).surface(number)["normal"] == [0.0, 0.0, 1.0]]
        point = records[records[bottom][0][1][1].id][0][1][1].id  # the plane's placement's location
        widened = re.sub(rf"(#{cylinder}\s*=\s*CYLINDRICAL_SURFACE\('[^']*',#\d+,)5\.", r"\g<1>6.", text)
        moved = re.sub(rf"(#{point}\s*=\s*CARTESIAN_POINT\('[^']*',\([^,]+,[^,]+,)-5\.", r"\g<1>-4.", text)
        for altered, ids in ((widened, {"hole-diameter", "hole-position", "hole-from-B", "hole-from-C"}),
                             (moved, {"A", "thickness"})):
            self.assertNotEqual(altered, text)
            with tempfile.TemporaryDirectory() as temp:
                wrong = Path(temp) / "wrong.step"
                wrong.write_text(altered, encoding="utf-8")
                self.assertEqual(check(entries, wrong, None, parts)["problems"], [], "the names alone still match")
                result = check(entries, wrong, surfaces, parts)
            failed = {problem.split(":")[0] for problem in result["problems"] if "is not the model's face" in problem}
            self.assertTrue(failed and failed <= ids, result["problems"])
            self.assertLess(result["matched"], result["total"])


if __name__ == "__main__":
    unittest.main()
