import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("skills/urdf/scripts")

from urdf import cli
from urdf.source import UrdfSourceError


def _write_urdf_source(path: Path, body: str) -> None:
    path.write_text(
        "\n".join(
            [
                "def gen_urdf():",
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


class UrdfCliTests(unittest.TestCase):
    def test_requires_explicit_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main([])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_summary_option(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["sample_robot.py", "--summary"])
        self.assertEqual(2, cm.exception.code)

    def test_rejects_validate_options(self) -> None:
        for option in ("--validate", "--no-validate"):
            with self.subTest(option=option):
                with self.assertRaises(SystemExit) as cm:
                    cli.main(["sample_robot.py", option])
                self.assertEqual(2, cm.exception.code)

    def test_passes_targets_and_output(self) -> None:
        with mock.patch.object(cli, "generate_urdf_targets", return_value=0) as generate:
            self.assertEqual(0, cli.main(["sample_robot.py", "-o", "sample_robot.urdf"]))

        generate.assert_called_once_with(["sample_robot.py"], output="sample_robot.urdf")

    def test_rejects_output_with_pair_target(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            cli.main(["sample_robot.py=sample_robot.urdf", "-o", "other.urdf"])
        self.assertEqual(2, cm.exception.code)

    def test_generates_default_sibling_output_from_xml_string(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_urdf_source(
                source_path,
                "return '<robot name=\"sample\"><link name=\"base_link\" /></robot>'",
            )

            self.assertEqual(0, cli.generate_urdf_targets([str(source_path)]))

            output_text = source_path.with_suffix(".urdf").read_text(encoding="utf-8")
            self.assertIn("<!-- cadpy:sourcePath=", output_text)
            self.assertEqual(
                '<robot name="sample"><link name="base_link" /></robot>\n',
                _strip_cadpy_metadata_comments(output_text),
            )

    def test_generates_default_sibling_output_from_element_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            source_path.write_text(
                "\n".join(
                    [
                        "import xml.etree.ElementTree as ET",
                        "",
                        "def gen_urdf():",
                        "    robot = ET.Element('robot', {'name': 'sample'})",
                        "    ET.SubElement(robot, 'link', {'name': 'base_link'})",
                        "    return robot",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(0, cli.generate_urdf_targets([str(source_path)]))

            output_text = source_path.with_suffix(".urdf").read_text(encoding="utf-8")
            self.assertIn("<!-- cadpy:sourcePath=", output_text)
            self.assertEqual(
                '<?xml version="1.0"?>\n<robot name="sample">\n  <link name="base_link" />\n</robot>\n',
                _strip_cadpy_metadata_comments(output_text),
            )

    def test_generates_envelope_output_from_element_root(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            source_path.write_text(
                "\n".join(
                    [
                        "import xml.etree.ElementTree as ET",
                        "",
                        "def gen_urdf():",
                        "    robot = ET.Element('robot', {'name': 'sample'})",
                        "    ET.SubElement(robot, 'link', {'name': 'base_link'})",
                        "    return {'xml': robot}",
                        "",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual(0, cli.generate_urdf_targets([str(source_path)]))

            self.assertIn(
                '<link name="base_link" />',
                source_path.with_suffix(".urdf").read_text(encoding="utf-8"),
            )

    def test_generates_output_override_for_single_target(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            output_path = Path(tempdir) / "custom" / "robot.urdf"
            _write_urdf_source(
                source_path,
                "return '<robot name=\"sample\"><link name=\"base_link\" /></robot>'",
            )

            self.assertEqual(0, cli.generate_urdf_targets([str(source_path)], output=str(output_path)))

            self.assertTrue(output_path.exists())
            self.assertFalse(source_path.with_suffix(".urdf").exists())

    def test_validates_generated_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            output_path = Path(tempdir) / "custom" / "robot.urdf"
            _write_urdf_source(
                source_path,
                "return '<robot name=\"sample\"><link name=\"base_link\" /></robot>'",
            )

            with mock.patch.object(cli, "read_urdf_source") as read_urdf_source:
                self.assertEqual(0, cli.generate_urdf_targets([str(source_path)], output=str(output_path)))

            read_urdf_source.assert_called_once_with(output_path.resolve())

    def test_rejects_invalid_generated_output(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            output_path = Path(tempdir) / "custom" / "robot.urdf"
            _write_urdf_source(source_path, "return '<not-robot />'")

            with self.assertRaisesRegex(UrdfSourceError, "root element must be <robot>"):
                cli.generate_urdf_targets([str(source_path)], output=str(output_path))

    def test_generates_mixed_plain_and_paired_targets(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            root = Path(tempdir)
            first_path = root / "first.py"
            second_path = root / "second.py"
            second_output = root / "custom" / "second.urdf"
            _write_urdf_source(first_path, "return '<robot name=\"first\"><link name=\"base\" /></robot>'")
            _write_urdf_source(second_path, "return '<robot name=\"second\"><link name=\"base\" /></robot>'")

            self.assertEqual(0, cli.generate_urdf_targets([str(first_path), f"{second_path}={second_output}"]))

            self.assertTrue(first_path.with_suffix(".urdf").exists())
            self.assertTrue(second_output.exists())
            self.assertFalse(second_path.with_suffix(".urdf").exists())

    def test_rejects_legacy_urdf_output_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_urdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<robot name=\"sample\"><link name=\"base_link\" /></robot>',",
                        "    'urdf_output': 'legacy/ignored.urdf',",
                        "}",
                    ]
                ),
            )

            with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): urdf_output"):
                cli.generate_urdf_targets([str(source_path)])

    def test_rejects_legacy_validate_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_urdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<robot name=\"sample\"><link name=\"base_link\" /></robot>',",
                        "    'validate': False,",
                        "}",
                    ]
                ),
            )

            with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): validate"):
                cli.generate_urdf_targets([str(source_path)])

    def test_rejects_explorer_metadata_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            output_path = Path(tempdir) / "custom" / "sample_robot.urdf"
            _write_urdf_source(
                source_path,
                "\n".join(
                    [
                        "return {",
                        "    'xml': '<robot name=\"sample\"><link name=\"base_link\" /></robot>',",
                        "    'explorer_metadata': {",
                        "        'schemaVersion': 1,",
                        "        'kind': 'example-urdf-consumer',",
                        "        'defaultJoints': {'joint_1': 90},",
                        "    },",
                        "}",
                    ]
                ),
            )

            with self.assertRaisesRegex(TypeError, "unsupported field\\(s\\): explorer_metadata"):
                cli.generate_urdf_targets([f"{source_path}={output_path}"])
            self.assertFalse(output_path.exists())

    def test_rejects_invalid_output_suffix(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            source_path = Path(tempdir) / "sample_robot.py"
            _write_urdf_source(source_path, "return '<robot name=\"sample\"><link name=\"base\" /></robot>'")

            with self.assertRaisesRegex(ValueError, "must end in .urdf"):
                cli.generate_urdf_targets([f"{source_path}={Path(tempdir) / 'sample.xml'}"])

    def test_rejects_duplicate_output_paths(self) -> None:
        with tempfile.TemporaryDirectory(prefix="tmp-urdf-") as tempdir:
            first_path = Path(tempdir) / "first.py"
            second_path = Path(tempdir) / "second.py"
            output_path = Path(tempdir) / "same.urdf"
            _write_urdf_source(first_path, "return '<robot name=\"first\"><link name=\"base\" /></robot>'")
            _write_urdf_source(second_path, "return '<robot name=\"second\"><link name=\"base\" /></robot>'")

            with self.assertRaisesRegex(ValueError, "used more than once"):
                cli.generate_urdf_targets([f"{first_path}={output_path}", f"{second_path}={output_path}"])


if __name__ == "__main__":
    unittest.main()
