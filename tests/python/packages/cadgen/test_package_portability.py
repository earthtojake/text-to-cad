"""A project must survive being moved without a rebuild.

The render packages live in the user-level store keyed by DOCUMENT content, so a
project move cannot invalidate them by construction: the moved .step hashes to
the same key. What can still leak is a path — in a store descriptor, a component
blob, or the model-side sidecar — and a leaked path survives the move and then
names a directory that only ever existed somewhere else.

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

HAS_NODE = shutil.which("node") is not None

PART = """from build123d import Box


from cadgen import step
@step
def model():
    return Box(20.0, 12.0, 4.0)


if __name__ == "__main__":
    model()
"""

CHILD = """from build123d import Cylinder


from cadgen import step
@step
def model():
    return Cylinder(3.0, 20.0)


if __name__ == "__main__":
    model()
"""

# Composes the sibling child the documented way: path-load, then call its model().
ASSEMBLY = """import importlib.util
from pathlib import Path

from build123d import Box, Compound, Pos


def _load(path):
    path = Path(path).resolve()
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_child = _load(Path(__file__).resolve().parent / "parts" / "bolt.py")


from cadgen import step
@step
def model():
    plate = Box(40.0, 40.0, 6.0)
    plate.label = "plate"
    bolt = Pos(0.0, 0.0, 13.0) * _child.model()
    bolt.label = "bolt"
    return Compound(children=[plate, bolt])


if __name__ == "__main__":
    model()
"""

DRAWING = """from cadgen import build123d as bd
from cadgen import dxf


@dxf
def drawing():
    with bd.BuildSketch() as cut:
        bd.Rectangle(60, 40)
    return {"CUT": cut.sketch}


if __name__ == "__main__":
    drawing()
"""


def _model_artifacts(root: Path) -> list[Path]:
    return sorted(
        path for path in root.rglob("*")
        if path.is_file() and path.suffix in {".step", ".stp"}
    )


def package_files(root: Path) -> list[Path]:
    """Every persisted build output for the models in ``root``: the store
    packages their artifacts resolve to, plus the model-side sidecars."""
    from cadgen.catalog import render_package_dir

    out: list[Path] = []
    for artifact in _model_artifacts(root):
        sidecar = Path(f"{artifact}.step.json")
        if sidecar.is_file():
            out.append(sidecar)
        package = render_package_dir(artifact)
        if package.is_dir():
            out.extend(path for path in sorted(package.rglob("*")) if path.is_file())
    return out


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
    """Every build-output mtime: model-side files keyed root-relative, store
    package files keyed store-relative. A rebuild changes these; a move
    followed by a no-op does not. Stronger than reading a producer's own
    "current" wording, which is exactly the claim under test."""
    from cadgen._internal.cache_paths import packages_dir

    out: dict[str, int] = {}
    store = packages_dir()
    for path in package_content_files(root):
        try:
            key = f"<store>/{path.relative_to(store).as_posix()}"
        except ValueError:
            key = str(path.relative_to(root))
        out[key] = path.stat().st_mtime_ns
    return out


class PackagePortabilityTest(unittest.TestCase):
    """One built project reused by every check: every package kind in one tree."""

    @classmethod
    def setUpClass(cls) -> None:
        cls._tmp = tempfile.TemporaryDirectory(prefix="cadport-")
        cls.root = Path(cls._tmp.name) / "project"
        (cls.root / "parts").mkdir(parents=True)
        (cls.root / "parts" / "bolt.py").write_text(CHILD, encoding="utf-8")
        (cls.root / "widget.py").write_text(PART, encoding="utf-8")
        (cls.root / "rig.py").write_text(ASSEMBLY, encoding="utf-8")
        (cls.root / "sheet.py").write_text(DRAWING, encoding="utf-8")
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
        generate_step_targets([f"{root / 'widget.py'}={root / 'imported.step'}"])
        cls._noop_pass(root)

    @staticmethod
    def _noop_pass(root: Path) -> None:
        """Every producer, in the mode that should do nothing to a current package."""
        from cadgen.generation import generate_dxf_targets, generate_step_targets
        from cadgen.step_artifact_cli import build_step_artifact

        generate_step_targets([
            f"{root / 'widget.py'}={root / 'widget.step'}",
            f"{root / 'rig.py'}={root / 'rig.step'}",
        ])
        build_step_artifact(repo_root=root, step=root / "imported.step")
        if HAS_NODE:
            generate_dxf_targets([str(root / "sheet.py")])

    def _validators(self, root: Path):
        # Status subjects are ARTIFACTS (library-first: scripts are not entries).
        # A plain .dxf renders directly and is not artifact-managed, so it has
        # no status to assert here (its no-op behavior is the pass above).
        checks = ["widget.step", "rig.step", "imported.step"]
        return [(name, str(root), str(root / name)) for name in checks]

    def test_every_package_kind_was_actually_built(self) -> None:
        # Guards the tests below from passing vacuously on an empty tree: every
        # document resolves to a store package by its content hash.
        from cadgen.catalog import render_package_dir

        for name in ("widget.step", "rig.step", "imported.step"):
            with self.subTest(entry=name):
                self.assertTrue(render_package_dir(self.root / name).is_dir())

    def test_the_model_folder_is_pristine(self) -> None:
        # The store-primary exit gate: a model folder holds sources, documents
        # and sidecars — no cache directories, no lock or progress files.
        allowed = {".py", ".pyc", ".step", ".stp", ".dxf", ".json"}
        for path in sorted(self.root.rglob("*")):
            if "__pycache__" in path.parts:
                continue  # interpreter noise, not a cadgen output
            with self.subTest(path=str(path.relative_to(self.root))):
                if path.is_dir():
                    self.assertNotIn(path.name, {"__cadgen__"})
                    continue
                self.assertIn(path.suffix, allowed)
                if path.suffix == ".json":
                    self.assertTrue(path.name.endswith(".step.json"))

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
        for descriptor_path in [p for p in package_files(self.root) if p.name.endswith(".json")]:
            descriptor = json.loads(descriptor_path.read_text(encoding="utf-8"))
            recorded = [
                *([descriptor["sourcePath"]] if "sourcePath" in descriptor else []),
                *descriptor.get("sourceClosureFiles", []),
                *(entry.get("surf", "") for entry in descriptor.get("components", {}).values()),
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
        quietly grow a path field and become part of the cache. Run state lives in the
        store's locks/ tier now, keyed by model path."""
        from cadgen.catalog import artifact_path_key
        from cadgen._internal.cache_paths import locks_dir

        keys = {
            artifact_path_key(self.root / name)
            for name in ("widget.step", "rig.step", "imported.step", "sheet.py")
        }
        run_state = [
            path for path in sorted(locks_dir().rglob("*"))
            if path.is_file() and is_run_state(path)
            and any(key in path.name for key in keys)
        ]
        self.assertTrue(run_state, "no lock/status files were written at all")
        for path in run_state:
            if not path.name.endswith(".json"):
                continue
            record = json.loads(path.read_text(encoding="utf-8"))
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

        from tests.python.support.viewer_status import viewer_artifact_status

        for name, root_arg, source_arg in self._validators(moved):
            with self.subTest(entry=name):
                self.assertEqual("ready", viewer_artifact_status(source_arg, root_arg)["state"])

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
                "parts/bolt.py", _relative_to_base(base / "parts" / "bolt.py", base)
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
            dependency.write_text("X = 1\n", encoding="utf-8")
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
        from cadgen.catalog import render_package_dir
        from cadgen.generation import generate_step_targets

        step = project / "widget.step"
        if step.exists():
            shutil.rmtree(render_package_dir(step), ignore_errors=True)
            step.unlink()
        previous = Path.cwd()
        os.chdir(cwd)
        try:
            generate_step_targets([str(project / "widget.py")])
        finally:
            os.chdir(previous)
        descriptor = json.loads(
            (render_package_dir(step) / "assembly.json").read_text(encoding="utf-8")
        )
        # The descriptor is a pure function of the STEP bytes — no timestamp
        # to excuse (generatedAt rides the source sidecar now).
        self.assertNotIn("generatedAt", descriptor)
        return descriptor

    def test_the_descriptor_is_the_same_from_any_working_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cadcwd-") as temp_dir:
            root = Path(temp_dir)
            project = root / "project"
            project.mkdir()
            (project / "widget.py").write_text(PART, encoding="utf-8")

            from_inside = self._descriptor_built_from(project, project)
            from_above = self._descriptor_built_from(root, project)
            from_elsewhere = self._descriptor_built_from(Path(tempfile.gettempdir()), project)

        self.assertEqual(from_inside, from_above)
        self.assertEqual(from_inside, from_elsewhere)


if __name__ == "__main__":
    unittest.main()
