"""The cad skill's documentation is executed, not just proofread.

A skill is consumed by an agent that copies what it reads, so a code block that
has drifted from the model contract is a generator of broken models, and the
drift is invisible to every other test. The complete model scripts in
`skills/cad/SKILL.md`, `references/step-generation.md` and
`references/supported-exports.md` are therefore extracted and BUILT here, cold
(`CADGEN_DAEMON=0`, transient workers), in a throwaway project with a private
store, and every output their decorators declare must exist afterwards.

Blocks fall into two kinds:

* **complete models** — every import present, a decorated function, a
  `__main__` call, no `<placeholder>` and no elided `...` body — are written to
  the project and run; a second run must be the no-op the docs promise.
* **fragments** (`...` bodies, bare decorator stacks, `<name>` templates) are
  parsed only: what a reader copies out of them must at least be Python.

A block whose first line is `# src/<path>.py` is written at that path (the
mirrored-pair example needs its `lib/` factory in place before either hand
builds); every other block lands in `src/` under a generated name. The one
composed example (`link_arm`) needs its child, and the wrapped-import example
needs a vendor STEP under `STEP/imported/`; both fixtures are provided here.
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

DOCUMENTS = (
    repo_path("skills/cad/SKILL.md"),
    repo_path("skills/cad/references/step-generation.md"),
    repo_path("skills/cad/references/supported-exports.md"),
)

_PYTHON_BLOCK = re.compile(r"```python\n(.*?)```", re.S)
_PLACEHOLDER = re.compile(r"<[A-Za-z_][A-Za-z0-9_]*>")
_PATH_HEADER = re.compile(r"\A#\s*(src/[\w/]+\.py)\b")
_OUT = re.compile(r'out="([^"]+)"')

# The child the composed example (`link_arm`) calls.
_LINK_PIN = '''from cadgen import build123d as bd
from cadgen import step


@step(out="../STEP/link_pin.step")
def link_pin():
    return bd.Cylinder(2.0, 10.0)


if __name__ == "__main__":
    link_pin()
'''

# The vendor document the wrapped-import example reads. Built rather than
# committed so the fixture cannot drift from the writer that makes it.
_VENDOR_MODEL = '''from cadgen import build123d as bd
from cadgen import step


@step
def sg90_servo():
    return bd.Box(23.0, 12.0, 22.0)


if __name__ == "__main__":
    sg90_servo()
'''

_VENDOR_STEP: Path | None = None


def tearDownModule() -> None:
    global _VENDOR_STEP
    if _VENDOR_STEP is not None:
        shutil.rmtree(_VENDOR_STEP.parent, ignore_errors=True)
        _VENDOR_STEP = None


def _environment(store: Path) -> dict[str, str]:
    return {
        **os.environ,
        # A warm worker would serve another checkout's code.
        "CADGEN_DAEMON": "0",
        "CADGEN_COMPONENT_WORKERS": "1",
        "CADGEN_CACHE_DIR": str(store),
        "PYTHONPATH": str(CADGEN_SRC),
    }


def _vendor_step() -> Path:
    global _VENDOR_STEP
    if _VENDOR_STEP is None or not _VENDOR_STEP.is_file():
        workspace = Path(tempfile.mkdtemp(prefix="cad-docs-vendor-")).resolve()
        script = workspace / "sg90_servo.py"
        script.write_text(_VENDOR_MODEL, encoding="utf-8")
        subprocess.run(
            [sys.executable, script.name],
            cwd=str(workspace),
            env=_environment(workspace / "store"),
            check=True,
            capture_output=True,
            text=True,
            timeout=600,
        )
        _VENDOR_STEP = workspace / "sg90_servo.step"
    return _VENDOR_STEP


def _python_blocks(path: Path) -> list[str]:
    # Dedented: a block nested inside a list is indented in the source, and a
    # reader copying it out un-indents it without thinking about it.
    return [textwrap.dedent(block) for block in _PYTHON_BLOCK.findall(path.read_text(encoding="utf-8"))]


def _is_complete_model(source: str) -> bool:
    if _PLACEHOLDER.search(source):
        return False
    if any(line.strip() == "..." for line in source.splitlines()):
        return False
    if "from cadgen import" not in source or "def " not in source:
        return False
    return '__name__ == "__main__"' in source


def _declares_a_model(source: str) -> bool:
    tree = ast.parse(source)
    decorators = {"step", "stl", "glb", "threemf", "dxf"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for d in node.decorator_list:
            target = d.func if isinstance(d, ast.Call) else d
            name = target.id if isinstance(target, ast.Name) else getattr(target, "attr", "")
            if name in decorators:
                return True
    return False


class _Blocks:
    """Every python block in the documents, with where it should live."""

    def __init__(self) -> None:
        self.models: list[tuple[str, str, str]] = []  # (document, relative path, source)
        self.libs: list[tuple[str, str]] = []  # (relative path, source)
        self.fragments: list[tuple[str, str]] = []  # (document, source)
        for document in DOCUMENTS:
            for index, block in enumerate(_python_blocks(document)):
                header = _PATH_HEADER.match(block)
                if header and not _declares_a_model(block):
                    self.libs.append((header.group(1), block))
                    continue
                if not _is_complete_model(block):
                    self.fragments.append((document.name, block))
                    continue
                relative = header.group(1) if header else f"src/documented_{document.stem.replace('-', '_')}_{index}.py"
                self.models.append((document.name, relative, block))


class DocumentedModelsBuild(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory(prefix="cad-docs-")
        self.addCleanup(self._tmp.cleanup)
        self.project = Path(self._tmp.name).resolve()
        self.src = self.project / "src"
        (self.src / "lib").mkdir(parents=True)
        (self.src / "link_pin.py").write_text(_LINK_PIN, encoding="utf-8")
        imported = self.project / "STEP" / "imported"
        imported.mkdir(parents=True)
        shutil.copyfile(_vendor_step(), imported / "sg90_servo.step")
        self.environment = _environment(self.project / "store")

    def run_script(self, relative: str) -> subprocess.CompletedProcess:
        script = self.project / relative
        completed = subprocess.run(
            [sys.executable, script.name],
            cwd=str(script.parent),
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=900,
        )
        self.assertEqual(completed.returncode, 0, f"{relative} failed:\n{completed.stdout}\n{completed.stderr}")
        return completed

    def test_every_complete_documented_model_builds_and_then_no_ops(self) -> None:
        blocks = _Blocks()
        self.assertGreaterEqual(len(blocks.models), 6, "the docs should carry runnable examples")
        self.assertTrue(any("bracket_shape" in path for path, _ in blocks.libs), "the mirrored-pair factory is missing")
        for relative, source in blocks.libs:
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        (self.src / "lib" / "__init__.py").write_text('"""Documented helpers."""\n', encoding="utf-8")
        for document, relative, source in blocks.models:
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        # The documented models are independent of one another (the one child they
        # compose, link_pin, is written above), so their cold builds run side by side;
        # each is its own process with its own kernel import, and the store settles
        # concurrent builds by the publish rule.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            first_runs = dict(zip((relative for _, relative, _ in blocks.models),
                                  pool.map(self.run_script, (relative for _, relative, _ in blocks.models))))
            second_runs = dict(zip((relative for _, relative, _ in blocks.models),
                                   pool.map(self.run_script, (relative for _, relative, _ in blocks.models))))
        for document, relative, source in blocks.models:
            with self.subTest(document=document, model=relative):
                first = first_runs[relative]
                self.assertTrue(first.stdout.startswith("built "), f"{relative} did not report a build:\n{first.stdout}")
                script_dir = (self.project / relative).parent
                # Declarations only: an `out=` quoted in a trailing comment is prose.
                code_only = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
                declared = _OUT.findall(code_only)
                if not declared:
                    # No out=: the default sibling output of the decorator kind.
                    stem = Path(relative).stem
                    suffix = ".step" if "@step" in source else ".stl" if "@stl" in source else ".glb" if "@glb" in source else ".3mf"
                    declared = [f"{stem}{suffix}"]
                for out in declared:
                    output = (script_dir / out).resolve()
                    self.assertTrue(output.is_file(), f"{relative} declared {out} but did not write it")
                    self.assertGreater(output.stat().st_size, 0)
                second = second_runs[relative]
                self.assertTrue(second.stdout.startswith("current "), f"{relative} was not a no-op on rerun:\n{second.stdout}")

    def test_fragments_parse(self) -> None:
        blocks = _Blocks()
        self.assertGreaterEqual(len(blocks.fragments), 2, "the docs should carry fragments too")
        for document, source in blocks.fragments:
            with self.subTest(document=document, head=source.splitlines()[0]):
                filled = _PLACEHOLDER.sub("name_here", source)
                if not source.lstrip().startswith("@"):
                    ast.parse(filled)
                else:
                    ast.parse(filled + "\ndef fragment():\n    pass\n")


class DocumentationTeachesTheContract(unittest.TestCase):
    """What the skill says, pinned where a regression would be silent."""

    RETIRED = (
        "memo(",
        "cadgen.compose",
        "render package",
        "packagePath",
        "--lock-timeout",
        "contended",
        "skipped-peer\" payload",
        "needs-build",
        "must have defaults",
    )

    def test_no_retired_mechanism_is_taught(self) -> None:
        for path in (*DOCUMENTS, *sorted(repo_path("skills/cad/references").glob("*.md"))):
            text = path.read_text(encoding="utf-8")
            for word in self.RETIRED:
                self.assertNotIn(word, text, f"{path.name} still teaches {word!r}")

    def test_the_skill_teaches_the_model_contract(self) -> None:
        # Whitespace-normalized: prose wraps, and a rewrap must not fail the pin.
        skill = re.sub(r"\s+", " ", repo_path("skills/cad/SKILL.md").read_text(encoding="utf-8"))
        for phrase in (
            'if __name__ == "__main__"',
            "takes no parameters",
            "STEP is not required",
            "never `child.located(loc)`",
            "cadgen store why",
            "never wait on or cancel",
            "does not update the assemblies",
            "CADGEN_DAEMON=0",
        ):
            self.assertIn(phrase, skill, f"SKILL.md lost: {phrase!r}")
        reference = re.sub(r"\s+", " ", repo_path("skills/cad/references/step-generation.md").read_text(encoding="utf-8"))
        for phrase in (
            "models by result, constants by value, functions by file",
            "Mirrored parts are their own models",
            "def servo():",
            "Never `read_step` your own output",
        ):
            self.assertIn(phrase, reference, f"step-generation.md lost: {phrase!r}")


_JS_BLOCK = re.compile(r"```js\n(.*?)```", re.S)


class DocumentedRenderModule(unittest.TestCase):
    """The render module the kinematics reference shows is a real one.

    `STEP/<name>.step.js` is authored from what the skill shows, so the sample
    must be exactly what the loader accepts: the CLI's pre-flight reads its
    clip ids, and the shared loader (cadgen-js renderModule.js) compiles it in
    Node the same way the viewer and the snapshot page do in the browser.
    """

    @classmethod
    def setUpClass(cls) -> None:
        text = repo_path("skills/cad/references/kinematics.md").read_text(encoding="utf-8")
        blocks = [block for block in _JS_BLOCK.findall(text) if "export const clips" in block]
        assert blocks, "kinematics.md shows no render module block"
        cls.module_text = blocks[0]

    def test_the_documented_module_names_the_render_module_beside_the_document(self) -> None:
        self.assertIn("STEP/arm.step.js", self.module_text.splitlines()[0])

    def test_the_cli_preflight_reads_the_documented_clips(self) -> None:
        from cadgen._internal.render_module import declared_clip_ids

        self.assertEqual(["demo"], declared_clip_ids(self.module_text))

    def test_the_shared_loader_compiles_the_documented_module(self) -> None:
        node = shutil.which("node")
        if node is None:
            self.skipTest("node is not installed")
        loader = repo_path("packages/cadgen-js/src/common/renderModule.js")
        script = textwrap.dedent(
            f"""
            import {{ compileRenderModule, importRenderModule }} from {str(loader.as_uri())!r};
            const text = process.argv[1];
            const namespace = await importRenderModule(text, {{ name: "arm.step.js" }});
            const compiled = compileRenderModule(namespace, {{ name: "arm.step.js" }});
            console.log(JSON.stringify(Object.keys(compiled.clips)));
            """
        )
        completed = subprocess.run(
            [node, "--input-type=module", "-e", script, self.module_text],
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual('["demo"]', completed.stdout.strip())

    def test_no_reference_teaches_the_retired_declaration(self) -> None:
        for path in sorted(repo_path("skills/cad/references").glob("*.md")):
            text = path.read_text(encoding="utf-8")
            for word in ('animation="', ".anim.js"):
                self.assertNotIn(word, text, f"{path.name} still teaches {word!r}")
