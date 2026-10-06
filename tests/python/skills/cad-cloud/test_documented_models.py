"""The cad-cloud skill's documentation is executed, not just proofread.

An agent reads this skill with no cadgen of its own and copies what it reads into requests to a
hosted server, so a script that has drifted from the model contract, a check that calls a function
cadgen no longer has, or a link that points nowhere fails on the server, after the agent has
already called the work done. The skill's code is therefore run here the way the server runs it:

* **model scripts** (a `# src/<path>.py` first line) are written into a throwaway build root and
  each one no other script imports is run as `python <entry>` from that root, cold, with a private
  store and no daemon; every output the decorators declare must exist afterwards;
* **checks** (a `# cad_inspect` first line) then run from the same root, as `cad_inspect` runs
  them (one script each, in one interpreter to pay the kernel import once), and must finish
  without error and print what they measured;
* every other Python block is parsed, every JSON block is loaded and every relative link and
  anchor must resolve;
* the skill teaches no local install and ships no code: the server is the install.
"""

from __future__ import annotations

import ast
import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.python.support.paths import REPO_ROOT, add_repo_path, repo_path

CADGEN_SRC = add_repo_path("packages/cadgen/src")

SKILL = repo_path("skills/cad-cloud")
DOCUMENTS = (SKILL / "SKILL.md", *sorted((SKILL / "references").glob("*.md")))

_FENCE = re.compile(r"^```(\w*)\n(.*?)^```", re.S | re.M)
_MODEL = re.compile(r"\A# (src/[\w/]+\.py)\n")
_CHECK = re.compile(r"\A# cad_inspect\n")
_MAIN = '__name__ == "__main__"'
_OUT = re.compile(r'out="([^"]+)"')
_IMPORT = re.compile(r"^from (\w+) import", re.M)
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^#{1,6} (.+)$", re.M)

# Runs each check as its own script (its own globals, stdout captured, a nonzero exit an error)
# in the build root. One interpreter for all of them: each would otherwise import the kernel.
_CHECKS = """\
import contextlib, io, json, sys, traceback

results = []
for name, source in json.loads(sys.stdin.read()):
    out, error = io.StringIO(), None
    try:
        with contextlib.redirect_stdout(out):
            exec(compile(source, name, "exec"), {"__name__": "__main__"})
    except SystemExit as exit_:
        error = None if exit_.code in (None, 0) else f"exited with {exit_.code}"
    except BaseException:
        error = traceback.format_exc()
    results.append({"name": name, "stdout": out.getvalue(), "error": error})
print(json.dumps(results))
"""


def _environment(store: Path) -> dict[str, str]:
    return {
        **os.environ,
        # A warm worker would serve another checkout's code.
        "CADGEN_DAEMON": "0",
        "CADGEN_COMPONENT_WORKERS": "1",
        "CADGEN_CACHE_DIR": str(store),
        "DO_NOT_TRACK": "1",
        "PYTHONPATH": str(CADGEN_SRC),
    }


def _fences(document: Path) -> list[tuple[str, str]]:
    return _FENCE.findall(document.read_text(encoding="utf-8"))


def _slug(heading: str) -> str:
    """GitHub's anchor for a heading: lowercase, punctuation dropped, spaces to hyphens."""
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


class _Blocks:
    """Every Python and JSON block in the skill, sorted by what the skill says it is."""

    def __init__(self) -> None:
        self.models: dict[str, str] = {}
        self.checks: list[tuple[str, str]] = []
        self.fragments: list[tuple[str, str]] = []
        self.json: list[tuple[str, str]] = []
        for document in DOCUMENTS:
            for language, body in _fences(document):
                if language == "json":
                    self.json.append((document.name, body))
                elif language == "python":
                    model = _MODEL.match(body)
                    if model:
                        self.models[model.group(1)] = body
                    elif _CHECK.match(body):
                        self.checks.append((document.name, body))
                    else:
                        self.fragments.append((document.name, body))

    def entries(self) -> list[str]:
        """The complete models no other documented script imports: what a build would name."""
        imported = {name for source in self.models.values() for name in _IMPORT.findall(source)}
        return sorted(
            path for path, source in self.models.items()
            if _MAIN in source and Path(path).stem not in imported
        )


class DocumentedSkillRuns(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        scratch = tempfile.TemporaryDirectory(prefix="cad-cloud-docs-")
        cls.addClassCleanup(scratch.cleanup)
        base = Path(scratch.name).resolve()
        cls.root = base / "build"
        cls.environment = _environment(base / "store")
        cls.blocks = _Blocks()
        # A sweep that silently matched nothing would pass forever.
        assert len(cls.blocks.entries()) >= 3, "the skill should document several runnable models"
        assert len(cls.blocks.checks) >= 3, "the skill should document several runnable checks"
        for relative, source in cls.blocks.models.items():
            target = cls.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source, encoding="utf-8")
        # The server's run: `python <entry>` from the build root. The entries are independent,
        # so their cold builds go side by side; each is its own process with its own kernel.
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            cls.builds = dict(zip(cls.blocks.entries(), pool.map(cls._python, cls.blocks.entries())))

    @classmethod
    def _python(cls, script: str) -> subprocess.CompletedProcess:
        path = Path(script)
        if not path.is_absolute():
            path = cls.root / script
        return subprocess.run(
            [sys.executable, str(path)],
            cwd=str(cls.root),
            env=cls.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )

    def test_every_documented_model_builds_and_writes_its_outputs(self) -> None:
        for entry, build in self.builds.items():
            with self.subTest(entry=entry):
                self.assertEqual(build.returncode, 0, f"{entry} failed:\n{build.stdout}\n{build.stderr}")
        for relative, source in self.blocks.models.items():
            code_only = "\n".join(line.split("#", 1)[0] for line in source.splitlines())
            for declared in _OUT.findall(code_only):
                output = (self.root / relative).parent / declared
                with self.subTest(model=relative, output=declared):
                    self.assertTrue(output.resolve().is_file(), f"{relative} declares {declared} but it was not written")
                    self.assertGreater(output.stat().st_size, 0)

    def test_every_documented_check_runs_against_what_the_models_built(self) -> None:
        checks = [(f"{document}: {source.splitlines()[1]}", source) for document, source in self.blocks.checks]
        run = subprocess.run(
            [sys.executable, "-c", _CHECKS],
            input=json.dumps(checks),
            cwd=str(self.root),
            env=self.environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=900,
        )
        self.assertEqual(run.returncode, 0, f"the check runner failed:\n{run.stdout}\n{run.stderr}")
        results = json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(len(checks), len(results))
        for result in results:
            with self.subTest(check=result["name"]):
                self.assertIsNone(result["error"], result["error"])
                self.assertTrue(result["stdout"].strip(), "a check prints what it measured")

    def test_fragments_parse_and_json_loads(self) -> None:
        for document, source in self.blocks.fragments:
            with self.subTest(document=document, head=source.splitlines()[0]):
                ast.parse(source)
        for document, source in self.blocks.json:
            with self.subTest(document=document, head=source.splitlines()[0]):
                json.loads(source)


class DocumentedSkillIsSelfContained(unittest.TestCase):
    def test_every_relative_link_and_anchor_resolves(self) -> None:
        links = 0
        for document in DOCUMENTS:
            text = _FENCE.sub("", document.read_text(encoding="utf-8"))
            for target in _LINK.findall(text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path, _, anchor = target.partition("#")
                linked = (document.parent / path).resolve() if path else document
                links += 1
                with self.subTest(document=document.name, link=target):
                    self.assertTrue(linked.is_file(), f"{document.name} links to {target}, which does not exist")
                    if anchor:
                        prose = _FENCE.sub("", linked.read_text(encoding="utf-8"))
                        headings = {_slug(h) for h in _HEADING.findall(prose)}
                        self.assertIn(anchor, headings, f"{linked.name} has no heading for #{anchor}")
        self.assertGreater(links, 10, "the sweep should find the skill's links")

    def test_the_skill_teaches_no_local_install_and_ships_no_code(self) -> None:
        for document in DOCUMENTS:
            text = document.read_text(encoding="utf-8")
            for word in ("uvx", "pip install", "requirements.txt", "--from cadgen=="):
                with self.subTest(document=document.name, word=word):
                    self.assertTrue(word not in text, f"{document.name} teaches a local install: {word!r}")
        self.assertEqual([], sorted(p.name for p in SKILL.rglob("*.py")))
        self.assertFalse((SKILL / "requirements.txt").exists())

    def test_the_skill_loads(self) -> None:
        head = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)
        self.assertEqual(3, len(head), "SKILL.md must open with YAML frontmatter")
        fields = dict(line.split(": ", 1) for line in head[1].strip().splitlines())
        self.assertEqual("cad-cloud", fields["name"])
        self.assertEqual("MIT", fields["license"])
        description = fields["description"]
        self.assertTrue(0 < len(description) <= 1024, "description is one non-empty line, 1024 characters at most")
        # An unquoted YAML scalar ends at ": " or " #", and a loader then rejects the file or cuts the text.
        self.assertNotIn(": ", description)
        self.assertNotIn(" #", description)
        self.assertEqual((REPO_ROOT / "LICENSE").read_bytes(), (SKILL / "LICENSE").read_bytes())
        self.assertTrue((SKILL / "agents" / "openai.yaml").is_file())


if __name__ == "__main__":
    unittest.main()
