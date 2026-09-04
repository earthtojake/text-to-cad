"""The dxf skill's documentation is executed, not just proofread.

A skill is consumed by an agent that copies what it reads. Documentation that
has drifted from the contract is therefore not a cosmetic problem: it is a
generator of broken drawings, and the drift is invisible to every other test in
the suite. So the code blocks in `skills/dxf/SKILL.md` and
`skills/dxf/references/generator-templates.md` are extracted and RUN here, and
the CLI forms those files document are run too.

Blocks fall into two kinds and are checked accordingly:

* **complete models** — every import present, no ``<placeholder>`` — are written
  to a temp project and built, and must produce a `.dxf` the drawing checks pass.
* **fragments and templates** — a bracket's multi-plane selection, a workflow
  skeleton with TODO markers — cannot run, so they are parsed and required to
  declare a ``@dxf`` entry. Syntax and contract shape, which is what a reader
  copies out of them.

Also pinned here: the retired-contract teaching error points at `SKILL.md`, so
`SKILL.md` must teach the contract that replaced it and not the one it removed.
"""

from __future__ import annotations

import ast
import concurrent.futures
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from tests.python.support.paths import add_repo_path, repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")

SKILL = repo_path("skills/dxf/SKILL.md")
TEMPLATES = repo_path("skills/dxf/references/generator-templates.md")

_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.S)
# A model the reader could paste somewhere else needs this to exist first.
_BRACKET_MODEL = '''from cadgen import build123d as bd
from cadgen import step


THICKNESS = 3.0


@step
def bracket():
    with bd.BuildSketch() as profile:
        bd.Rectangle(40, 25)
        with bd.Locations((-14, 0), (14, 0)):
            bd.Circle(2.5, mode=bd.Mode.SUBTRACT)
    return bd.extrude(profile.sketch, amount=THICKNESS)


if __name__ == "__main__":
    bracket()
'''


# The imported-STEP workflow reads a `.step` this project does not generate, so
# the documented example needs a real one to read -- `read_step` parses it. Built
# rather than committed, so the fixture cannot drift from the writer that makes
# them, and built ONCE for the module: it is the same file for every project.
_VENDOR_MODEL = '''from cadgen import build123d as bd
from cadgen import step


THICKNESS = 3.0


@step
def vendor_panel():
    with bd.BuildSketch() as profile:
        bd.Rectangle(60, 40)
        bd.Circle(4, mode=bd.Mode.SUBTRACT)
    return bd.extrude(profile.sketch, amount=THICKNESS)


if __name__ == "__main__":
    vendor_panel()
'''

_VENDOR_STEP: Path | None = None


def tearDownModule() -> None:
    global _VENDOR_STEP
    if _VENDOR_STEP is not None:
        shutil.rmtree(_VENDOR_STEP.parent, ignore_errors=True)
        _VENDOR_STEP = None


def _vendor_step() -> Path:
    global _VENDOR_STEP
    if _VENDOR_STEP is None or not _VENDOR_STEP.is_file():
        workspace = Path(tempfile.mkdtemp(prefix="dxf-docs-vendor-")).resolve()
        script = workspace / "vendor_panel.py"
        script.write_text(_VENDOR_MODEL, encoding="utf-8")
        subprocess.run(
            [sys.executable, script.name],
            cwd=str(workspace),
            env={
                **os.environ,
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_CACHE_DIR": str(workspace / "store"),
                "PYTHONPATH": str(CADGEN_SRC),
            },
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        _VENDOR_STEP = workspace / "vendor_panel.step"
    return _VENDOR_STEP


def _python_blocks(path: Path) -> list[str]:
    # Dedented: a block nested inside a numbered list is indented in the source,
    # and a reader copying it out un-indents it without thinking about it.
    return [textwrap.dedent(block) for block in _PYTHON_BLOCK.findall(path.read_text(encoding="utf-8"))]


_PLACEHOLDER = re.compile(r"<([A-Za-z_][A-Za-z0-9_]*)>")


def _fill_placeholders(source: str) -> str:
    """`<name>` markers become a valid identifier so a template still PARSES.

    Substituting rather than skipping: the structure a reader copies out of a
    template is exactly what should be checked, and `<name>` is the only thing
    stopping it from being Python.
    """
    return _PLACEHOLDER.sub(lambda match: f"{match.group(1)}_here", source)


def _declares_a_dxf_model(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.FunctionDef)
        and any(
            (isinstance(d, ast.Name) and d.id == "dxf")
            or (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "dxf")
            or (isinstance(d, ast.Attribute) and d.attr == "dxf")
            or (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute) and d.func.attr == "dxf")
            for d in node.decorator_list
        )
        for node in ast.walk(tree)
    )


def _is_runnable_model(source: str) -> bool:
    if "<" in source and ">" in source:  # a template's <name> markers
        return False
    if "@dxf" not in source or "from cadgen import" not in source:
        return False
    return "def " in source


class _DrawingHarness(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="dxf-docs-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        (self.project / "bracket.py").write_text(_BRACKET_MODEL, encoding="utf-8")
        # Where the docs say a source STEP lives: an input path that is not any
        # model's output path, which is the whole of the self-read rule.
        imported = self.project / "imported"
        imported.mkdir()
        shutil.copyfile(_vendor_step(), imported / "vendor_panel.step")
        self.environment = dict(os.environ)
        self.environment.update(
            {
                # A warm worker would serve another checkout's code.
                "CADGEN_DAEMON": "0",
                "CADGEN_COMPONENT_WORKERS": "1",
                "CADGEN_CACHE_DIR": str(self.project / "store"),
                "PYTHONPATH": str(CADGEN_SRC),
            }
        )

    def run_drawing(self, *argv: str, expect_success: bool = True) -> subprocess.CompletedProcess:
        completed = subprocess.run(
            [sys.executable, *argv],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if expect_success:
            self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
        return completed


class DocumentedModelsBuild(_DrawingHarness):
    def test_every_complete_documented_model_builds(self) -> None:
        sources = [
            (path.name, index, block)
            for path in (SKILL, TEMPLATES)
            for index, block in enumerate(_python_blocks(path))
            if _is_runnable_model(block)
        ]
        self.assertGreaterEqual(len(sources), 3, "the docs should carry runnable examples")
        models = []
        for name, index, block in sources:
            model = self.project / f"documented_{name.replace('.', '_')}_{index}.py"
            model.write_text(block, encoding="utf-8")
            models.append((name, index, model))
        # The documented drawings are independent, so they build side by side, each in
        # its own process.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda entry: self.run_drawing(entry[2].name), models))
        for name, index, model in models:
            with self.subTest(document=name, block=index):
                drawing = model.with_suffix(".dxf")
                self.assertTrue(drawing.is_file(), f"{model.name} wrote no drawing")
                self.assertGreater(drawing.stat().st_size, 0)

    def test_templates_and_fragments_parse_and_declare_a_dxf_entry(self) -> None:
        blocks = [
            block
            for block in _python_blocks(TEMPLATES)
            if "@dxf" in block and not _is_runnable_model(block)
        ]
        self.assertGreaterEqual(len(blocks), 2, "the templates should carry skeletons too")
        for index, block in enumerate(blocks):
            with self.subTest(block=index):
                filled = _fill_placeholders(block)
                ast.parse(filled)  # a template a reader copies must at least be Python
                self.assertTrue(_declares_a_dxf_model(filled))


class DocumentedCommandForms(_DrawingHarness):
    """Each command form SKILL.md documents, actually run."""

    DRAWING = textwrap.dedent(
        """\
        from cadgen import build123d as bd
        from cadgen import dxf


        HOLE_D = 4.5


        @dxf
        def gasket():
            with bd.BuildSketch() as cut:
                bd.Rectangle(60, 40)
                bd.Circle(HOLE_D / 2, mode=bd.Mode.SUBTRACT)
            return cut.sketch


        if __name__ == "__main__":
            gasket()
        """
    )

    def setUp(self) -> None:
        super().setUp()
        (self.project / "gasket.py").write_text(self.DRAWING, encoding="utf-8")
        (self.project / "panel.py").write_text(
            self.DRAWING.replace("def gasket", "def panel"), encoding="utf-8"
        )

    def test_a_bare_run_writes_the_sibling(self) -> None:
        self.run_drawing("gasket.py")
        self.assertTrue((self.project / "gasket.dxf").is_file())

    def test_an_unchanged_source_is_a_no_op(self) -> None:
        self.run_drawing("gasket.py")
        before = (self.project / "gasket.dxf").stat().st_mtime_ns
        self.run_drawing("gasket.py")
        self.assertEqual(before, (self.project / "gasket.dxf").stat().st_mtime_ns)

    def test_force_rebuilds_to_identical_bytes(self) -> None:
        self.run_drawing("gasket.py")
        first = (self.project / "gasket.dxf").read_bytes()
        self.run_drawing("gasket.py", "--force")
        self.assertEqual(first, (self.project / "gasket.dxf").read_bytes())


    def test_there_is_no_dxf_build_door(self) -> None:
        """A drawing has no derived state a door must materialize — the viewer
        parses the file directly and snapshot meshes it on demand — so `dxf
        build` is simply not a command, and the dispatcher says so with the
        command list."""
        completed = subprocess.run(
            [sys.executable, "-m", "cadgen.cli", "dxf", "build", "gasket.py"],
            cwd=str(self.project), env=self.environment, capture_output=True, text=True, timeout=600,
        )
        self.assertEqual(2, completed.returncode)
        self.assertIn("unknown command", completed.stderr)
        self.assertIn("dxf snapshot", completed.stderr)

    def test_no_undocumented_or_missing_flags(self) -> None:
        """SKILL.md's flag list is what the parser accepts, exactly.

        Caught the drift this test was written for: the skill still advertised
        `--validate` and `SOURCE.py=OUTPUT.dxf` pairs, both of which belonged to
        the retired `dxf gen` CLI and had been failing with argparse's usage
        message since generation moved into the decorator.
        """
        usage = self.run_drawing("gasket.py", "--help").stdout
        documented = set(re.findall(r"`(--[a-z-]+)", SKILL.read_text(encoding="utf-8")))
        model_flags = {flag for flag in documented if flag in {"--force", "--verbose", "--json"}}
        for flag in model_flags:
            self.assertIn(flag, usage, f"SKILL.md documents {flag}, the parser does not accept it")
        for retired in ("--validate",):
            self.assertNotIn(retired, usage)
            self.assertNotIn(f"`{retired}`", SKILL.read_text(encoding="utf-8"))

    def test_post_hoc_validation_runs_the_documented_way(self) -> None:
        self.run_drawing("gasket.py")
        completed = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys\n"
                "from cadgen.drawing_checks import validate_dxf_file\n"
                "print([f.render() for f in validate_dxf_file(sys.argv[1])])",
                str(self.project / "gasket.dxf"),
            ],
            cwd=str(self.project),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=600,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "[]", "a generated drawing must validate clean")

    def test_an_ezdxf_return_fails_the_current_return_contract(self) -> None:
        (self.project / "legacy.py").write_text(
            textwrap.dedent(
                """\
                import ezdxf

                from cadgen import dxf


                @dxf
                def legacy():
                    document = ezdxf.new()
                    document.modelspace().add_circle((0, 0), 5)
                    return {"document": document}


                if __name__ == "__main__":
                    legacy()
                """
            ),
            encoding="utf-8",
        )
        completed = self.run_drawing("legacy.py", expect_success=False)
        self.assertNotEqual(completed.returncode, 0)
        output = completed.stdout + completed.stderr
        # Ordinary validation of the CURRENT contract — @dxf returns build123d
        # 2D geometry — with no recognition of what the value used to mean.
        self.assertIn("build123d geometry", output)
        self.assertNotIn("removed", output)
        self.assertFalse((self.project / "legacy.dxf").exists())


class DocumentationTeachesTheNewContract(unittest.TestCase):
    def test_the_skill_teaches_the_current_return_contract(self) -> None:
        """The teaching error sends authors HERE, so this file has to answer."""
        text = SKILL.read_text(encoding="utf-8")
        self.assertIn("returns build123d 2D geometry", text)
        self.assertIn("read_step", text)
        self.assertNotIn('{"document"', text)
        self.assertNotIn("ezdxf.new(", text)

    def test_the_templates_teach_the_current_return_contract(self) -> None:
        text = TEMPLATES.read_text(encoding="utf-8")
        self.assertNotIn('{"document"', text)
        self.assertNotIn("ezdxf.new(", text)
        self.assertNotIn("union_projected_faces", text)
        self.assertNotIn("add_shapely_geometry", text)

    def test_the_skill_teaches_the_exact_snapshot_output_rule(self) -> None:
        """The snapshot section's whole job here is the output contract.

        A drawing review is render -> Read -> edit -> render, and the reader needs
        to know that the second render replaces the file the first one wrote. The
        section used to have to teach the opposite (the written name was not the
        name passed), so this pins the replacement rather than leaving the section
        free to drift back into teaching what to KNOW instead of what to do.
        """
        text = SKILL.read_text(encoding="utf-8")
        snapshot_section = text[text.index("cadgen dxf snapshot` renders") :]
        self.assertIn("written exactly as given", snapshot_section)
        self.assertIn("current working directory", snapshot_section)
        self.assertIn("missing file", snapshot_section)
        # The generate-a-name case is the only surviving read-the-printed-path case.
        self.assertIn("`tmp/` as OUT", snapshot_section)

    def test_documented_snapshot_forms_name_a_file(self) -> None:
        """`cadgen dxf snapshot TARGET OUT` — the OUT in every documented form is
        a file the reader can open by that name afterwards.

        Read off the command's OWN parser rather than by counting words, so a
        form written against a retired spelling fails here instead of quietly
        matching nothing and passing."""
        from cadgen.cli.dxf_snapshot import build_parser

        forms = [
            line.strip()
            for line in SKILL.read_text(encoding="utf-8").splitlines()
            if line.strip().startswith("cadgen dxf snapshot ")
            and "--help" not in line
        ]
        self.assertGreaterEqual(len(forms), 2)
        for form in forms:
            with self.subTest(form=form):
                rest = form.split("#")[0].split()[3:]
                out = build_parser().parse_args(rest).out
                self.assertIsNotNone(out, f"`{form}` names no OUT")
                value = str(out)
                self.assertTrue(Path(value).suffix, f"OUT `{value}` names no file")
                self.assertFalse(value.endswith(("/", "\\")))
