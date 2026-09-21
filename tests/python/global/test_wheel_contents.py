from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
import warnings
import zipfile

from tests.python.support.paths import REPO_ROOT

spec = importlib.util.spec_from_file_location("wheel_contents", REPO_ROOT / "scripts/release/wheel_contents.py")
wheel_contents = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wheel_contents)


class WheelContentsTests(unittest.TestCase):
    def test_clean_staging_does_not_copy_previous_build_or_package_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            paths = ["src/cadgen/_runtime/viewer/new.js", "build/lib/cadgen/_runtime/viewer/old.js",
                     "src/cadgen.egg-info/SOURCES.txt", "src/cadgen/__pycache__/module.pyc"]
            for name in paths:
                path = source / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"asset")
            wheel_contents.stage_package(source, root / "staged")
            staged = sorted(path.relative_to(root / "staged").as_posix()
                            for path in (root / "staged").rglob("*") if path.is_file())
            self.assertEqual(staged, [paths[0]])
            self.assertTrue((source / paths[1]).exists(), "developer build scratch is not ours to remove")

    def test_runtime_requires_exact_paths_and_bytes(self):
        name = "cadgen/_runtime/viewer/current.js"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "src" / name
            source.parent.mkdir(parents=True)
            source.write_bytes(b"current bytes")
            cases = [
                ([(name, b"current bytes")], None),
                ([(name, b"current bytes"), ("cadgen/_runtime/viewer/old.js", b"stale")], "extra"),
                ([], "missing"),
                ([(name, b"old bytes")], "different bytes"),
                ([(name, b"current bytes"), (name, b"current bytes")], "duplicate"),
            ]
            for entries, error in cases:
                with self.subTest(error=error):
                    wheel = root / "test.whl"
                    with warnings.catch_warnings(), zipfile.ZipFile(wheel, "w") as archive:
                        warnings.simplefilter("ignore", UserWarning)
                        archive.writestr("cadgen/__init__.py", b"# unrelated Python module")
                        for filename, data in entries:
                            archive.writestr(filename, data)
                    if error:
                        with self.assertRaisesRegex(ValueError, error):
                            wheel_contents.verify_runtime(wheel, root)
                    else:
                        self.assertEqual(wheel_contents.verify_runtime(wheel, root), 1)

    def test_an_unbundled_source_cannot_pass_with_an_empty_wheel(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "No bundled runtime"):
                wheel_contents.verify_runtime(root / "absent.whl", root)


if __name__ == "__main__":
    unittest.main()
