"""The render skill's files, read as text: its Blender helper is the repository's one GPL file and says so, imports
nothing but bpy and the standard library, and is the API the skill's page documents; the GPL's text beside it and in
cad-server is the Free Software Foundation's, unchanged; and every licence the skill ships under names the exception.
Standard library alone: the helper runs only inside Blender, and its behaviour is the blender job's suite
(tests/python/packages/blender)."""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
import tomllib
import unittest

from tests.python.support.paths import REPO_ROOT

SKILL = REPO_ROOT / "skills/render"
HELPER = SKILL / "scripts/cad_glb.py"
# sha256 of https://www.gnu.org/licenses/gpl-3.0.txt, the GPL version 3's text as the FSF publishes it.
GPL_3 = "3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986"
EXPRESSION = "MIT AND GPL-3.0-or-later"
MARK = "SPDX-License-" "Identifier: GPL"  # split, so this file does not carry it
MANIFESTS = (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".cursor-plugin/plugin.json", "plugin.json")


def _files() -> list[str]:
    listed = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=REPO_ROOT,
                            capture_output=True, text=True, check=True).stdout.splitlines()
    return [path for path in listed if not path.startswith("models/") and (REPO_ROOT / path).is_file()]


class HelperLicence(unittest.TestCase):
    def test_the_helper_says_it_is_gpl_whose_it_is_and_that_it_alone_is(self) -> None:
        head = HELPER.read_text(encoding="utf-8").split('"""', 1)[0]
        self.assertIn(f"# {MARK}-3.0-or-later\n", head)
        self.assertIn("either version 3 of the License,\n# or (at your option) any later version.", head)
        holder = re.search(r"^Copyright \(c\) .+$", (REPO_ROOT / "LICENSE").read_text(encoding="utf-8"), re.M).group(0)
        self.assertIn(f"# {holder}\n", head)
        self.assertIn("only GPL file, and it runs only inside Blender", head)

    def test_it_is_the_repositorys_only_gpl_file(self) -> None:
        marked = []
        for path in _files():
            if path.endswith((".py", ".js", ".mjs", ".ts", ".tsx", ".sh", ".md")):
                if MARK in (REPO_ROOT / path).read_text(encoding="utf-8", errors="replace"):
                    marked.append(path)
        self.assertEqual(marked, ["skills/render/scripts/cad_glb.py"])

    def test_the_gpl_text_is_the_fsfs_unchanged_beside_it_and_in_cad_server(self) -> None:
        for path in (SKILL / "scripts/COPYING", REPO_ROOT / "packages/cad-server/COPYING"):
            with self.subTest(path=path.relative_to(REPO_ROOT).as_posix()):
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), GPL_3)

    def test_every_licence_the_skill_ships_under_names_the_exception(self) -> None:
        front = (SKILL / "SKILL.md").read_text(encoding="utf-8").split("\n---\n", 1)[0]
        self.assertIn(f"\nlicense: {EXPRESSION}\n", front)
        self.assertIn("scripts/cad_glb.py", (SKILL / "LICENSE").read_text(encoding="utf-8"))
        self.assertIn("skills/render/scripts/cad_glb.py", (REPO_ROOT / "LICENSE").read_text(encoding="utf-8"))
        # The server's wheel carries the skills (its plugin), so its licence is the expression, with the GPL's text.
        server = tomllib.loads((REPO_ROOT / "packages/cad-server/pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual((server["license"], server["license-files"]), (EXPRESSION, ["LICENSE", "COPYING"]))
        self.assertIn("render/scripts/cad_glb.py", (REPO_ROOT / "packages/cad-server/LICENSE").read_text(encoding="utf-8"))
        # The library and the shim ship no skill: MIT alone.
        for project in ("cad", "cad-mcp"):
            with self.subTest(project=project):
                text = (REPO_ROOT / f"packages/{project}/pyproject.toml").read_text(encoding="utf-8")
                self.assertEqual(tomllib.loads(text)["project"]["license"], "MIT")
        for path in MANIFESTS:
            with self.subTest(manifest=path):
                self.assertEqual(json.loads((REPO_ROOT / path).read_text(encoding="utf-8"))["license"], EXPRESSION)
        catalog = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        self.assertEqual({entry["license"] for entry in catalog["plugins"]}, {EXPRESSION})


class HelperCode(unittest.TestCase):
    def setUp(self) -> None:
        self.tree = ast.parse(HELPER.read_text(encoding="utf-8"))

    def test_it_imports_bpy_and_the_standard_library_alone(self) -> None:
        names = set()
        for node in ast.walk(self.tree):
            if isinstance(node, ast.Import):
                names |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom):
                names.add((node.module or "").split(".")[0])
        self.assertIn("bpy", names)
        self.assertEqual(sorted(names - set(sys.stdlib_module_names) - {"bpy", "mathutils", "__future__"}), [])

    def test_the_page_documents_the_api_it_has(self) -> None:
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        load = next(node for node in self.tree.body if isinstance(node, ast.FunctionDef) and node.name == "load")
        defaults = [ast.literal_eval(value) for value in load.args.defaults]
        arguments = [argument.arg for argument in load.args.args]
        self.assertEqual((arguments, defaults), (["path", "clip", "fps"], [None, 24]))
        self.assertIn("`cad_glb.load(path, clip=None, fps=24)`", text)
        model = next(node for node in self.tree.body if isinstance(node, ast.ClassDef) and node.name == "Model")
        members = {node.target.id for node in model.body if isinstance(node, ast.AnnAssign)}
        members |= {node.name for node in model.body if isinstance(node, ast.FunctionDef)}
        for name in set(re.findall(r"`model\.(\w+)", text)):
            with self.subTest(name=name):
                self.assertIn(name, members)


if __name__ == "__main__":
    unittest.main()
