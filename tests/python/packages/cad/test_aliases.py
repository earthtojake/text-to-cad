"""The library's earlier spellings: each the SAME object as its new path, saying so once.

The table is pinned here whole (``cad._internal.aliases``): an alias added or dropped is a change to
the library's public imports, made on purpose. Each warns with ``CadDeprecationWarning``, a
``FutureWarning`` so Python shows it by default, once per name per process, naming the new path at
the line of the program that spelled the old one -- which is what the person or agent who ran a
model reads, since a model's own process imports its script before any build.
"""

from __future__ import annotations

import importlib
import subprocess
import sys
import tempfile
import unittest
import warnings
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cad/src")

import cad  # noqa: E402
from cad._internal import aliases  # noqa: E402

NAMES = {
    "cad": {"read_step": "cad.step.read", "read_xbf": "cad.xbf.read", "read_mesh": "cad.stl.read",
            "memo": "cad.build123d.memo", "paint": "cad.build123d.paint", "export": "cad.engine.api.export",
            "snapshot": "cad.engine.api.snapshot", "inspect": "cad.engine.api.inspect"},
    "cad.results": {"ValidationResult": "cad.results._ValidationResult", "ValidationIssue": "cad.results._ValidationIssue"},
}
MODULES = {
    "cad.ap242": "cad.build123d", "cad.gltf": "cad.build123d", "cad.geometry": "cad.build123d._geometry",
    "cad.flatten": "cad.build123d._flatten", "cad.findings": "cad._internal.findings",
    "cad.xml_common": "cad._internal.xml_common", "cad.check_fonts": "cad._internal.check_fonts",
    "cad.urdf_source": "cad.urdf._source", "cad.sdf_source": "cad.sdf._source",
    "cad.sdf_validation": "cad.sdf._validation", "cad.sdf_external": "cad.sdf._external",
    "cad.srdf_source": "cad.srdf._source", "cad.srdf_validation": "cad.srdf._validation",
}


def _new(path: str):
    module, _, name = path.rpartition(".")
    return getattr(importlib.import_module(module), name)


class TheAliases(unittest.TestCase):
    def test_the_table_is_pinned(self) -> None:
        self.assertEqual(NAMES, aliases.NAME_ALIASES)
        self.assertEqual(MODULES, aliases.MODULE_ALIASES)
        self.assertTrue(issubclass(cad.CadDeprecationWarning, FutureWarning))

    def test_each_alias_is_the_object_its_new_path_names_and_is_in_no_all(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", cad.CadDeprecationWarning)
            for owner, names in NAMES.items():
                module = importlib.import_module(owner)
                for old, new in names.items():
                    with self.subTest(alias=f"{owner}.{old}"):
                        self.assertIs(getattr(module, old), _new(new))
                        self.assertNotIn(old, getattr(module, "__all__", ()))
            for old, new in MODULES.items():
                with self.subTest(alias=old):
                    self.assertIs(importlib.import_module(old), importlib.import_module(new))
                    self.assertEqual(new, importlib.import_module(new).__spec__.name, "the module keeps its own spec")

    def test_an_alias_warns_once_per_process_naming_the_new_path_at_the_callers_line(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "old.py"
            script.write_text("from cad import read_step\nimport cad\ncad.read_step\ncad.export\n"
                              "from cad.ap242 import mechanism_state\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120)
            program = subprocess.run([sys.executable, "-P", "-m", "cad._internal.program", str(script)],
                                     capture_output=True, text=True, timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        for said in (proc.stderr, program.stderr):
            lines = [line for line in said.splitlines() if "CadDeprecationWarning" in line]
            self.assertEqual([f"{script}:1: CadDeprecationWarning: cad.read_step is deprecated; use cad.step.read",
                              f"{script}:4: CadDeprecationWarning: cad.export is deprecated; use cad.model.export (a file's: "
                              "cad.<document_type>.export, cad.step.export, ...)",
                              f"{script}:5: CadDeprecationWarning: cad.ap242 is deprecated; use cad.build123d"], lines)

    def test_what_another_process_said_is_not_said_again_and_a_file_in_the_working_folder_is_named_relative(self) -> None:
        # A worker importing a script its program imported already ignores what that import says (cad.engine.build),
        # and each counts as said: once a run. What is said names the file relative to the working folder.
        with tempfile.TemporaryDirectory() as folder:
            script = Path(folder) / "arm.py"
            script.write_text("import cad, warnings\nwith warnings.catch_warnings():\n"
                              "    warnings.filterwarnings('ignore', category=FutureWarning)\n"
                              "    cad.read_step\ncad.read_step\ncad.memo\n", encoding="utf-8")
            proc = subprocess.run([sys.executable, str(script)], capture_output=True, text=True, timeout=120, cwd=folder)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertEqual(["arm.py:6: CadDeprecationWarning: cad.memo is deprecated; use cad.build123d.memo"],
                         [line for line in proc.stderr.splitlines() if "CadDeprecationWarning" in line])

    def test_the_old_result_types_take_their_0_10_call_shapes(self) -> None:
        from cad import results

        with warnings.catch_warnings(record=True) as said:
            warnings.simplefilter("always")
            ValidationIssue, ValidationResult = results.ValidationIssue, results.ValidationResult
        self.assertTrue(any(issubclass(item.category, cad.CadDeprecationWarning) for item in said) or
                        "cad.results.ValidationIssue" in aliases._WARNED)
        issue = ValidationIssue("error", "a joint has no parent", "/robot/joint[1]", "missing_parent", "name one")
        self.assertIsInstance(issue, results.CheckFinding)
        self.assertEqual(("error", "a joint has no parent", "/robot/joint[1]", "missing_parent", "name one"),
                         (issue.severity, issue.message, issue.element, issue.code, issue.hint))
        self.assertEqual("/robot/joint[1]", issue.location)
        keyword = ValidationIssue(severity="warning", message="m", element="e", code="c")
        self.assertEqual(("warning", "m", "e", "c", None), (keyword.severity, keyword.message, keyword.element,
                                                            keyword.code, keyword.hint))
        result = ValidationResult(False, Path("robot.urdf"), issues=(issue,), summary="")
        self.assertIsInstance(result, results.CheckResult)
        self.assertEqual(((issue,), (issue,), False), (result.issues, result.findings, result.ok))
        self.assertEqual(ValidationResult(True, Path("r.urdf")).issues, ())
        self.assertEqual(issue.human_line(), "error: missing_parent at /robot/joint[1]: a joint has no parent Hint: name one")

    def test_every_module_alias_answers_every_name_its_0_10_module_exported(self) -> None:
        # What each 0.10 module exported, beyond its private names: each resolves through its alias.
        exported = {
            "cad.ap242": ("configuration_sequence", "gear_pair", "mechanism_state", "posed", "rack_and_pinion_pair",
                          "screw_pair"),
            "cad.gltf": ("animation",),
            "cad.geometry": ("GeometryError", "GeometryIssue", "ClosestPoints", "MassProperties", "Matrix3",
                             "closest_points", "overlap_volume", "is_sound", "topology_errors", "boundary_edges",
                             "self_intersections", "mass_properties"),
            "cad.flatten": ("axis_value", "snap", "planar_faces", "flatten_face", "flatten_faces", "union_faces",
                            "offset_profile", "flat_pattern"),
        }
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", cad.CadDeprecationWarning)
            for old, names in exported.items():
                module = importlib.import_module(old)
                for name in names:
                    with self.subTest(name=f"{old}.{name}"):
                        self.assertTrue(hasattr(module, name))
            self.assertIs(importlib.import_module("cad.geometry").Matrix3,
                          importlib.import_module("cad.build123d._geometry").Matrix3, "a name cad.build123d does not list")

    def test_a_module_alias_still_runs_as_a_program(self) -> None:
        proc = subprocess.run([sys.executable, "-m", "cad.check_fonts", "--help"], capture_output=True, text=True,
                              timeout=120)
        self.assertEqual(0, proc.returncode, proc.stderr)
        self.assertIn("cad.check_fonts is deprecated", proc.stderr)


if __name__ == "__main__":
    unittest.main()
