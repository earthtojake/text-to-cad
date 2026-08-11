"""Server-side implicit CAD export: the CLI the viewer's Export action now runs.

Export used to happen in the BROWSER -- the client loaded the `.implicit.js` module, meshed
and serialized it in the tab, and POSTed the bytes for the server to write. That kept a
second live geometry runtime in the viewer for the sake of one menu item. This module runs
the same shipped exporter (`packages/implicitjs/scripts/export.mjs`) in a Node child instead,
so the viewer keeps exactly one render path.

Every test here spawns the real exporter. The properties worth pinning are properties of the
pair -- the file lands where it was asked to, the payload names it, a bad format is refused
before Node is spawned -- and a mocked child proves none of them.
"""

from __future__ import annotations

import shutil
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path
from tests.python.support.tmp_root import temporary_directory

add_repo_path("packages/cadgen/src")

from cadgen._internal.implicit_package import (  # noqa: E402
    IMPLICIT_DESCRIPTOR_NAME,
    IMPLICIT_GLB_NAME,
)
from cadgen.catalog import render_package_dir  # noqa: E402
from cadgen.implicit_export import (  # noqa: E402
    IMPLICIT_EXPORT_FORMATS,
    build_parser,
    export_implicit_model,
    implicit_export_cli,
    normalize_export_format,
)

_NODE = shutil.which("node")

_MODEL_SOURCE = """
export default {
  name: "test sphere",
  units: "mm",
  bounds: 12,
  glsl: `
    float sdf(vec3 p) {
      return length(p) - 8.0;
    }
    vec3 color(vec3 p, vec3 normal) {
      return vec3(0.2, 0.6, 0.9);
    }
  `,
};
"""

_RESOLUTION = 16


class ExportFormatSurface(unittest.TestCase):
    """No Node needed: the format gate is the cheap half and it must reject before spawning."""

    def test_formats_are_mesh_only(self) -> None:
        # There is no "export to implicit": the `.implicit.js` source IS the native file.
        self.assertEqual(sorted(IMPLICIT_EXPORT_FORMATS), ["3mf", "glb", "stl"])

    def test_normalization_accepts_a_dotted_or_cased_format(self) -> None:
        self.assertEqual(normalize_export_format(".STL"), "stl")
        self.assertEqual(normalize_export_format("3mf"), "3mf")

    def test_an_unsupported_format_is_refused(self) -> None:
        with self.assertRaises(ValueError):
            normalize_export_format("step")
        with self.assertRaises(ValueError):
            normalize_export_format("")

    def test_the_cli_mirrors_step_export_target(self) -> None:
        # The viewer's export backend shells out to every format's producer through one
        # contract; a drifting flag surface here is a runtime failure with no compile-time
        # signal, so the parser is pinned.
        args = build_parser().parse_args(
            ["--repo-root", ".", "--source-path", "a.implicit.js", "--format", "stl", "--out", "a.stl"]
        )
        self.assertEqual(args.format, "stl")
        self.assertEqual(args.out, "a.stl")
        self.assertIsNone(args.resolution)


@unittest.skipUnless(_NODE, "node is required to run the implicit CAD export CLI")
class ImplicitExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = temporary_directory(prefix="implicit-export-")
        self.addCleanup(self._tmp.cleanup)
        self.folder = Path(self._tmp.name)
        self.source = self.folder / "test-shape.implicit.js"
        self.source.write_text(_MODEL_SOURCE, encoding="utf-8")

    def test_the_shipped_export_cli_is_reachable(self) -> None:
        # A runtime that vendors cadgen but not implicitjs cannot export at all, and must
        # say so with the path it looked at rather than failing later inside node.
        self.assertTrue(implicit_export_cli().is_file())

    def test_export_writes_the_requested_file_and_reports_it(self) -> None:
        out_path = self.folder / "out" / "shape.stl"
        payload = export_implicit_model(
            source_path=self.source, fmt="stl", out_path=out_path, resolution=_RESOLUTION
        )
        self.assertTrue(payload["ok"])
        self.assertEqual(Path(payload["path"]), out_path.resolve())
        self.assertEqual(payload["filename"], "shape.stl")
        self.assertEqual(payload["format"], "stl")
        self.assertTrue(out_path.is_file())
        self.assertGreater(out_path.stat().st_size, 0)
        self.assertEqual(payload["bytes"], out_path.stat().st_size)

    def test_export_bakes_no_render_package(self) -> None:
        # An export is a file the user asked for, not a cache the viewer reads. It takes the
        # GENERATOR lock (whose sentinel does live in the package dir) precisely so it can
        # occupy the model without CLAIMING to rewrite its package -- so no descriptor and no
        # model.glb appear, and a fully current model does not start reporting `generating`.
        export_implicit_model(
            source_path=self.source,
            fmt="glb",
            out_path=self.folder / "shape.glb",
            resolution=_RESOLUTION,
        )
        package_dir = render_package_dir(self.source)
        self.assertFalse((package_dir / IMPLICIT_DESCRIPTOR_NAME).exists())
        self.assertFalse((package_dir / IMPLICIT_GLB_NAME).exists())

    def test_a_non_implicit_source_is_refused(self) -> None:
        other = self.folder / "notes.js"
        other.write_text("export default {};\n", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            export_implicit_model(
                source_path=other, fmt="stl", out_path=self.folder / "notes.stl"
            )

    def test_a_missing_source_is_refused(self) -> None:
        with self.assertRaises(FileNotFoundError):
            export_implicit_model(
                source_path=self.folder / "nope.implicit.js",
                fmt="stl",
                out_path=self.folder / "nope.stl",
            )


if __name__ == "__main__":
    unittest.main()
