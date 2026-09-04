"""Regression tests for incremental-regen building blocks:

- source import-closure capture/check (cadgen.source_hash)
- the binary (BinTools) scene cache round-trip
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

import build123d
from OCP.TopAbs import TopAbs_FACE
from OCP.TopExp import TopExp_Explorer

from cadgen._internal import source_hash as cad_source_hash
from cadgen._internal import step_scene
from cadgen._internal.step_scene import LoadedStepScene, OccurrenceNode
from tests.python.support.tmp_root import temporary_directory


def _face_count(shape: object) -> int:
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    count = 0
    while explorer.More():
        count += 1
        explorer.Next()
    return count


class SourceClosureTests(unittest.TestCase):
    def test_closure_round_trip_detects_dependency_changes(self) -> None:
        with temporary_directory(prefix="closure-") as raw_dir:
            base = Path(raw_dir)
            script = base / "part.py"
            dep = base / "helper.py"
            script.write_text("import helper\n", encoding="utf-8")
            dep.write_text("VALUE = 1\n", encoding="utf-8")

            closure = cad_source_hash.closure_for_files(script, [dep], base=base)
            # The script and its dependency are both recorded.
            self.assertEqual(2, len(closure.files))

            # Re-checking the recorded file list against the recorded hash matches.
            self.assertTrue(
                cad_source_hash.closure_hash_matches(closure.closure_hash, closure.files, base=base)
            )

            # A semantic edit to a dependency invalidates the recorded hash (stale).
            dep.write_text("VALUE = 2\n", encoding="utf-8")
            self.assertFalse(
                cad_source_hash.closure_hash_matches(closure.closure_hash, closure.files, base=base)
            )

            # A missing recorded file is never a match (callers treat as stale).
            dep.unlink()
            self.assertFalse(
                cad_source_hash.closure_hash_matches(closure.closure_hash, closure.files, base=base)
            )

    def test_capture_runtime_closure_includes_imported_repo_local_modules(self) -> None:
        with temporary_directory(prefix="closure-capture-") as raw_dir:
            base = Path(raw_dir)
            script = base / "widget.py"
            dep = base / "shared_helper.py"
            script.write_text("import shared_helper\n", encoding="utf-8")
            dep.write_text("X = 1\n", encoding="utf-8")

            # Ensure a clean import so the sys.modules delta actually captures it.
            sys.modules.pop("shared_helper", None)
            before = set(sys.modules)
            sys.path.insert(0, str(base))
            try:
                import shared_helper  # noqa: F401  (exercise a real import)
                closure = cad_source_hash.capture_runtime_closure(before, script, base=base)
            finally:
                sys.path.remove(str(base))
                sys.modules.pop("shared_helper", None)

            self.assertIn("shared_helper.py", " ".join(closure.files))
            self.assertTrue(any(f.endswith("widget.py") for f in closure.files))

    def test_repo_local_modules_key_on_interpreter_not_cwd(self) -> None:
        """First-party detection keys on the interpreter's stdlib/site-packages layout, NOT a
        repo-root global or the process working directory. So the dependency closure a generator
        records is identical no matter which directory the build runs from, while build123d / OCP /
        stdlib stay excluded. Guards against reintroducing a repo-root containment filter (which
        silently truncated the closure when a build ran from a subdirectory)."""
        import json  # noqa: F401  (a stdlib module: must always be excluded)
        import os

        with temporary_directory(prefix="closure-root-indep-") as raw_dir:
            base = Path(raw_dir)
            (base / "first_party_mod.py").write_text("Y = 1\n", encoding="utf-8")
            sys.modules.pop("first_party_mod", None)
            sys.path.insert(0, str(base))
            previous_cwd = Path.cwd()
            try:
                import first_party_mod  # noqa: F401  (a real first-party import)
                names = ["json", "build123d", "first_party_mod"]
                # Capture from two unrelated working directories; the result must be identical
                # because the filter consults neither the cwd nor any repo-root global.
                results = []
                for cwd in (base, base.parent):
                    os.chdir(cwd)
                    results.append(cad_source_hash.repo_local_loaded_modules(names))
            finally:
                os.chdir(previous_cwd)
                sys.path.remove(str(base))
                sys.modules.pop("first_party_mod", None)

        self.assertEqual(results[0], results[1])
        captured = results[0]
        self.assertIn("first_party_mod", captured)   # first-party temp module: included
        self.assertNotIn("json", captured)           # stdlib: excluded
        self.assertNotIn("build123d", captured)      # site-packages: excluded


class ReadStepCachedTests(unittest.TestCase):
    """cadgen read_step: build123d shape identical to build123d.import_step, served from cache."""

    def test_matches_build123d_import_and_warms_from_the_render_package(self) -> None:
        with temporary_directory(prefix="import-cached-") as raw_dir:
            step_path = Path(raw_dir) / "widget.step"
            build123d.export_step(build123d.Box(4, 3, 2), step_path)

            from cadgen.step_scene import read_step

            raw = build123d.import_step(step_path)
            cold = read_step(step_path)  # cold: full text-STEP parse

            self.assertEqual(_face_count(raw.wrapped), _face_count(cold.wrapped))
            self.assertAlmostEqual(raw.volume, cold.volume, places=4)

            # Once the entry is built, its tree IS the warm store:
            # read_step must reconstruct from it without re-parsing the text.
            from cadgen.step_artifact_cli import build_step_artifact

            build_step_artifact(repo_root=Path(raw_dir), step=step_path)
            with mock.patch(
                "cadgen._internal.step_scene_package.load_step_scene",
                side_effect=AssertionError("package miss"),
            ):
                warm = read_step(step_path)
            self.assertEqual(_face_count(raw.wrapped), _face_count(warm.wrapped))
            self.assertAlmostEqual(raw.volume, warm.volume, places=4)


if __name__ == "__main__":
    unittest.main()


class UserSiteIsNotModelCodeTest(unittest.TestCase):
    """Dependencies installed with ``pip install --user`` are third party, not model code.

    Regression for #215. ``sysconfig.get_paths()`` answers for the DEFAULT (prefix-based)
    scheme only, so it never names the per-user scheme. build123d/OCP/numpy installed with
    ``pip install --user`` — the normal layout on a machine whose system site-packages needs
    admin rights — were therefore classified as model code and evicted from ``sys.modules``
    before every build. numpy cannot survive re-import while its C extension is loaded, so
    every build died with "module 'numpy.dtypes' has no attribute 'BoolDType'", including a
    five-line Box generator.
    """

    def setUp(self) -> None:
        cad_source_hash._interpreter_roots.cache_clear()
        cad_source_hash._excluded_roots.cache_clear()
        cad_source_hash.is_first_party_source_file.cache_clear()

    tearDown = setUp

    def test_user_site_packages_is_excluded(self) -> None:
        import site

        user_site = Path(site.getusersitepackages())
        self.assertFalse(
            cad_source_hash.is_first_party_source_file(user_site / "numpy" / "__init__.py"),
            "a --user installed dependency must not be treated as model code",
        )
        self.assertFalse(
            cad_source_hash.is_first_party_source_file(
                user_site / "build123d" / "geometry.py"
            )
        )

    def test_the_user_scheme_purelib_is_excluded(self) -> None:
        # The path sysconfig itself reports for the per-user scheme, which is what the
        # default-scheme lookup was missing.
        import sysconfig

        user_paths = sysconfig.get_paths(sysconfig.get_preferred_scheme("user"))
        purelib = user_paths.get("purelib")
        self.assertTrue(purelib, "the platform must describe a per-user purelib")
        self.assertFalse(
            cad_source_hash.is_first_party_source_file(Path(purelib) / "pkg" / "mod.py")
        )

    def test_the_user_base_itself_is_not_excluded(self) -> None:
        # Deliberately narrower than the fix suggested in the issue: the user BASE holds
        # bin/ and share/ too, and excluding all of it would classify a model kept anywhere
        # beneath it as third party — dropping it from the closure and silently disabling
        # staleness detection for that model.
        import site

        user_base = Path(site.getuserbase())
        model = user_base / "projects" / "widget" / "widget.py"
        self.assertTrue(
            cad_source_hash.is_first_party_source_file(model),
            "a model under the user base must stay first party",
        )

    def test_a_model_beside_the_repo_is_still_first_party(self) -> None:
        with temporary_directory(prefix="closure-model") as root:
            model = Path(root) / "widget.py"
            model.write_text("from build123d import Box\n", encoding="utf-8")
            self.assertTrue(cad_source_hash.is_first_party_source_file(model))


class ExtensionOwningPackagesSurviveEvictionTest(unittest.TestCase):
    """A package with a loaded C extension is never evicted, whatever the install layout.

    The root lists are a denylist and will keep missing layouts (``pip install --target``,
    conda, PYTHONPATH trees). This backstop turns "wrong closure" into the worst case
    instead of "every build crashes", because a half-evicted extension package cannot be
    re-imported.
    """

    def test_numpy_is_never_evicted_even_if_misclassified(self) -> None:
        import numpy

        with mock.patch.object(
            cad_source_hash,
            "repo_local_loaded_modules",
            return_value={"numpy": Path(numpy.__file__)},
        ):
            evicted = cad_source_hash.evict_first_party_modules()

        self.assertNotIn("numpy", evicted)
        self.assertIn("numpy", sys.modules, "evicting numpy breaks every later import")

    def test_a_pure_python_module_is_still_evicted(self) -> None:
        module_name = "cadgen_test_pure_python_module"
        module = type(sys)(module_name)
        module.__file__ = "/tmp/does-not-matter/widget.py"
        sys.modules[module_name] = module
        self.addCleanup(sys.modules.pop, module_name, None)

        with mock.patch.object(
            cad_source_hash,
            "repo_local_loaded_modules",
            return_value={module_name: Path(module.__file__)},
        ):
            evicted = cad_source_hash.evict_first_party_modules()

        self.assertIn(module_name, evicted)
        self.assertNotIn(module_name, sys.modules)

    def test_extension_owners_are_detected_by_suffix_not_by_name(self) -> None:
        protected = cad_source_hash._packages_owning_loaded_extensions()
        # Whatever compiled packages this interpreter has loaded, numpy is one of them.
        import numpy  # noqa: F401

        self.assertIn("numpy", protected)
        # A stdlib pure-Python package must not be swept into the protected set.
        import json  # noqa: F401

        self.assertNotIn("json", protected)
