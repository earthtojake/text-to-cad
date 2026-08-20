"""A ``__cadgen__`` package must survive being moved.

The cache lives beside the source it describes, so it travels with the project: folders get
renamed, copied to another machine, archived, or vendored into another repository. Nothing
about a package's identity is its location -- currency is content hashes, components are
content-addressed, and every recorded path is relative to the model folder -- so a move
should be a no-op and a rebuild should not happen.

That is a design invariant with almost no enforcement. ONE ``relative_to_cwd()`` in a
descriptor writer, or one ``str(path.resolve())``, would bake the builder's directory into
the cache, and nothing would say so: the package still validates on the machine that wrote
it. It surfaces later, as a silent full rebuild after a move, or as a stale-artifact error
in the viewer on a colleague's checkout -- with the descriptor's own recorded path pointing
at a directory that only ever existed somewhere else.

So this asserts both halves, per package kind:

* no file in the package mentions where it was built -- checked over BYTES, because the
  component GLBs and the topology manifests inside them are not text;
* after moving and after renaming, every producer still reports the package current and the
  viewer's freshness validator still accepts it.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from tests.python.support.paths import add_repo_path

add_repo_path("packages/cadgen/src")
add_repo_path("viewer")

HAS_NODE = shutil.which("node") is not None

PART = """from build123d import Box


def gen_step():
    return Box(20.0, 12.0, 4.0)
"""

CHILD = """from build123d import Cylinder


def gen_step():
    return Cylinder(3.0, 20.0)
"""

# Composes the sibling child the documented way: path-load, then call its gen_step().
ASSEMBLY = """import importlib.util
from pathlib import Path

from build123d import Box, Compound, Pos


def _load(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_child = _load(Path(__file__).resolve().parent / "parts" / "bolt.step.py")


def gen_step():
    plate = Box(40.0, 40.0, 6.0)
    plate.label = "plate"
    bolt = Pos(0.0, 0.0, 13.0) * _child.gen_step()
    bolt.label = "bolt"
    return Compound(children=[plate, bolt])
"""

DRAWING = """import ezdxf
from ezdxf.units import MM


def gen_dxf():
    doc = ezdxf.new(setup=True)
    doc.units = MM
    msp = doc.modelspace()
    doc.layers.add("CUT")
    msp.add_lwpolyline(
        [(0, 0), (60, 0), (60, 40), (0, 40)], close=True, dxfattribs={"layer": "CUT"}
    )
    return {"document": doc}
"""

IMPLICIT = """export default {
  schema: "implicit.js/0.1.0",
  name: "orb",
  bounds: () => [[-6, -6, -6], [6, 6, 6]],
  glsl: `float sdf(vec3 p) { return length(p) - 4.0; }`
};
"""


def package_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("__cadgen__/**/*") if path.is_file())


def is_run_state(path: Path) -> bool:
    """The generation lock and the status record: this machine's view of a build in flight.

    They live in the same directory as the package but are not part of it -- the lock is a
    kernel-owned sentinel and the record is progress UI, carrying a pid and a hostname that
    mean nothing anywhere else. Every run rewrites the record, including a run that decides
    to do nothing, so they are excluded from the "nothing was rebuilt" comparison."""
    return path.name.endswith((".generation.lock", ".generation.progress.json"))


def package_content_files(root: Path) -> list[Path]:
    return [path for path in package_files(root) if not is_run_state(path)]


def mtimes(root: Path) -> dict[str, int]:
    """Every package file's mtime, keyed root-relative. A rebuild changes these; a move
    followed by a no-op does not. Stronger than reading a producer's own "current" wording,
    which is exactly the claim under test."""
    return {
        str(path.relative_to(root)): path.stat().st_mtime_ns
        for path in package_content_files(root)
    }


class PackagePortabilityTest(unittest.TestCase):
    """One built project reused by every check: five package kinds in one tree."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="cadport-")
        cls.root = Path(cls._tmp.name) / "project"
        (cls.root / "parts").mkdir(parents=True)
        (cls.root / "parts" / "bolt.step.py").write_text(CHILD)
        (cls.root / "widget.step.py").write_text(PART)
        (cls.root / "rig.step.py").write_text(ASSEMBLY)
        (cls.root / "sheet.dxf.py").write_text(DRAWING)
        (cls.root / "orb.implicit.js").write_text(IMPLICIT)
        cls._build(cls.root)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    @classmethod
    def _build(cls, root: Path) -> None:
        from cadgen.generation import generate_step_targets

        # An imported STEP: exported from the part, then given its own render package, which
        # is the one descriptor whose source is a .step file rather than a generator. Kept out
        # of the no-op pass below because an explicit export ALWAYS writes its file -- that is
        # the documented contract, not a freshness miss.
        generate_step_targets([f"{root / 'widget.step.py'}={root / 'imported.step'}"])
        cls._noop_pass(root)

    @staticmethod
    def _noop_pass(root: Path) -> None:
        """Every producer, in the mode that should do nothing to a current package."""
        from cadgen.generation import generate_dxf_targets, generate_step_targets
        from cadgen.step_artifact_cli import build_step_artifact

        generate_step_targets([str(root / "widget.step.py"), str(root / "rig.step.py")])
        build_step_artifact(repo_root=root, step=root / "imported.step")
        if HAS_NODE:
            from cadgen.implicit_artifact import build_implicit_artifact

            generate_dxf_targets([str(root / "sheet.dxf.py")])
            # The DEFAULT bake resolution on purpose: resolution is part of the bake
            # identity, so a package baked at another one is legitimately stale to the
            # viewer, which asks with the defaults -- and the viewer agreeing is half of
            # what this file is checking.
            build_implicit_artifact(repo_root=root, source_path=root / "orb.implicit.js")

    def _validators(self, root: Path):
        from server_py.artifact import (
            validate_dxf_freshness,
            validate_implicit_freshness,
            validate_step_freshness,
        )

        checks = [
            ("widget.step.py", validate_step_freshness),
            ("rig.step.py", validate_step_freshness),
            ("imported.step", validate_step_freshness),
        ]
        if HAS_NODE:
            checks += [
                ("sheet.dxf.py", validate_dxf_freshness),
                ("orb.implicit.js", validate_implicit_freshness),
            ]
        return [(name, validate, str(root), str(root / name)) for name, validate in checks]

    def test_every_package_kind_was_actually_built(self) -> None:
        # Guards the tests below from passing vacuously on an empty tree.
        expected = {"widget.step.py", "rig.step.py", "imported.step"}
        if HAS_NODE:
            expected |= {"sheet.dxf.py", "orb.implicit.js"}
        self.assertEqual(
            expected,
            {path.name for path in (self.root / "__cadgen__" / "models").iterdir() if path.is_dir()},
        )

    def test_no_package_file_mentions_the_directory_it_was_built_in(self) -> None:
        # Over bytes, not text: the component GLBs carry a JSON chunk with the topology
        # manifest in it, which is where a leaked path would be least visible.
        needle = str(self.root).encode()
        offenders = [
            str(path.relative_to(self.root))
            for path in package_files(self.root)
            if needle in path.read_bytes()
        ]
        self.assertEqual([], offenders, "a package file records its own build location")

    def test_no_package_file_mentions_the_builder_or_its_interpreter(self) -> None:
        # A home directory or a .venv path in a descriptor is the same defect wearing a
        # different hat: it survives a move and then names a directory that does not exist.
        needles = {
            "home": str(Path.home()),
            "interpreter prefix": sys.prefix,
            "cwd": os.getcwd(),
        }
        for label, needle in needles.items():
            if not needle or needle == os.sep:
                continue
            with self.subTest(needle=label):
                offenders = [
                    str(path.relative_to(self.root))
                    for path in package_files(self.root)
                    if needle.encode() in path.read_bytes()
                ]
                self.assertEqual([], offenders, f"a package file records the builder's {label}")

    def test_recorded_paths_are_relative_and_stay_inside_the_project(self) -> None:
        for descriptor_path in sorted(self.root.rglob("__cadgen__/models/*/*.json")):
            descriptor = json.loads(descriptor_path.read_text())
            recorded = [
                *([descriptor["sourcePath"]] if "sourcePath" in descriptor else []),
                *([descriptor["stepPath"]] if "stepPath" in descriptor else []),
                *([descriptor["glb"]] if "glb" in descriptor else []),
                *descriptor.get("sourceClosureFiles", []),
                *(entry.get("glb", "") for entry in descriptor.get("components", {}).values()),
            ]
            for value in recorded:
                with self.subTest(descriptor=descriptor_path.parent.name, value=value):
                    self.assertFalse(
                        Path(value).is_absolute(),
                        "a descriptor records an absolute path",
                    )
                    self.assertNotIn(
                        "\\",
                        value,
                        "a recorded path must be posix so it survives crossing platforms",
                    )

    def test_the_only_machine_specific_files_are_the_transient_run_state(self) -> None:
        """The status record names a pid and a host, and that is allowed -- it describes a
        RUN, not the artifact. What is not allowed is any of it reaching the package's own
        content, which is what the rest of this class checks. Pinned so the record cannot
        quietly grow a path field and become part of the cache."""
        run_state = [path for path in package_files(self.root) if is_run_state(path)]
        self.assertTrue(run_state, "no lock/status files were written at all")
        for path in run_state:
            if not path.name.endswith(".json"):
                continue
            record = json.loads(path.read_text())
            with self.subTest(record=path.name):
                self.assertEqual({"pid", "host"}, {"pid", "host"} & set(record))
                for key, value in record.items():
                    if isinstance(value, str):
                        self.assertNotIn(os.sep, value, f"{key} in the status record looks like a path")

    def test_moving_the_project_rebuilds_nothing(self) -> None:
        moved = self.root.parent / "moved-elsewhere" / "project"
        moved.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root, moved)
        self.addCleanup(shutil.rmtree, moved.parent, True)

        before = mtimes(moved)
        self._noop_pass(moved)
        self.assertEqual(before, mtimes(moved), "moving the project rebuilt its packages")

        for name, validate, root_arg, source_arg in self._validators(moved):
            with self.subTest(entry=name):
                self.assertEqual((True, None), validate(root_arg, source_arg))

    def test_renaming_the_project_folder_rebuilds_nothing(self) -> None:
        # The folder name is part of every path a descriptor could have recorded, so this is
        # a different question from moving the folder somewhere else.
        renamed = self.root.parent / "renamed" / "a-different-name"
        renamed.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root, renamed)
        self.addCleanup(shutil.rmtree, renamed.parent, True)

        before = mtimes(renamed)
        self._noop_pass(renamed)
        self.assertEqual(before, mtimes(renamed), "renaming the project rebuilt its packages")

    def test_nesting_the_project_deeper_rebuilds_nothing(self) -> None:
        nested = self.root.parent / "deeper" / "one" / "two" / "project"
        nested.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.root, nested)
        self.addCleanup(shutil.rmtree, self.root.parent / "deeper", True)

        before = mtimes(nested)
        self._noop_pass(nested)
        self.assertEqual(before, mtimes(nested), "nesting the project rebuilt its packages")


class RecordedPathHelpersTest(unittest.TestCase):
    """The two functions every persisted path goes through."""

    def test_a_sibling_and_a_parent_dependency_stay_relative(self) -> None:
        from cadgen._internal.source_hash import _relative_to_base

        with tempfile.TemporaryDirectory(prefix="cadrel-") as temp_dir:
            root = Path(temp_dir)
            (root / "models" / "parts").mkdir(parents=True)
            (root / "shared").mkdir()
            base = root / "models"
            self.assertEqual(
                "parts/bolt.step.py", _relative_to_base(base / "parts" / "bolt.step.py", base)
            )
            self.assertEqual(
                "../shared/dims.py", _relative_to_base(root / "shared" / "dims.py", base)
            )

    def test_a_dependency_on_another_volume_is_recorded_rather_than_crashing(self) -> None:
        # os.path.relpath RAISES across Windows drives -- a model on D: importing a helper from
        # C:. There is no relative path to record, and the build must not die over it.
        from cadgen import render
        from cadgen._internal import source_hash

        def _across_drives(*args, **kwargs):
            raise ValueError("path is on mount 'C:', start on mount 'D:'")

        with tempfile.TemporaryDirectory(prefix="cadrel-") as temp_dir:
            root = Path(temp_dir)
            dependency = root / "elsewhere.py"
            dependency.write_text("X = 1\n")
            with unittest.mock.patch.object(os.path, "relpath", _across_drives):
                self.assertEqual(
                    dependency.resolve().as_posix(),
                    source_hash._relative_to_base(dependency, root),
                )
                self.assertEqual(
                    dependency.resolve().as_posix(),
                    render.relative_to_directory(dependency, root),
                )

    def test_the_source_identity_carries_no_path_at_all(self) -> None:
        # The field that used to be here was cwd-relative, or absolute when the model was not
        # under the cwd, and was read by nothing -- one attribute away from values that ARE
        # persisted. Its absence is the point.
        from cadgen._internal.source_hash import PythonSourceHash

        self.assertEqual(("source_hash",), tuple(PythonSourceHash.__dataclass_fields__))


class DescriptorIsIndependentOfTheWorkingDirectoryTest(unittest.TestCase):
    """Where the COMMAND ran from must not reach the descriptor either.

    The same defect as an absolute path, one step removed: a cwd-relative path recorded in a
    cache makes the cache's contents depend on the shell that produced it, so two agents
    building the same model from different directories disagree about it.
    """

    def _descriptor_built_from(self, cwd: Path, project: Path) -> dict:
        from cadgen.generation import generate_step_targets

        package = project / "__cadgen__"
        shutil.rmtree(package, ignore_errors=True)
        previous = Path.cwd()
        os.chdir(cwd)
        try:
            generate_step_targets([str(project / "widget.step.py")])
        finally:
            os.chdir(previous)
        descriptor = json.loads(
            (package / "models" / "widget.step.py" / "assembly.json").read_text()
        )
        # The build timestamp is the one field that is allowed to differ.
        descriptor.pop("generatedAt", None)
        return descriptor

    def test_the_descriptor_is_the_same_from_any_working_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadcwd-") as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "widget.step.py").write_text(PART)

            from_inside = self._descriptor_built_from(project, project)
            from_above = self._descriptor_built_from(root, project)
            from_elsewhere = self._descriptor_built_from(Path(tempfile.gettempdir()), project)

        self.assertEqual(from_inside, from_above)
        self.assertEqual(from_inside, from_elsewhere)


if __name__ == "__main__":
    unittest.main()
