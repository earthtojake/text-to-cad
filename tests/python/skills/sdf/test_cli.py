import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("skills/sdf/scripts")

from sdf import cli
from sdf.source import SdfSourceError


def _write_sdf_source(path: Path, body: str) -> None:
    path.write_text(
        "\n".join(
            [
                "def gen_sdf():",
                *[f"    {line}" for line in body.splitlines()],
                "",
            ]
        ),
        encoding="utf-8",
    )


def _strip_cadpy_metadata_comments(text: str) -> str:
    return "\n".join(
        line for line in text.splitlines() if not line.startswith("<!-- cadpy:")
    ) + "\n"


class SdfCliTests(unittest.TestCase):
    def test_requires_explicit_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main([])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_summary_option(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["sample_robot.py", "--summary"])
        self.assertEqual(2, cm.exception.code)

    def test_passes_targets_and_output(self) -> None:
        with mock.patch.object(cli, "generate_sdf_targets", return_value=0) as generate:
            self.assertEqual(0, cli.main(["sample_robot.py", "-o", "sample_robot.sdf"]))

        generate.assert_called_once_with(["sample_robot.py"], output="sample_robot.sdf", gz_check="auto", strict=False)

    def test_passes_gz_check_and_strict_options(self) -> None:
        with mock.patch.object(cli, "generate_sdf_targets", return_value=0) as generate:
            self.assertEqual(0, cli.main(["sample_robot.py", "--gz-check", "required", "--strict"]))

        generate.assert_called_once_with(["sample_robot.py"], output=None, gz_check="required", strict=True)

    def test_rejects_output_with_pair_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["sample_robot.py=sample_robot.sdf", "-o", "other.sdf"])
        self.assertEqual(2, cm.exception.code)

    def test_generates_default_sibling_output_from_xml_string(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(
                source_path,
                "return '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>'",
            )

            self.assertEqual(0, cli.generate_sdf_targets([str(source_path)]))

            output_text = source_path.with_suffix(".sdf").read_text(encoding="utf-8")
            self.assertIn("<!-- cadpy:sourcePath=", output_text)
            self.assertEqual(
                '<sdf version="1.12"><model name="sample"><link name="base_link" /></model></sdf>\n',
                _strip_cadpy_metadata_comments(output_text),
            )

    def test_validates_generated_sdf_before_writing_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            output_path = source_path.with_suffix(".sdf")
            output_path.write_text("original output\n", encoding="utf-8")
            _write_sdf_source(
                source_path,
                "return '<robot name=\"not_sdf\" />'",
            )

            with self.assertRaisesRegex(SdfSourceError, "root element must be <sdf>"):
                cli.generate_sdf_targets([str(source_path)])

            self.assertEqual("original output\n", output_path.read_text(encoding="utf-8"))

    def test_generates_default_sibling_output_from_element_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            source_path.write_text(
                "\n".join(
                    [
                        "import xml.etree.ElementTree as ET",
                        "",
                        "def gen_sdf():",
                        "    sdf = ET.Element('sdf', {'version': '1.12'})",
                        "    model = ET.SubElement(sdf, 'model', {'name': 'sample'})",
                        "    ET.SubElement(model, 'link', {'name': 'base_link'})",
                        "    return sdf",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(0, cli.generate_sdf_targets([str(source_path)]))

            output_text = source_path.with_suffix(".sdf").read_text(encoding="utf-8")
            self.assertIn("<!-- cadpy:sourcePath=", output_text)
            self.assertEqual(
                '<?xml version="1.0"?>\n'
                '<sdf version="1.12">\n'
                '  <model name="sample">\n'
                '    <link name="base_link" />\n'
                '  </model>\n'
                '</sdf>\n',
                _strip_cadpy_metadata_comments(output_text),
            )

    def test_generates_envelope_output_from_element_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            source_path.write_text(
                "\n".join(
                    [
                        "import xml.etree.ElementTree as ET",
                        "",
                        "def gen_sdf():",
                        "    sdf = ET.Element('sdf', {'version': '1.12'})",
                        "    model = ET.SubElement(sdf, 'model', {'name': 'sample'})",
                        "    ET.SubElement(model, 'link', {'name': 'base_link'})",
                        "    return {'xml': sdf}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(0, cli.generate_sdf_targets([str(source_path)]))

            self.assertIn(
                '<link name="base_link" />',
                source_path.with_suffix(".sdf").read_text(encoding="utf-8"),
            )

    def test_generates_output_override_for_single_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            output_path = Path(tempdir) / "custom" / "robot.sdf"
            _write_sdf_source(
                source_path,
                "return '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>'",
            )

            self.assertEqual(0, cli.generate_sdf_targets([str(source_path)], output=str(output_path)))

            self.assertTrue(output_path.exists())
            self.assertFalse(source_path.with_suffix(".sdf").exists())

    def test_generates_mixed_plain_and_paired_targets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            root = Path(tempdir)
            first_path = root / "first.py"
            second_path = root / "second.py"
            second_output = root / "custom" / "second.sdf"
            _write_sdf_source(first_path, "return '<sdf version=\"1.12\"><model name=\"first\"><link name=\"base\" /></model></sdf>'")
            _write_sdf_source(second_path, "return '<sdf version=\"1.12\"><model name=\"second\"><link name=\"base\" /></model></sdf>'")

            self.assertEqual(0, cli.generate_sdf_targets([str(first_path), f"{second_path}={second_output}"]))

            self.assertTrue(first_path.with_suffix(".sdf").exists())
            self.assertTrue(second_output.exists())
            self.assertFalse(second_path.with_suffix(".sdf").exists())

    def test_rejects_legacy_sdf_output_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>',",
                        "    'sdf_output': 'legacy/ignored.sdf',",
                        "}",
                    ]
                ),
            )

            with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): sdf_output"):
                cli.generate_sdf_targets([str(source_path)])

            self.assertFalse(source_path.with_suffix(".sdf").exists())
            self.assertFalse((Path(tempdir) / "legacy" / "ignored.sdf").exists())

    def test_envelope_prints_assumptions_and_warnings(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>',",
                        "    'metadata': {'target_consumer': 'CAD Viewer'},",
                        "    'assumptions': [{'code': 'mesh_units', 'message': 'Assumed mesh units are meters'}],",
                        "    'warnings': ['Plugin startup was not smoke-tested'],",
                        "}",
                    ]
                ),
            )

            with mock.patch("builtins.print") as print_mock:
                self.assertEqual(0, cli.generate_sdf_targets([str(source_path)], gz_check="never"))

            printed = "\n".join(" ".join(str(arg) for arg in call.args) for call in print_mock.call_args_list)
            self.assertIn("Assumption [mesh_units]", printed)
            self.assertIn("generator_warning", printed)

    def test_rejects_unknown_envelope_fields(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>',",
                        "    'unexpected': True,",
                        "}",
                    ]
                ),
            )

            with self.assertRaisesRegex(TypeError, "unsupported field"):
                cli.generate_sdf_targets([str(source_path)], gz_check="never")

    def test_strict_rejects_generator_warnings_before_writing(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>',",
                        "    'warnings': ['Unverified plugin'],",
                        "}",
                    ]
                ),
            )

            with self.assertRaisesRegex(SdfSourceError, "generator_warning"):
                cli.generate_sdf_targets([str(source_path)], gz_check="never", strict=True)
            self.assertFalse(source_path.with_suffix(".sdf").exists())

    def test_gz_check_required_failure_prevents_write(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(
                source_path,
                "return '<sdf version=\"1.12\"><model name=\"sample\"><link name=\"base_link\" /></model></sdf>'",
            )

            with mock.patch("sdf.external.shutil.which", return_value=None):
                with self.assertRaisesRegex(SdfSourceError, "gz_check_unavailable"):
                    cli.generate_sdf_targets([str(source_path)], gz_check="required")
            self.assertFalse(source_path.with_suffix(".sdf").exists())

    def test_rejects_invalid_output_suffix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_sdf_source(source_path, "return '<sdf version=\"1.12\"><model name=\"sample\" /></sdf>'")

            with self.assertRaisesRegex(ValueError, "must end in .sdf"):
                cli.generate_sdf_targets([f"{source_path}={Path(tempdir) / 'sample.xml'}"])

    def test_rejects_duplicate_output_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-sdf-") as tempdir:
            first_path = Path(tempdir) / "first.py"
            second_path = Path(tempdir) / "second.py"
            output_path = Path(tempdir) / "same.sdf"
            _write_sdf_source(first_path, "return '<sdf version=\"1.12\"><model name=\"first\"><link name=\"base\" /></model></sdf>'")
            _write_sdf_source(second_path, "return '<sdf version=\"1.12\"><model name=\"second\"><link name=\"base\" /></model></sdf>'")

            with self.assertRaisesRegex(ValueError, "used more than once"):
                cli.generate_sdf_targets([f"{first_path}={output_path}", f"{second_path}={output_path}"])


if __name__ == "__main__":
    unittest.main()
