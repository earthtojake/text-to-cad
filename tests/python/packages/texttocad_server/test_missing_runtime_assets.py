"""A missing packaged runtime must say how to get one, and assets resolve explicitly.

``packages/texttocad-server/src/cad_server/_runtime`` is built, never committed, so the ordinary state
of a fresh clone is that it does not exist. Every failure downstream of that is opaque --
a page 404ing on its own script -- so what reaches for it answers with the fix instead,
and the fix differs by where cadgen is running from: a checkout builds, an installation
reinstalls.

The assertion is on the ACTIONABLE half of the message, not its wording: what must never
regress is that a developer is told the command and a user is told it is a bad install.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/texttocad/src")

from cad_server import assets  # noqa: E402

BUNDLER = "scripts/bundle/bundle.sh"


class MissingRuntimeNamesTheBundler(unittest.TestCase):
    def test_a_checkout_is_told_to_run_the_bundler(self) -> None:
        with mock.patch.object(assets, "_in_source_checkout", return_value=True):
            hint = assets.runtime_build_hint(Path("_runtime") / "mcp" / "index.html")
        self.assertIn(BUNDLER, hint)

    def test_an_installed_cadgen_is_told_to_reinstall_not_to_run_a_repo_script(self) -> None:
        # A wheel has no repository around it, so naming the bundler there would be advice
        # nobody can follow. The source-checkout anchor is what decides.
        with mock.patch.object(assets, "_in_source_checkout", return_value=False):
            hint = assets.runtime_build_hint(Path("_runtime") / "mcp" / "index.html")
        self.assertNotIn(BUNDLER, hint)
        self.assertIn("Reinstall cadgen", hint)


class ExplicitRuntimeAssets(unittest.TestCase):
    def test_an_installed_package_uses_bundled_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            packaged = Path(tmp) / "cad_server" / "_runtime"
            with mock.patch.object(assets, "_RUNTIME", packaged), \
                    mock.patch.object(assets, "_dev_viewer_dist_dir", return_value=None), \
                    mock.patch.dict(os.environ, {"CADGEN_VIEWER_DIST": ""}):
                self.assertEqual(assets.viewer_dist_dir(), packaged / "viewer")

    def test_a_checkout_serves_its_own_web_build(self):
        root = Path(__file__).resolve().parents[4]
        self.assertTrue(assets._in_source_checkout())
        web_dist = root / "apps" / "web" / "dist"
        if (web_dist / "index.html").is_file():
            self.assertEqual(assets.viewer_dist_dir(), web_dist)

    def test_an_installation_never_takes_a_folder_above_it_for_a_checkout(self):
        # A wheel installed under any folder (a venv inside some project, a tool directory): an
        # apps/web or apps/mcp build in a folder above it is not this cadgen's, and is never served.
        from cad_server.mcp import ui

        with tempfile.TemporaryDirectory() as tmp:
            above = Path(tmp).resolve()
            for app in ("web", "mcp"):
                (above / "apps" / app / "dist").mkdir(parents=True)
                (above / "apps" / app / "package.json").write_text("{}", encoding="utf-8")
                for built in ("index.html", "shell.html"):
                    (above / "apps" / app / "dist" / built).write_text("<!doctype html>", encoding="utf-8")
            (above / "packages" / "core").mkdir(parents=True)
            (above / "packages" / "core" / "package.json").write_text("{}", encoding="utf-8")
            installed = above / "venv" / "lib" / "python3.14" / "site-packages" / "cad_server"
            installed.mkdir(parents=True)
            packaged = installed / "_runtime"
            with mock.patch.object(assets, "__file__", str(installed / "assets.py")), \
                    mock.patch.object(assets, "_RUNTIME", packaged), \
                    mock.patch.dict(os.environ, {"CADGEN_VIEWER_DIST": "", "CADGEN_MCP_APP_DIR": ""}):
                self.assertIsNone(assets.checkout_root())
                self.assertFalse(assets._in_source_checkout())
                self.assertEqual(assets.viewer_dist_dir(), packaged / "viewer")
                self.assertEqual(ui.app_dir(), packaged / "mcp")

    def test_development_overrides_are_explicit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            with mock.patch.dict(os.environ, {"CADGEN_VIEWER_DIST": str(root / "web")}):
                self.assertEqual(assets.viewer_dist_dir(), root / "web")


if __name__ == "__main__":
    unittest.main()
