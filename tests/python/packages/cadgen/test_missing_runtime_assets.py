"""A missing packaged runtime must say how to get one.

``packages/cadgen/src/cadgen/_runtime`` is built, never committed, so the ordinary state
of a fresh clone is that it does not exist. Every failure downstream of that is opaque --
a Node child dying on a file it cannot open, a headless page 404ing on its own script --
so the two resolvers that reach for it answer with the fix instead, and the fix differs by
where cadgen is running from: a checkout builds, an installation reinstalls.

The assertion is on the ACTIONABLE half of the message, not its wording: what must never
regress is that a developer is told the command and a user is told it is a bad install.
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")

from cadgen import assets  # noqa: E402
from cadgen._internal.node_runtime import NodeBuilderError, node_builder_script  # noqa: E402

BUNDLER = "scripts/bundle/bundle.sh"


class MissingRuntimeNamesTheBundler(unittest.TestCase):
    def setUp(self) -> None:
        self.empty = Path(tempfile.mkdtemp(prefix="cadgen-empty-runtime-"))
        self.addCleanup(self.empty.rmdir)

    def test_a_missing_node_builder_names_the_bundler_in_a_checkout(self) -> None:
        # The env override is how a caller points the lookup elsewhere, and it is also the
        # cheapest way to stand in for an unbundled _runtime/node: the resolution order
        # ends at a directory with no builders in it either way.
        with mock.patch.dict("os.environ", {"CADGEN_NODE_BUILDERS_DIR": str(self.empty)}):
            with self.assertRaises(NodeBuilderError) as caught:
                node_builder_script("mesh-export.mjs")
        message = str(caught.exception)
        self.assertIn("mesh-export.mjs", message)
        self.assertIn(BUNDLER, message)

    def test_a_missing_browser_runtime_names_the_bundler_in_a_checkout(self) -> None:
        with self.assertRaises(assets.AssetMissing) as caught:
            assets.require_browser_runtime(self.empty)
        message = str(caught.exception)
        # Both files, so a bundle that wrote one and lost the other is not reported as if
        # the whole stage were absent.
        self.assertIn("render.html", message)
        self.assertIn("snapshot-render.js", message)
        self.assertIn(BUNDLER, message)

    def test_a_half_built_browser_runtime_names_only_what_is_missing(self) -> None:
        (self.empty / "render.html").write_text("<!doctype html>", encoding="utf-8")
        self.addCleanup((self.empty / "render.html").unlink)
        with self.assertRaises(assets.AssetMissing) as caught:
            assets.require_browser_runtime(self.empty)
        message = str(caught.exception)
        self.assertIn("snapshot-render.js", message)
        self.assertNotIn("render.html,", message)

    def test_a_complete_browser_runtime_is_returned_unchanged(self) -> None:
        for name in ("render.html", "snapshot-render.js"):
            (self.empty / name).write_text("built", encoding="utf-8")
            self.addCleanup((self.empty / name).unlink)
        self.assertEqual(self.empty, assets.require_browser_runtime(self.empty))

    def test_an_installed_cadgen_is_told_to_reinstall_not_to_run_a_repo_script(self) -> None:
        # A wheel has no repository around it, so naming the bundler there would be advice
        # nobody can follow. The source-checkout anchor is what decides.
        with mock.patch.object(assets, "_dev_builders_dir", return_value=None):
            hint = assets.runtime_build_hint(self.empty / "snapshot-render.js")
        self.assertNotIn(BUNDLER, hint)
        self.assertIn("Reinstall cadgen", hint)


if __name__ == "__main__":
    unittest.main()
