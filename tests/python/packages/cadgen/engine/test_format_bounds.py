"""A file the stills or an export read is read in work bounded by the file, or refused by name.
A DXF block is drawn once for every insert of it and every cell of a MINSERT's grid, and a glTF
node or a 3MF object is placed once for every parent that lists it, so a few hundred bytes can
name an exponential drawing or build; each reader counts what it expands and refuses a file past
its bound before it holds what it would draw. The mesh readers share the bounds of a document's
assembly (``document.MAX_OCCURRENCES``, ``document.MAX_ASSEMBLY_DEPTH``). A 3MF is a zip, so what
a read unpacks from it is bounded too: its entries, its parts' bytes in all, and how far a large
part unpacks past the bytes it is stored in. A STEP is read as the file it is: one that names
another file for the reader to open is refused."""

from __future__ import annotations

import json
import shutil
import struct
import sys
import zipfile
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SRC = Path(__file__).resolve().parents[5] / "packages" / "cadgen" / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cadgen.engine import document  # noqa: E402
from cadgen.engine.formats import FormatError, dxf, glb, gltf, threemf  # noqa: E402


class FolderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.folder = Path(tempfile.mkdtemp(prefix="format-bounds-")).resolve()
        self.addCleanup(shutil.rmtree, self.folder, True)


def nested_blocks(path: Path, fanout: int, levels: int) -> Path:
    """A DXF of one line in block B0 and ``levels`` blocks, each inserting the one below
    ``fanout`` times; modelspace inserts the top one (``fanout**levels`` lines)."""
    import ezdxf

    document = ezdxf.new()
    document.blocks.new("B0").add_line((0, 0), (1, 0))
    for level in range(1, levels + 1):
        block = document.blocks.new(f"B{level}")
        for at in range(fanout):
            block.add_blockref(f"B{level - 1}", (2 * at, 0))
    document.modelspace().add_blockref(f"B{levels}", (0, 0))
    document.saveas(path)
    return path


def grid(path: Path, columns: int, rows: int) -> Path:
    """A DXF of one MINSERT of a one-line block in a ``columns`` x ``rows`` grid."""
    import ezdxf

    document = ezdxf.new()
    document.blocks.new("B0").add_line((0, 0), (1, 0))
    insert = document.modelspace().add_blockref("B0", (0, 0))
    insert.dxf.column_count, insert.dxf.row_count = columns, rows
    insert.dxf.column_spacing, insert.dxf.row_spacing = 2.0, 2.0
    document.saveas(path)
    return path


class DxfExpansionTest(FolderTest):
    def test_shared_blocks_within_the_bound_draw_every_placement(self) -> None:
        drawing = dxf.read_dxf(nested_blocks(self.folder / "small.dxf", 2, 3))
        self.assertEqual(len(drawing.lines), 8)
        drawing = dxf.read_dxf(grid(self.folder / "grid.dxf", 3, 4))
        self.assertEqual(len(drawing.lines), 12)

    def test_nested_inserts_past_the_bound_are_refused(self) -> None:
        path = nested_blocks(self.folder / "fanout.dxf", 10, 4)  # 10,000 lines
        with mock.patch.object(dxf, "MAX_EXPANDED", 1000):
            with self.assertRaisesRegex(dxf.DxfError, "draw more than 1,000 entities"):
                dxf.read_dxf(path)

    def test_a_minsert_grid_past_the_bound_is_refused_before_its_cells_are_placed(self) -> None:
        path = grid(self.folder / "grid.dxf", 30_000, 30_000)  # 9e8 cells
        with mock.patch.object(dxf.np, "eye", wraps=dxf.np.eye) as eye:
            with self.assertRaisesRegex(dxf.DxfError, "draw more than"):
                dxf.read_dxf(path)
        self.assertLess(eye.call_count, 10)

    def test_a_minsert_grid_of_a_count_that_is_no_number_is_refused(self) -> None:
        path = grid(self.folder / "grid.dxf", 2, 2)
        text = path.read_text(encoding="utf-8")
        # Group code 70 (the column count) of the one MINSERT, written as an overflowing float.
        head, insert, tail = text.partition("\nINSERT\n")
        cut = tail.index("\n 70\n2\n")
        path.write_text(head + insert + tail[:cut] + "\n 70\n1e400\n" + tail[cut + len("\n 70\n2\n"):], encoding="utf-8")
        with self.assertRaisesRegex(dxf.DxfError, "draw more than"):
            dxf.read_dxf(path)


def shared_nodes(path: Path, fanout: int, levels: int) -> Path:
    """A GLB of one triangle under ``levels`` nodes, each listing the one below ``fanout`` times
    (``fanout**levels`` placements)."""
    points = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    nodes = [{"children": [at + 1] * fanout} for at in range(levels)] + [{"mesh": 0, "name": "leaf"}]
    found = {"asset": {"version": "2.0"}, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": nodes,
             "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
             "accessors": [{"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3",
                            "min": [0, 0, 0], "max": [1, 1, 0]}],
             "bufferViews": [{"buffer": 0, "byteLength": len(points)}], "buffers": [{"byteLength": len(points)}]}
    text = json.dumps(found).encode()
    text += b" " * (-len(text) % 4)
    body = struct.pack("<II", len(text), 0x4E4F534A) + text + struct.pack("<II", len(points), 0x004E4942) + points
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 12 + len(body)) + body)
    return path


def shared_objects(path: Path, fanout: int, levels: int) -> Path:
    """A 3MF of one triangle object under ``levels`` component objects, each listing the one below
    ``fanout`` times (``fanout**levels`` placements)."""
    objects = ['<object id="%d" type="model"><mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>'
               '<vertex x="0" y="1" z="0"/></vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh>'
               '</object>' % (levels + 1)]
    for at in range(levels, 0, -1):
        objects.append('<object id="%d" type="model"><components>%s</components></object>'
                       % (at, ('<component objectid="%d"/>' % (at + 1)) * fanout))
    model = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>%s</resources>'
             '<build><item objectid="1"/></build></model>' % "".join(objects))
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("3D/3dmodel.model", model)
    return path


class MeshPlacementTest(FolderTest):
    """The export's GLB reader (``gltf``), the stills' (``glb``, over OCCT's document) and the 3MF
    reader each place a shared node once per parent, within the assembly bounds."""

    def readers(self, fanout: int, levels: int):
        glb_path = shared_nodes(self.folder / f"n{fanout}x{levels}.glb", fanout, levels)
        threemf_path = shared_objects(self.folder / f"o{fanout}x{levels}.3mf", fanout, levels)
        return (("gltf", lambda: len(gltf.read_gltf(glb_path).placed), gltf.GltfError),
                ("glb", lambda: len(glb.read_glb(glb_path)[1]), FormatError),
                ("3mf", lambda: len(threemf.read_3mf(threemf_path).placed), threemf.ThreeMfError))

    def test_shared_nodes_within_the_bound_place_every_occurrence(self) -> None:
        for name, read, _error in self.readers(2, 3):
            with self.subTest(name):
                self.assertEqual(read(), 8)

    def test_shared_nodes_past_the_occurrence_bound_are_refused(self) -> None:
        for name, read, error in self.readers(10, 4):  # 10,000 placements
            with self.subTest(name), mock.patch.object(document, "MAX_OCCURRENCES", 1000):
                with self.assertRaisesRegex(error, "more than 1000 occurrences"):
                    read()

    def test_a_tree_past_the_depth_bound_is_refused(self) -> None:
        for name, read, error in self.readers(1, 8):
            with self.subTest(name), mock.patch.object(document, "MAX_ASSEMBLY_DEPTH", 4):
                with self.assertRaisesRegex(error, "deeper than 4 levels"):
                    read()


MODEL = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" '
         'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources><object id="1" type="model">'
         '<mesh><vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/><vertex x="0" y="1" z="0"/>'
         '</vertices><triangles><triangle v1="0" v2="1" v3="2"/></triangles></mesh></object></resources>'
         '<build><item objectid="1"/></build></model>')


def package(path: Path, padding: int = 0, extra: int = 0) -> Path:
    """A one-triangle 3MF whose model part ends in ``padding`` spaces, with ``extra`` more entries."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as found:
        found.writestr("3D/3dmodel.model", MODEL + " " * padding)
        for at in range(extra):
            found.writestr(f"Metadata/note{at}.txt", "")
    return path


class ThreeMfUnpackTest(FolderTest):
    def test_a_package_within_the_bounds_reads(self) -> None:
        model = threemf.read_3mf(package(self.folder / "plain.3mf", padding=4096, extra=3))
        self.assertEqual(len(model.placed), 1)

    def test_a_part_past_the_unpacked_bound_is_refused(self) -> None:
        path = package(self.folder / "padded.3mf", padding=200_000)
        with mock.patch.object(threemf, "MAX_UNPACKED", 100_000):
            with self.assertRaisesRegex(threemf.ThreeMfError, "unpacks to more than"):
                threemf.read_3mf(path)

    def test_a_large_part_packed_far_past_the_ratio_is_refused(self) -> None:
        path = package(self.folder / "dense.3mf", padding=400_000)  # spaces pack about a thousand to one
        with mock.patch.object(threemf, "RATIO_FROM", 100_000):
            with self.assertRaisesRegex(threemf.ThreeMfError, "unpacks to more than"):
                threemf.read_3mf(path)
        self.assertEqual(len(threemf.read_3mf(path).placed), 1)  # under the default threshold it reads

    def test_a_package_of_too_many_entries_is_refused(self) -> None:
        path = package(self.folder / "many.3mf", extra=20)
        with mock.patch.object(threemf, "MAX_ENTRIES", 10):
            with self.assertRaisesRegex(threemf.ThreeMfError, "more than 10 entries"):
                threemf.read_3mf(path)



def external_step(folder: Path) -> Path:
    """A STEP assembly whose one part is another file it names (an external document reference, by
    absolute path), as OCCT's writer makes one in its multi-file mode; the part's file beside it."""
    from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox
    from OCP.IFSelect import IFSelect_RetDone
    from OCP.STEPCAFControl import STEPCAFControl_Writer
    from OCP.STEPControl import STEPControl_AsIs
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDocStd import TDocStd_Document
    from OCP.TopLoc import TopLoc_Location
    from OCP.XCAFDoc import XCAFDoc_DocumentTool

    doc = TDocStd_Document(TCollection_ExtendedString("XCAF"))
    shapes = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    assembly = shapes.NewShape()
    TDataStd_Name.Set_s(assembly, TCollection_ExtendedString("assembly"))
    part = shapes.AddShape(BRepPrimAPI_MakeBox(7, 11, 13).Shape(), False)
    TDataStd_Name.Set_s(part, TCollection_ExtendedString("part"))
    shapes.AddComponent(assembly, part, TopLoc_Location())
    shapes.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    assert writer.Transfer(doc, STEPControl_AsIs, str(folder / "named"))
    assert writer.Write(str(folder / "main.step")) == IFSelect_RetDone
    return folder / "main.step"


class StepReferenceTest(FolderTest):
    def test_a_step_that_names_another_file_is_refused_by_both_readers(self) -> None:
        from cadgen.engine import reader

        path = external_step(self.folder)
        [named] = [entry for entry in self.folder.iterdir() if entry.name.startswith("named")]
        self.assertNotIn(b"MANIFOLD_SOLID_BREP", path.read_bytes(), "the STEP holds no geometry of its own")
        with self.assertRaisesRegex(ValueError, "names another file"):
            document.load(path)  # the viewer's, an export's and a snapshot's read
        with self.assertRaisesRegex(ValueError, "names another file"):
            reader._parse(str(path))  # read_step's, in its reader process
        [prototype] = document.load(named).prototypes  # the part's own file reads as itself
        self.assertEqual(prototype.shape.ShapeType().name, "TopAbs_SOLID")

    def test_the_check_counts_entities_in_the_kernel_not_one_by_one(self) -> None:
        # Fetching a STEP's entities into Python one at a time cost about 0.25 ms each: 235 s of
        # tom's cold build went to one million-entity file. The check never takes one entity.
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.STEPCAFControl import STEPCAFControl_Reader

        path = external_step(self.folder)
        [named] = [entry for entry in self.folder.iterdir() if entry.name.startswith("named")]
        for step, refused in ((path, True), (named, False)):
            reader = STEPCAFControl_Reader()
            self.assertEqual(reader.ReadFile(str(step)), IFSelect_RetDone)
            model = reader.ChangeReader().Model()
            fetched = mock.Mock(side_effect=AssertionError("an entity fetched into Python"))
            # The reader as the check sees it: its model's every entity reachable one by one too.
            seen = mock.Mock(Entities=model.Entities, NbEntities=model.NbEntities, Value=fetched)
            stand_in = mock.Mock(ChangeReader=lambda: mock.Mock(Model=lambda: seen))
            if refused:
                with self.assertRaisesRegex(ValueError, "names another file"):
                    document.refuse_external_files(stand_in, step)
            else:
                document.refuse_external_files(stand_in, step)
            fetched.assert_not_called()


if __name__ == "__main__":
    unittest.main()
