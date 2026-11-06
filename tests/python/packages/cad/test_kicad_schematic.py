"""A KiCad schematic read, its nets resolved, its references answered, its plot payload and its still.

The schematics are the test projects (``tests/python/support/kicad_schematic.py``), written fresh: a
two-sheet divider and a bus across a sheet. No KiCad runs (the KiCad suite holds the nets to
``kicad-cli``'s netlist: ``tests/python/packages/kicad/test_schematic_files.py``), and nothing of the
corpus is read.
"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.python.support.engine_daemon import isolate
from tests.python.support.kicad_schematic import (
    BUS_NETS, NETS, ROOT_UUID, SHEET_UUID, UUIDS, at, write_bus_schematic, write_schematic,
)
from tests.python.support.paths import add_repo_path, repo_path

add_repo_path("packages/cad/src")

from cad.engine.formats.kicad.schematic import read_schematic  # noqa: E402


class SchematicFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.folder = tempfile.TemporaryDirectory(prefix="kicad-sch-")
        cls.addClassCleanup(cls.folder.cleanup)
        cls.root = write_schematic(Path(cls.folder.name) / "divider")
        cls.child = cls.root.with_name("load.kicad_sch")
        cls.busses = write_bus_schematic(Path(cls.folder.name) / "busses")
        cls.view = read_schematic(cls.child)


class TheHierarchy(SchematicFixture):
    def test_any_sheet_reads_the_project_from_its_root(self) -> None:
        self.assertEqual(self.view.root, self.root.resolve())
        self.assertEqual([(sheet.path, sheet.page, sheet.file.name) for sheet in self.view.sheets],
                         [("/", "1", "divider.kicad_sch"), ("/Load/", "2", "load.kicad_sch")])
        load = self.view.sheet("Load")
        self.assertEqual((load.parent, load.uuid_path, load.at), ("/", f"/{ROOT_UUID}/{SHEET_UUID}", at(100, 45)))
        self.assertEqual([(pin.name, pin.net) for pin in load.pins], [("IN", "/MID")])
        self.assertEqual(self.view.warnings, ())

    def test_symbols_are_placed_by_their_transform(self) -> None:
        [r1] = self.view.part("R1")
        self.assertEqual((r1.value, r1.lib_id, r1.mpn, r1.sheet, r1.uuid), ("10k", "Device:R", "RC0603FR-0710KL", "/", UUIDS["R1"]))
        self.assertEqual(r1.footprint, "Resistor_SMD:R_0603_1608Metric")
        self.assertEqual([(pin.number, pin.at) for pin in r1.pins], [("1", at(80, 44)), ("2", at(80, 50))])
        # Mirrored about the vertical (J1), and turned a quarter turn counter-clockwise (R3): pin 1 to the left.
        self.assertEqual([pin.at for pin in self.view.part("J1")[0].pins], [at(64, 50), at(64, 52)])
        self.assertEqual([pin.at for pin in self.view.part("R3")[0].pins], [at(46, 30), at(52, 30)])
        self.assertEqual(self.view.pin("J1", "2").name, "Pin_2")
        self.assertEqual(self.view.parts, ("C1", "J1", "R1", "R2", "R3"))
        self.assertTrue(all(symbol.power for symbol in self.view.symbols if symbol.ref.startswith("#PWR")))

    def test_a_symbol_saved_with_body_style_0_has_its_first_styles_pins(self) -> None:
        """KiCad's IPC API places a symbol that it saves with ``(body_style 0)``, and draws and connects it as
        style 1: so is it read."""
        with tempfile.TemporaryDirectory(prefix="kicad-sch-style-") as folder:
            root = write_schematic(Path(folder))
            text = root.read_text(encoding="utf-8")
            root.write_text(text.replace('(lib_id "Device:R") (at 101.6 59.69 0) (unit 1)',
                                         '(lib_id "Device:R") (at 101.6 59.69 0) (unit 1) (body_style 0)', 1),
                            encoding="utf-8")
            self.assertIn("(body_style 0)", root.read_text(encoding="utf-8"))
            [r1] = read_schematic(root).part("R1")
            self.assertEqual(["1", "2"], [pin.number for pin in r1.pins])


class TheNets(SchematicFixture):
    def test_nets_are_kicads_names_and_pins(self) -> None:
        found = {net.name: {f"{pin.ref}.{pin.number}" for pin in net.pins} for net in self.view.nets}
        self.assertEqual(found, {**NETS, "unconnected-(R3-Pad2)": {"R3.2"}})
        mid = self.view.net("/MID")
        self.assertEqual(mid.sheets, ("/", "/Load/"))
        self.assertEqual({(label.kind, label.text) for label in mid.labels}, {("local", "MID"), ("hierarchical", "IN")})
        self.assertEqual(self.view.item("junction", UUIDS["junction"]).net, "/MID")
        self.assertEqual(self.view.item("wire", UUIDS["mid wire"]).net, "/MID")

    def test_a_bus_joins_its_members_by_index_across_a_sheet(self) -> None:
        view = read_schematic(self.busses)
        found = {net.name: {f"{pin.ref}.{pin.number}" for pin in net.pins} for net in view.nets}
        for name, pins in BUS_NETS.items():
            with self.subTest(net=name):
                self.assertEqual(found.get(name), pins)
        self.assertEqual(len(found), len(BUS_NETS) + 4)  # and R1.2, R2.2, R3.2, R4.2 alone
        bus = [wire for wire in view.wires if wire.kind == "bus" and wire.sheet == "/"]
        self.assertEqual({wire.net for wire in bus}, {"/D[0..1]"})


class TheReferences(SchematicFixture):
    def test_a_reference_names_what_the_board_would(self) -> None:
        from cad.engine.formats.kicad.refs import parse_board_selector

        pin = self.view.resolve("#R1.2")
        self.assertEqual((pin.ref, pin.number, pin.net), ("R1", "2", "/MID"))
        self.assertEqual(pin.selector, "#R1.2")
        self.assertEqual(parse_board_selector(pin.selector).kind, "pad")  # the board's pad of the same name
        self.assertEqual([symbol.ref for symbol in self.view.resolve("#R1")], ["R1"])
        self.assertEqual(self.view.resolve("#net:GND").name, "GND")
        self.assertEqual(self.view.resolve("#net:MID").name, "/MID")  # a local net by its bare name
        self.assertEqual(self.view.resolve("#net:/MID").selector, "#net:/MID")

    def test_sheets_and_items(self) -> None:
        self.assertEqual(self.view.resolve("#sheet:/Load/").path, "/Load/")
        self.assertEqual(self.view.resolve("#sheet:Load").selector, "#sheet:/Load/")
        self.assertEqual(self.view.resolve("#sheet:/").path, "/")
        self.assertEqual(self.view.resolve(f"#label:{UUIDS['mid label']}").text, "MID")
        self.assertEqual(self.view.resolve(f"#no_connect:{UUIDS['no connect'].upper()}").sheet, "/Load/")
        self.assertEqual(self.view.resolve(f"#symbol:{UUIDS['R1']}").ref, "R1")
        answers = self.view.resolve_all("load.kicad_sch#C1.1,net:VOUT")
        self.assertEqual([answers[0].net, answers[1].name], ["/MID", "VOUT"])

    def test_what_names_nothing_is_refused_by_name(self) -> None:
        for ref, words in (("#R9", "no part R9"), ("#R1.7", "R1 has no pin 7"), ("#net:VBUS", "no net 'VBUS'"),
                           ("#sheet:/Power/", "no sheet /Power/"), ("#F.Cu@x1y2", "not a schematic reference"),
                           ("board.kicad_pcb#R1", "no sheet of divider.kicad_sch"),
                           (f"#wire:{UUIDS['R1']}", "no wire")):
            with self.subTest(ref=ref), self.assertRaisesRegex(ValueError, words):
                self.view.resolve(ref)

    def test_the_selector_text_is_canonical(self) -> None:
        from cad.engine.formats.kicad.schematic_refs import format_sheet_selector, parse_schematic_selector

        self.assertEqual(format_sheet_selector("Power/Stage"), "#sheet:/Power/Stage/")
        self.assertEqual(format_sheet_selector("/Power Stage/"), '#sheet:"/Power Stage/"')
        self.assertEqual(parse_schematic_selector('#sheet:"/Power Stage/"').sheet, "/Power Stage/")
        self.assertIsNone(parse_schematic_selector("#WIRE:abc"))
        self.assertEqual(parse_schematic_selector("#wire:ABC-12").canonical, "#wire:abc-12")


class ThePayload(SchematicFixture):
    def test_each_sheet_is_a_page_of_the_boards_primitives(self) -> None:
        from cad.engine.formats.kicad import PLOT_SCHEMA_VERSION
        from cad.engine.formats.kicad.schematic_plot import LAYERS, build_schematic_plot

        payload = json.loads(json.dumps(build_schematic_plot(self.root)))
        self.assertEqual((payload["schemaVersion"], payload["kind"]), (PLOT_SCHEMA_VERSION, "schematic"))
        self.assertEqual([(page["path"], page["number"], page["width"], page["height"]) for page in payload["sheets"]],
                         [("/", "1", 297.0, 210.0), ("/Load/", "2", 297.0, 210.0)])
        order = [layer_id for layer_id, _kind in LAYERS]
        root = payload["sheets"][0]
        ids = [layer["id"] for layer in root["layers"]]
        self.assertEqual(ids, sorted(ids, key=order.index))
        self.assertEqual(ids[0], "page")
        layers = {layer["id"]: layer for layer in root["layers"]}
        for layer in root["layers"]:
            self.assertEqual(layer["kind"], dict(LAYERS)[layer["id"]])
            for item in layer["items"]:
                self.assertIn(item["t"], ("path", "poly", "circle", "text"))
        self.assertTrue(layers["page"]["items"][0]["page"])
        self.assertEqual({item.get("net") for item in layers["wires"]["items"]}, {"+5V", "/MID", "GND", "VOUT"})
        mid = next(item for item in layers["wires"]["items"] if item.get("id") == UUIDS["mid wire"])
        self.assertEqual(mid["pts"], [list(at(80, 51)), list(at(100, 51))])
        self.assertIn("#R1", {item.get("ref") for item in layers["symbols"]["items"]})
        self.assertIn("#R1.1", {item.get("ref") for item in layers["pins"]["items"]})
        self.assertEqual({item["fill"] for item in layers["symbols"]["items"] if "fill" in item}, {"background"})  # J1's body
        self.assertEqual({item.get("label") for item in layers["labels"]["items"]}, {"local", "global"})
        fields = {item["text"]: item for item in layers["fields"]["items"]}
        self.assertEqual((fields["R1"]["field"], fields["10k"]["field"]), ("Reference", "Value"))
        self.assertNotIn("#PWR01", fields)  # a hidden field is not drawn
        self.assertEqual([part["ref"] for part in payload["schematic"]["parts"]], ["C1", "J1", "R1", "R2", "R3"])

    def test_a_sheet_block_draws_its_own_sheets_pins_in_any_order_in_the_file(self) -> None:
        """KiCad saves a sheet's blocks in uuid order, which need not be page order: each block draws its own
        sheet's pins, every one, under its own sheet's reference."""
        from cad.engine.formats.kicad.schematic import read_schematic_index
        from cad.engine.formats.kicad.schematic_plot import build_schematic_plot

        def block(uuid: str, name: str, y: float, page: str, pins: tuple[str, ...]) -> str:
            drawn = "".join(f'\n    (pin "{pin}" input (at 100 {y + 2.54 * (index + 1):g} 180) (uuid "{uuid[:-1]}{index + 1}")'
                            f' (effects (font (size 1.27 1.27)) (justify left)))' for index, pin in enumerate(pins))
            return f"""
  (sheet (at 100 {y:g}) (size 20 10) (exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)
    (stroke (width 0.1524) (type solid)) (fill (color 0 0 0 0.0000)) (uuid "{uuid}")
    (property "Sheetname" "{name}" (at 100 {y - 0.7:g} 0) (effects (font (size 1.27 1.27)) (justify left bottom)))
    (property "Sheetfile" "{name.lower()}.kicad_sch" (at 100 {y + 10.6:g} 0) (effects (font (size 1.27 1.27)) (justify left top))){drawn}
    (instances (project "pages" (path "/{ROOT_UUID}" (page "{page}")))))"""

        folder = Path(self.folder.name) / "pages"
        folder.mkdir()
        for name in ("Sensors", "Lights"):
            (folder / f"{name.lower()}.kicad_sch").write_text(
                '(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (paper "A4") (embedded_fonts no))\n',
                encoding="utf-8")
        root = folder / "pages.kicad_sch"
        # Lights (page 3) saved before Sensors (page 2), its uuid the lower.
        root.write_text(f"""(kicad_sch (version 20250114) (generator "eeschema") (generator_version "9.0") (uuid "{ROOT_UUID}") (paper "A4")
  (lib_symbols){block("00000000-0000-4000-8000-0000000000b0", "Lights", 80, "3", ("DIN",))}{block(
      "00000000-0000-4000-8000-0000000000c0", "Sensors", 40, "2", ("SDA", "SCL"))}
  (sheet_instances (path "/" (page "1")))
  (embedded_fonts no)
)
""", encoding="utf-8")
        index, _warnings = read_schematic_index(root)
        self.assertEqual([sheet.path for sheet in index.sheets], ["/", "/Sensors/", "/Lights/"])
        page = build_schematic_plot(root, sheets=["/"], index=False)["sheets"][0]
        (sheets,) = [layer["items"] for layer in page["layers"] if layer["id"] == "sheets"]
        drawn = {(item["ref"], item["text"]) for item in sheets if item.get("role") == "pin" and item["t"] == "text"}
        self.assertEqual(drawn, {("#sheet:/Sensors/", "SDA"), ("#sheet:/Sensors/", "SCL"), ("#sheet:/Lights/", "DIN")})

    def test_a_page_alone(self) -> None:
        from cad.engine.formats.kicad.schematic_plot import build_schematic_plot

        payload = build_schematic_plot(self.root, sheets=["Load"], index=False)
        self.assertEqual([page["path"] for page in payload["sheets"]], ["/Load/"])
        self.assertNotIn("schematic", payload)
        with self.assertRaisesRegex(ValueError, "no sheet /Power/; its sheets are /, /Load/"):
            build_schematic_plot(self.root, sheets=["/Power/"])

    def test_the_javascript_fixture_is_this_schematics_payload(self) -> None:
        from cad.engine.formats.kicad.schematic_plot import build_schematic_plot

        fixture = repo_path("packages", "ui", "src", "renderers", "schematic", "__fixtures__", "schematic.plot.json")
        self.assertEqual(json.loads(fixture.read_text(encoding="utf-8")), json.loads(json.dumps(build_schematic_plot(self.root))),
                         "regenerate the fixture: see its README")


class TheStill(SchematicFixture):
    """The still drawn in this process, its pixels read back through a plan camera: 10 px per mm."""

    SIZE = (400, 400)

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        isolate(cls.addClassCleanup)

    def draw(self, name: str, display: dict | None = None, center=(114.3, 64.77)):
        from PIL import Image

        from cad.engine.api import snapshot

        out = Path(self.folder.name) / f"{name}.png"
        camera = {"target": [center[0], -center[1], 0], "position": [center[0], -center[1], 50], "up": [0, 1, 0],
                  "orthographicHalfHeight": 20}
        snapshot(self.root, out, display=display, camera=camera, daemon=False, width=self.SIZE[0], height=self.SIZE[1])
        return Image.open(out).convert("RGB")

    @staticmethod
    def near(pixel, color, tolerance=90) -> bool:
        return sum(abs(a - b) for a, b in zip(pixel, color)) <= tolerance

    def test_wires_are_drawn_where_they_run(self) -> None:
        image = self.draw("root")
        # The MID wire, y = 64.77 mm, at x = 125 mm: 107 px right of the centre, on the centre row.
        self.assertTrue(any(self.near(image.getpixel((307, row)), (0, 150, 0)) for row in (199, 200, 201)))
        self.assertTrue(self.near(image.getpixel((307, 120)), (245, 244, 239), 10))  # the page, 8 mm above it
        dark = self.draw("dark", {"appearance": "dark"})
        self.assertTrue(self.near(dark.getpixel((307, 120)), (28, 28, 28), 10))

    def test_another_sheet_is_drawn_by_its_path(self) -> None:
        image = self.draw("load", {"sheet": "/Load/"}, center=at(43, 30))
        # R3's VOUT wire, y = 38.1 mm, from x = 50.8 to 58.42, the centre at x = 54.61: 2 mm right of it.
        self.assertTrue(any(self.near(image.getpixel((220, row)), (0, 150, 0)) for row in (199, 200, 201)))

    def test_what_a_schematic_does_not_draw_is_refused(self) -> None:
        from cad.engine.snapshot import SnapshotRefused

        for display, words in (({"sheet": "/Power/"}, "no sheet /Power/"), ({"mode": "copper"}, "takes appearance"),
                               ({"border": "yes"}, "border is true or false")):
            with self.subTest(display=display), self.assertRaisesRegex(SnapshotRefused, words):
                self.draw("refused", display)


class TheType(SchematicFixture):
    def test_the_type_reads_inspects_and_runs_kicad_where_kicode_is(self) -> None:
        import cad
        from cad._internal.document_type import DocumentType

        self.assertIsInstance(cad.kicad_sch, DocumentType)
        self.assertIs(cad.kicad_sch.read, read_schematic)
        found = cad.kicad_sch.inspect(self.child, "#net:MID")
        self.assertEqual((found["root"], found["counts"]["sheets"], found["counts"]["parts"]), ("divider.kicad_sch", 2, 5))
        self.assertEqual(found["resolved"]["pins"], ["C1.1", "R1.2", "R2.1"])
        # KiCad's own operations run kicad-cli, the kicad integration's: without one they say how to get it.
        import os
        from unittest import mock

        with mock.patch.dict(os.environ, {"CAD_KICAD_CLI": str(Path(self.folder.name) / "no-kicad-cli")}):
            checked = cad.kicad_sch.erc(self.root)
            self.assertEqual([finding.code for finding in checked.findings], ["kicad_missing"])
            self.assertIn("cad[kicad]", checked.findings[0].message)
            with self.assertRaisesRegex(RuntimeError, r"cad\[kicad\]"):
                cad.kicad_sch.export(self.root, "netlist", Path(self.folder.name) / "out")
        with self.assertRaisesRegex(ValueError, "is a kicad_pcb, not a kicad_sch"):
            cad.kicad_sch.snapshot("board.kicad_pcb", "out.png")

    def test_erc_counts_the_warnings_it_lists(self) -> None:
        # KiCad, in homes of its own, cannot see the person's global libraries: those checks are one note,
        # and the summary counts the one warning it lists, not the 220 library checks of the demos.
        from unittest import mock

        import cad
        from cad.kicad import _schematic

        unseen = [_schematic.ErcFinding("warning", "lib_symbol_issues", f"The current configuration does not include "
                                        f"the symbol library 'Device{index}'", "/", (), None) for index in range(220)]
        real = _schematic.ErcFinding("warning", "label_dangling", "Label not connected", "/", ("MID",), (90.0, 51.0))
        with mock.patch.object(_schematic, "ready", lambda: Path("kicad-cli")), \
                mock.patch.object(_schematic, "run_erc", lambda cli, target: [*unseen, real]):
            checked = cad.kicad_sch.erc(self.root)
        self.assertEqual([(finding.severity, finding.code) for finding in checked.findings],
                         [("warning", "label_dangling"), ("info", "libraries_not_checked")])
        self.assertTrue(checked.summary.endswith("ERC clean (1 warning(s))"), checked.summary)

    def test_a_file_that_is_no_schematic_is_refused(self) -> None:
        folder = Path(self.folder.name)
        (folder / "board.kicad_sch").write_text("(kicad_pcb (version 1))", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "board.kicad_sch is not a KiCad schematic"):
            read_schematic(folder / "board.kicad_sch")
        with self.assertRaisesRegex(ValueError, r"\.kicad_sch"):
            read_schematic(folder / "board.kicad_pcb")


if __name__ == "__main__":
    unittest.main()
