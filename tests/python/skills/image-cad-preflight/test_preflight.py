from __future__ import annotations

import base64
import copy
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tests.python.support.paths import REPO_ROOT as ROOT
SCRIPT = ROOT / "skills/image-cad-preflight/scripts/visual_preflight.py"
loader = importlib.util.spec_from_file_location("visual_preflight", SCRIPT)
preflight = importlib.util.module_from_spec(loader)
loader.loader.exec_module(preflight)
PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a5V0AAAAASUVORK5CYII=")


def inspection():
    return {"schema_version":"1.0", "p0":[{"region":"top surface", "observation":"appears shallow-convex",
            "confidence":"MEDIUM", "views":["V1"], "visual_basis":"broad highlight changes across the top",
            "construction_implication":"check a curved section before using an extrusion"}],
            "p1":[], "unknown":[{"question":"rear cavity depth", "reason":"rear is not visible", "views":["V1"]}]}


class PreflightTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="visual-preflight-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.image = self.root / "reference with spaces.png"
        self.image.write_bytes(PNG)
        self.request = self.root / "request.txt"
        self.request.write_text("Reconstruct the handle, width 100 mm.", encoding="utf-8")
        self.input = self.root / "inspection.json"
        self.input.write_text(json.dumps(inspection()), encoding="utf-8")
        self.md = self.root / "visual_spec.md"
        self.json = self.root / "visual_spec.json"

    def flags(self):
        return ["--image", str(self.image), "--request-file", str(self.request),
                "--output", str(self.md), "--json-out", str(self.json)]

    def test_skill_runs_from_standalone_copy(self):
        # Skills installers copy just this directory, without the repository.
        installed = self.root / "installed skill"
        shutil.copytree(SCRIPT.parents[1], installed,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        result = subprocess.run(
            [sys.executable, str(installed / "scripts/visual_preflight.py"),
             "--from-json", str(self.input), *self.flags()],
            cwd=self.root, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(self.json.read_text(encoding="utf-8"))
        self.assertEqual(output["mode"], "main-session")
        self.assertIn(output["run_id"], self.md.read_text(encoding="utf-8"))

    def test_main_session_cli_provenance_and_evidence(self):
        result = subprocess.run([sys.executable, str(SCRIPT), "--from-json", str(self.input), *self.flags()],
                                capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(self.json.read_text(encoding="utf-8"))
        text = self.md.read_text(encoding="utf-8")
        self.assertEqual(output["mode"], "main-session")
        self.assertEqual(output["sources"][0]["sha256"], preflight.digest(self.image))
        self.assertEqual(output["request"]["sha256"], preflight.digest(self.request))
        self.assertIn(output["run_id"], text)
        self.assertIn(inspection()["p0"][0]["visual_basis"], text)
        self.assertIn(inspection()["p0"][0]["construction_implication"], text)

    def test_in_chat_fallback_is_honestly_labeled(self):
        result = preflight.main(["--from-json", str(self.input), "--image-label", "Original chat attachment",
                                 "--output", str(self.md), "--json-out", str(self.json)])
        self.assertEqual(result, 0)
        output = json.loads(self.json.read_text(encoding="utf-8"))
        self.assertEqual(output["mode"], "main-session")
        self.assertIsNone(output["sources"][0]["sha256"])

    def test_schema_rejects_bad_confidence_extra_fields_and_empty_evidence(self):
        for field, value in (("confidence", "CERTAIN"), ("visual_basis", "  "), ("invented_radius", 5)):
            with self.subTest(field=field):
                spec = inspection()
                spec["p0"][0][field] = value
                with self.assertRaises(ValueError):
                    preflight.validate_inspection(spec, ["V1"])

    def test_unknown_views_and_excess_observations_rejected(self):
        spec = inspection()
        spec["p0"][0]["views"] = ["V2"]
        with self.assertRaises(ValueError):
            preflight.validate_inspection(spec, ["V1"])
        spec = inspection()
        spec["p0"] *= 6
        with self.assertRaises(ValueError):
            preflight.validate_inspection(spec, ["V1"])

    def test_low_confidence_p0_and_empty_groups_valid(self):
        spec = inspection()
        spec["p0"][0]["confidence"] = "LOW"
        preflight.validate_inspection(spec, ["V1"])
        preflight.validate_inspection({"schema_version":"1.0", "p0":[], "p1":[], "unknown":[]}, ["V1"])

    def test_original_inputs_never_overwritten(self):
        before = self.image.read_bytes()
        self.assertEqual(preflight.main(["--from-json", str(self.input), "--image", str(self.image),
                                         "--output", str(self.image), "--json-out", str(self.json)]), 1)
        self.assertEqual(self.image.read_bytes(), before)

    def test_failure_keeps_old_outputs_but_reports_failure(self):
        self.md.write_text("old spec", encoding="utf-8")
        self.json.write_text("old result", encoding="utf-8")
        with patch.object(preflight, "run_child", side_effect=ValueError("fake child failed")):
            result = preflight.main([*self.flags(), "--codex", sys.executable])
        self.assertEqual(result, 1)
        self.assertEqual(self.md.read_text(encoding="utf-8"), "old spec")
        self.assertEqual(self.json.read_text(encoding="utf-8"), "old result")

    def test_isolated_child_contract_and_multiview(self):
        other = self.root / "side.png"
        other.write_bytes(PNG)
        def fake_child(command, prompt, timeout):
            self.assertIn("--ephemeral", command)
            self.assertEqual(command[command.index("--sandbox")+1], "read-only")
            self.assertNotIn("--model", command)
            self.assertEqual(command[-4::2], ["--image", "--image"])
            # Windows TEMP can use an 8.3 alias (RUNNER~1); compare file identity.
            self.assertTrue(Path(command[-3]).samefile(self.image))
            self.assertTrue(Path(command[-1]).samefile(other))
            self.assertNotIn(self.request.read_text(encoding="utf-8"), prompt)
            self.assertIn('"id": "V2"', prompt)
            self.assertFalse((Path(command[command.index("--cd")+1]) / "AGENTS.md").exists())
            output = Path(command[command.index("--output-last-message")+1])
            output.write_text(json.dumps(inspection()), encoding="utf-8")
        with patch.object(preflight, "run_child", side_effect=fake_child):
            result = preflight.main([*self.flags(), "--image", str(other), "--codex", sys.executable])
        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.json.read_text(encoding="utf-8"))["mode"], "isolated-child")

    def test_dry_run_publishes_nothing(self):
        with patch.object(preflight, "run_child") as child:
            result = preflight.main([*self.flags(), "--codex", sys.executable, "--dry-run"])
        self.assertEqual(result, 0)
        child.assert_not_called()
        self.assertFalse(self.md.exists())
        self.assertFalse(self.json.exists())

    def test_inputs_changed_during_child_rejected(self):
        def fake_child(command, prompt, timeout):
            Path(command[command.index("--output-last-message")+1]).write_text(json.dumps(inspection()), encoding="utf-8")
            self.image.write_bytes(PNG + b"changed")
        with patch.object(preflight, "run_child", side_effect=fake_child):
            result = preflight.main([*self.flags(), "--codex", sys.executable])
        self.assertEqual(result, 1)
        self.assertFalse(self.md.exists())

    def test_missing_malformed_or_unsupported_input_rejected(self):
        self.image.write_text("not an image", encoding="utf-8")
        self.assertEqual(preflight.main(["--from-json", str(self.input), *self.flags()]), 1)
        self.image.write_bytes(PNG)
        self.input.write_text("{}", encoding="utf-8")
        self.assertEqual(preflight.main(["--from-json", str(self.input), *self.flags()]), 1)
        self.input.unlink()
        self.assertEqual(preflight.main(["--from-json", str(self.input), *self.flags()]), 1)

    def test_nonzero_child_and_timeout(self):
        with self.assertRaisesRegex(ValueError, "exited"):
            preflight.run_child([sys.executable, "-c", "raise SystemExit(2)"], "", 10)
        with self.assertRaisesRegex(ValueError, "timed out"):
            preflight.run_child([sys.executable, "-c", "import sys; sys.stdin.read(); import time; time.sleep(10)"], "", 1)


if __name__ == "__main__":
    unittest.main()
