"""The CAD app as a host keeps it (``cadgen.mcp.ui``): the resource is the shell, addressed by the
engine's release and its build, and the app it loads is the engine's own (``GET /__cad/mcp-app``),
read through the call a card's host carries back (``cad_http``) as any viewer route is."""

from __future__ import annotations

import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

import cadgen  # noqa: E402
from cadgen.mcp import ui  # noqa: E402
from cadgen.mcp.tunnel import ViewerTunnel  # noqa: E402


class ShellTest(unittest.TestCase):
    def setUp(self) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cad-shell-")
        self.addCleanup(scratch.cleanup)
        self.page = Path(scratch.name)
        (self.page / ui.SHELL).write_text("<!doctype html><title>CAD</title>", encoding="utf-8")
        (self.page / ui.APP).write_text("export const app = 1;\n", encoding="utf-8")
        patched = mock.patch.dict(os.environ, {"CADGEN_MCP_APP_DIR": str(self.page)})
        patched.start()
        self.addCleanup(patched.stop)

    def test_the_resource_is_the_shell_named_by_the_engine_s_release(self) -> None:
        page = ui.AppPage(self.page)
        self.assertRegex(page.uri, rf"^ui://cad/{cadgen.__version__.replace('.', r'\.')}/[0-9a-f]{{16}}/app\.html$")
        self.assertEqual(page.html(), "<!doctype html><title>CAD</title>")
        self.assertTrue(page.owns("ui://cad/0.0.1/0123456789abcdef/app.html"), "any build's shell reads as this one")

    def test_the_engine_serves_its_app_to_the_shell_through_the_card_s_call(self) -> None:
        answer = ViewerTunnel().serve(method="GET", url="http://cad.invalid/__cad/mcp-app", headers={}, body=b"")
        self.assertEqual(answer["status"], 200, answer)
        self.assertTrue(answer["headers"]["content-type"].startswith("text/javascript"))
        self.assertEqual(base64.b64decode(answer["body"]), b"export const app = 1;\n")
        # A new build is read again; none at all is said.
        (self.page / ui.APP).write_text("export const app = 2;\n", encoding="utf-8")
        os.utime(self.page / ui.APP, ns=(1, 1))
        self.assertEqual(ui.app_code(), b"export const app = 2;\n")
        (self.page / ui.APP).unlink()
        missing = ViewerTunnel().serve(method="GET", url="http://cad.invalid/__cad/mcp-app", headers={}, body=b"")
        self.assertEqual(missing["status"], 404)


if __name__ == "__main__":
    unittest.main()
