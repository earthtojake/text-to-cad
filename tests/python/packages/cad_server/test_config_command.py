"""Saved settings that an environment variable overrides, and ``cad config``, which shows and changes them.

A public variable declared a setting in ``cad._internal.environment`` is read through ``environment.value``: the
environment's value where it is set and not blank, else the ``config`` section of ``settings.json`` in the state
folder, else ``""``, the reader's default. The library only reads the file and never fails to; ``cad config`` writes
it under the settings' lock, refusing an unknown key or a value its kind does not take before anything is written.
Every test runs in a state folder of its own, with none of the settings' variables set.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cad._internal import environment, programs
from cad_server import cli

VARIABLES = [row.name for row in environment.settings()]


def _run(argv: list[str]) -> tuple[int, str, str]:
    """``cad <argv>`` as the console runs it: its exit status, stdout and stderr."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = cli.main(argv)
        except SystemExit as exited:
            code = exited.code
    return code, out.getvalue(), err.getvalue()


class Settings(unittest.TestCase):
    def setUp(self) -> None:
        held = tempfile.TemporaryDirectory()
        self.addCleanup(held.cleanup)
        self.state = Path(held.name) / "state"
        self.state.mkdir()
        self.file = self.state / "settings.json"
        clean = {name: value for name, value in os.environ.items() if name not in VARIABLES}
        patched = mock.patch.dict(os.environ, {**clean, "CAD_STATE_DIR": str(self.state), "CAD_TELEMETRY": "0",
                                               "CAD_UPDATE_CHECK": "0"}, clear=True)
        patched.start()
        self.addCleanup(patched.stop)

    def save(self, settings: object) -> None:
        self.file.write_text(json.dumps(settings), encoding="utf-8")


class Precedence(Settings):
    def test_a_count_is_its_default_then_saved_then_the_environment_s(self) -> None:
        self.assertEqual(environment.resolved("CAD_ENGINE_WORKERS"), ("", "default"))
        self.save({"config": {"engine_workers": "3"}})
        self.assertEqual(environment.resolved("CAD_ENGINE_WORKERS"), ("3", "saved"))
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKERS": "5"}):
            self.assertEqual(environment.resolved("CAD_ENGINE_WORKERS"), ("5", "environment"))
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKERS": "  "}):
            self.assertEqual(environment.value("CAD_ENGINE_WORKERS"), "3", "a blank variable is unset")

    def test_a_path_is_its_default_then_saved_then_the_environment_s(self) -> None:
        self.assertEqual(environment.value("CAD_CCX"), "")
        self.save({"config": {"ccx": "/saved/ccx"}})
        self.assertEqual(environment.resolved("CAD_CCX"), ("/saved/ccx", "saved"))
        with mock.patch.dict(os.environ, {"CAD_CCX": "/named/ccx"}):
            self.assertEqual(environment.resolved("CAD_CCX"), ("/named/ccx", "environment"))

    def test_only_a_setting_consults_the_file(self) -> None:
        self.save({"config": {"state_dir": "/elsewhere", "font_guard": "0"}})
        os.environ.pop("CAD_FONT_GUARD", None)
        self.assertEqual(environment.resolved("CAD_FONT_GUARD"), ("", "default"))

    def test_a_missing_unreadable_or_malformed_file_saves_nothing_and_raises_nothing(self) -> None:
        self.assertEqual(environment.saved(), {}, "no file")
        for text in ("{not json", "[1, 2]", '{"config": ["engine_workers"]}', '{"config": {"engine_workers": true}}',
                     "\udcff"):
            with self.subTest(text=text):
                self.file.write_bytes(text.encode("utf-8", "surrogateescape"))
                self.assertEqual(environment.saved(), {})
                self.assertEqual(environment.resolved("CAD_ENGINE_WORKERS"), ("", "default"))
        self.file.unlink()
        self.file.mkdir()  # there, and not a file that reads
        self.assertEqual(environment.saved(), {})
        self.assertEqual(environment.value("CAD_KICAD_CLI"), "")

    def test_the_server_s_worker_cap_resolves_from_a_saved_setting(self) -> None:
        from cad_server.engine.daemon import worker_cap

        self.assertEqual(worker_cap(), os.cpu_count() or 1)
        self.save({"config": {"engine_workers": "2"}})
        self.assertEqual(worker_cap(), 2)
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKERS": "7"}):
            self.assertEqual(worker_cap(), 7)

    def test_a_program_resolves_from_a_saved_setting_and_its_refusal_names_the_setting(self) -> None:
        from cad.kicad import _program as kicad

        cli_path = self.state / ("kicad-cli.exe" if sys.platform.startswith("win") else "kicad-cli")
        cli_path.write_text("", encoding="utf-8")
        self.save({"config": {"kicad_cli": str(cli_path)}})
        self.assertEqual(programs._named_outright("CAD_KICAD_CLI"), str(cli_path))  # noqa: SLF001
        self.assertTrue(kicad.carried())
        self.assertEqual(kicad.find_kicad_cli(), cli_path)
        self.save({"config": {"kicad_cli": str(self.state / "kicad")}})
        with self.assertRaisesRegex(kicad.KicadMissingError, "the saved setting kicad_cli .* names"):
            kicad.find_kicad_cli()


class TheCommand(Settings):
    def test_list_json_gives_every_setting_its_value_source_and_variable(self) -> None:
        self.save({"config": {"engine_checks": "2"}})
        with mock.patch.dict(os.environ, {"CAD_ENGINE_PORT": "4000"}):
            code, said, _ = _run(["config", "list", "--json"])
        self.assertEqual(code, 0)
        found = json.loads(said)
        self.assertTrue(found["ok"])
        self.assertEqual([item["variable"] for item in found["settings"]], VARIABLES)
        by_key = {item["key"]: item for item in found["settings"]}
        self.assertEqual(by_key["engine_checks"], {"key": "engine_checks", "value": "2", "source": "saved",
                                                   "variable": "CAD_ENGINE_CHECKS"})
        self.assertEqual(by_key["engine_port"]["source"], "environment")
        self.assertEqual(by_key["ccx"], {"key": "ccx", "value": "", "source": "default", "variable": "CAD_CCX"})
        code, said, _ = _run(["config"])
        self.assertEqual(code, 0)
        self.assertEqual(len(said.splitlines()), len(VARIABLES), said)

    def test_set_saves_get_reads_and_another_section_survives(self) -> None:
        self.save({"telemetry": {"choice": "off"}})
        code, said, _ = _run(["config", "set", "CAD_ENGINE_WORKERS", "2"])
        self.assertEqual(code, 0, said)
        self.assertIn("engine_workers: 2 saved", said)
        self.assertIn("`cad server stop`, then `cad server start`", said, "the server reads it as it starts")
        kept = json.loads(self.file.read_text(encoding="utf-8"))
        self.assertEqual(kept, {"telemetry": {"choice": "off"}, "config": {"engine_workers": "2"}})
        code, said, _ = _run(["config", "get", "engine_workers", "--json"])
        self.assertEqual(json.loads(said), {"ok": True, "key": "engine_workers", "value": "2", "source": "saved",
                                            "variable": "CAD_ENGINE_WORKERS"})
        with mock.patch.dict(os.environ, {"CAD_ENGINE_WORKERS": "5"}):
            code, said, _ = _run(["config", "set", "engine_workers", "3"])
        self.assertIn("CAD_ENGINE_WORKERS is set in this environment and overrides the saved value here", said)
        code, said, _ = _run(["config", "set", "kicad_3dmodels", os.path.abspath("models")])
        self.assertEqual(code, 0)
        self.assertNotIn("cad server stop", said, "read where it is used, never only at a start")

    def test_unset_removes_the_saved_value(self) -> None:
        self.save({"telemetry": {"choice": "off"}, "config": {"engine_workers": "2", "ccx": "/x/ccx"}})
        code, said, _ = _run(["config", "unset", "engine_workers"])
        self.assertEqual(code, 0)
        self.assertIn("the saved value removed", said)
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8")),
                         {"telemetry": {"choice": "off"}, "config": {"ccx": "/x/ccx"}})
        _run(["config", "unset", "ccx"])
        self.assertEqual(json.loads(self.file.read_text(encoding="utf-8")), {"telemetry": {"choice": "off"}})
        code, said, _ = _run(["config", "unset", "ccx"])
        self.assertEqual((code, said.strip()), (0, "ccx: no value was saved"))

    def test_a_state_folder_that_cannot_be_written_is_said_with_what_to_do(self) -> None:
        # An agent app's shell sandbox refuses the state folder: the command fails in a sentence naming the folder
        # and the way out, and nothing it printed says the value was saved.
        with mock.patch("cad_server.settings.update_section", side_effect=PermissionError(13, "Permission denied")):
            code, said, err = _run(["config", "set", "engine_workers", "2"])
        self.assertNotEqual(code, 0)
        self.assertEqual(said, "")
        for words in ("could not save the setting", str(self.state), "Permission denied", "outside it"):
            self.assertIn(words, err)
        self.assertFalse(self.file.exists())

    def test_an_unknown_key_and_a_bad_value_are_refused_and_nothing_is_written(self) -> None:
        for argv, words in ((["set", "engine_worker", "2"], "no setting 'engine_worker'; the settings are engine_port"),
                            (["set", "CAD_TELEMETRY", "0"], "no setting 'CAD_TELEMETRY'"),
                            (["get", "nope"], "no setting 'nope'"),
                            (["unset", "nope"], "no setting 'nope'"),
                            (["set", "engine_workers", "many"], "engine_workers takes a whole number of zero or more"),
                            (["set", "engine_workers", "-1"], "a whole number of zero or more"),
                            (["set", "engine_port", "65536"], "a port"),
                            (["set", "engine_memory_mb", "nan"], "a number of zero or more"),
                            (["set", "ccx", "ccx"], "the full path of a file"),
                            (["set", "kicad_3dmodels", ""], "full paths of folders")):
            with self.subTest(argv=argv):
                code, said, err = _run(["config", *argv])
                self.assertEqual(code, 2, err)
                self.assertIn(words, err)
                self.assertFalse(self.file.exists(), "nothing written")
        code, said, _ = _run(["config", "get", "nope", "--json"])
        self.assertEqual((code, json.loads(said)["reason"]), (2, "invalid_argument"))


if __name__ == "__main__":
    unittest.main()
