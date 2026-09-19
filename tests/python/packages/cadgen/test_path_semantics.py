"""``~`` expansion across cadgen's path arguments.

USER RULING: every cadgen CLI/function path argument takes NATIVE semantics —
relative resolves against the process working directory, absolute works
anywhere, ``~`` expands. The relative/absolute halves are pinned where each
door is tested; what is easy to regress is the tilde, because a bare
``Path(text)`` looks correct and only fails against a real ``~`` argument.

These drive the RESOLUTION helpers directly rather than the full commands: the
commands they belong to render geometry or import the CAD stack, and the thing
under test is one line of path handling in each.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen import catalog, snapshot_core  # noqa: E402
from cadgen.cli import doctor  # noqa: E402


class TildeExpansion(unittest.TestCase):
    def setUp(self) -> None:
        tempdir = temporary_directory(prefix="cadpath-")
        self.addCleanup(tempdir.cleanup)
        self.home = Path(tempdir.name).resolve()
        self.cwd = self.home / "cwd"
        self.cwd.mkdir(parents=True, exist_ok=True)
        patcher = mock.patch.dict(os.environ, {"HOME": str(self.home)}, clear=False)
        patcher.start()
        self.addCleanup(patcher.stop)
        # Path.expanduser reads HOME on POSIX and USERPROFILE on Windows.
        if os.name == "nt":  # pragma: no cover - parity, not a second code path
            nt_patcher = mock.patch.dict(
                os.environ, {"USERPROFILE": str(self.home)}, clear=False
            )
            nt_patcher.start()
            self.addCleanup(nt_patcher.stop)

    def test_snapshot_out_expands_a_tilde(self) -> None:
        resolved = snapshot_core.resolve_output_target(
            "~/renders/view.png",
            resolved_cwd=self.cwd,
            generated_name="generated.png",
        )
        self.assertEqual(Path(resolved), (self.home / "renders" / "view.png").resolve())

    def test_snapshot_out_still_resolves_relative_against_the_cwd(self) -> None:
        resolved = snapshot_core.resolve_output_target(
            "view.png",
            resolved_cwd=self.cwd,
            generated_name="generated.png",
        )
        self.assertEqual(Path(resolved), (self.cwd / "view.png").resolve())

    def test_doctor_target_expands_a_tilde(self) -> None:
        skill_dir = self.home / "skill"
        skill_dir.mkdir(parents=True, exist_ok=True)
        requirements = skill_dir / "requirements.txt"
        requirements.write_text("cadgen==9.9.9\n", encoding="utf-8")
        self.assertEqual(
            doctor._resolve_requirements("~/skill"), Path("~/skill").expanduser() / "requirements.txt"
        )
        self.assertEqual(doctor._resolve_requirements("~/skill/requirements.txt"), requirements)

    def test_doctor_target_reports_nothing_when_no_requirements_exist(self) -> None:
        empty = self.home / "empty"
        empty.mkdir(parents=True, exist_ok=True)
        self.assertIsNone(doctor._resolve_requirements("~/empty"))

    def test_scene_reader_expands_a_tilde(self) -> None:
        from cadgen.step_scene import _record_input
        document = self.home / "part.step"
        document.write_text("fixture", encoding="utf-8")
        self.assertEqual(_record_input("~/part.step", reader="read_scene"), document)

    def test_source_from_path_expands_a_tilde(self) -> None:
        document = self.home / "imported.step"
        document.write_text("ISO-10303-21;\nENDSEC;\nEND-ISO-10303-21;\n", encoding="utf-8")
        source = catalog.source_from_path(Path("~/imported.step"))
        self.assertIsNotNone(source)
        self.assertEqual(Path(source.step_path), document.resolve())


if __name__ == "__main__":
    unittest.main()
