"""A STEP's general notes as AP242 writes them (``cad.engine.step_notes``): read as the file is read,
listed as the part's general notes, and the part's material named as the file declares it."""
from __future__ import annotations

import re
import tempfile
import unittest
from pathlib import Path

# The properties Specify writes on a part, as its writer spells them; ``{pd}`` is the part's
# PRODUCT_DEFINITION_SHAPE, ``{ctx}`` its representation context. A user-defined attribute of its
# own on the part (``history``) is what OCCT's reader took for the part's material.
NOTES = """#9001=DESCRIPTIVE_REPRESENTATION_ITEM('tolerance class','ISO 2768-m');
#9002=PROPERTY_DEFINITION('default tolerances','',{pd});
#9003=REPRESENTATION('default tolerances',(#9001),{ctx});
#9004=PROPERTY_DEFINITION_REPRESENTATION(#9002,#9003);
#9005=DESCRIPTIVE_REPRESENTATION_ITEM('Aluminium 6082-T6','Aluminium 6082-T6');
#9006=PROPERTY_DEFINITION('material property','material name',{pd});
#9007=REPRESENTATION('material identification (no separate name)',(#9005),{ctx});
#9008=PROPERTY_DEFINITION_REPRESENTATION(#9006,#9007);
#9009=DESCRIPTIVE_REPRESENTATION_ITEM('edge condition','Break sharp edges 0.2 max');
#9010=PROPERTY_DEFINITION('semantic text','user defined attribute',{pd});
#9011=REPRESENTATION('',(#9009),{ctx});
#9012=PROPERTY_DEFINITION_REPRESENTATION(#9010,#9011);
#9013=DESCRIPTIVE_REPRESENTATION_ITEM('measuring method','Ra');
#9014=(LENGTH_UNIT()NAMED_UNIT(*)SI_UNIT(.MICRO.,.METRE.));
#9015=(LENGTH_MEASURE_WITH_UNIT()MEASURE_REPRESENTATION_ITEM()MEASURE_WITH_UNIT(LENGTH_MEASURE(3.2),#9014)REPRESENTATION_ITEM('characteristic value'));
#9016=PROPERTY_DEFINITION('surface_condition','',{pd});
#9017=SURFACE_TEXTURE_REPRESENTATION('surface texture parameter',(#9013,#9015),{ctx});
#9018=PROPERTY_DEFINITION_REPRESENTATION(#9016,#9017);
#9019=DESCRIPTIVE_REPRESENTATION_ITEM('history','{{"schema":2}}');
#9020=PROPERTY_DEFINITION('specify characteristic numbers','user defined attribute',{definition});
#9021=REPRESENTATION('',(#9019),{ctx});
#9022=PROPERTY_DEFINITION_REPRESENTATION(#9020,#9021);
"""


def _box_step(folder: Path, notes: bool) -> Path:
    import build123d as bd

    path = folder / ("noted.step" if notes else "plain.step")
    bd.export_step(bd.Box(10, 20, 5), str(path))
    if notes:
        text = path.read_text()
        pd = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION_SHAPE\(", text).group(1)
        definition = re.search(r"#(\d+)\s*=\s*PRODUCT_DEFINITION\(", text).group(1)
        ctx = re.search(r"ADVANCED_BREP_SHAPE_REPRESENTATION\([^;]*?,\s*#(\d+)\s*\)\s*;", text, re.S).group(1)
        block = NOTES.format(pd=f"#{pd}", definition=f"#{definition}", ctx=f"#{ctx}")
        path.write_text(text.replace("ENDSEC;\nEND-ISO", block + "ENDSEC;\nEND-ISO", 1))
    return path


class StepNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="step-notes-"))
        self.addCleanup(lambda: __import__("shutil").rmtree(self.folder, ignore_errors=True))

    def test_a_steps_general_notes_are_its_parts_notes_and_its_material_is_the_one_it_declares(self) -> None:
        from cad.engine.document import Loaded

        loaded = Loaded(_box_step(self.folder, notes=True))
        structure = loaded.structure()
        notes = [entry for entry in structure["pmi"] if entry["kind"] == "note"]
        self.assertEqual([(note["note"]["number"], note["note"]["text"], note["note"]["general"], note["part"])
                          for note in notes],
                         [(1, "Material: Aluminium 6082-T6", True, 0), (2, "General tolerance: ISO 2768-m", True, 0),
                          (3, "Surface finish: Ra 3.2", True, 0), (4, "Edges: Break sharp edges 0.2 max", True, 0)])
        self.assertEqual(structure["prototypes"][0]["material"]["material"]["name"], "Aluminium 6082-T6")

    def test_a_step_without_them_has_no_pmi_of_them(self) -> None:
        from cad.engine.document import Loaded

        self.assertNotIn("pmi", Loaded(_box_step(self.folder, notes=False)).structure())


if __name__ == "__main__":
    unittest.main()
