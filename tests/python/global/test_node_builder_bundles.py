"""Every skill that ships cadgen's JS-backed producers must also ship its Node builders.

cadgen builds the DXF and implicit render packages by spawning a Node child
(``cadgen._internal.node_runtime``), and it looks for that child at
``node_package_root()/cadjs/bin/<name>`` -- the ``packages/`` directory cadgen itself was
loaded from. In the dev checkout that is the real ``packages/cadjs/bin``; in a published
skill it is ``skills/<skill>/scripts/packages/cadjs/bin``, which only exists because
``scripts/bundle/skills/bundle-{dxf,implicit-cad}.sh`` esbuilds it there.

This test is the regression guard for the failure those bundle steps fix: a skill runtime
that vendored ``cadgen`` but not its builder shipped a format it could not build, and said so
only at build time, in the user's model directory. It asserts what a published skill needs
and cannot get any other way -- the file is present, is a REAL file (a symlink would be
dropped silently by Codex's plugin installer; see ``check-builds.sh``), and is
self-contained: no bare specifier survives that would need a ``node_modules`` the published
tree does not have.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# Builder file name -> the cadgen module constant that names it, so a rename in either place
# has to be a rename in both.
BUILDER_CONSTANTS = {
    "dxf-artifact.mjs": ("cadgen/_internal/drawing_package.py", "DRAWING_PREVIEW_BUILDER"),
    "implicit-artifact.mjs": ("cadgen/_internal/implicit_package.py", "IMPLICIT_BUILDER"),
}

# Skill -> the files its builders need at runtime. The extra two implicit entries are not
# optional decoration: their paths are computed from `import.meta.url` INSIDE the bundle
# (`register("./implicitClosureHooks.mjs", ...)` and
# `new Worker(new URL("./meshWorkerEntry.js", ...))`), so esbuild cannot inline them and the
# builder dies at run time without them.
SKILL_BUILDERS = {
    "dxf": ("dxf-artifact.mjs",),
    "implicit-cad": ("implicit-artifact.mjs", "implicitClosureHooks.mjs", "meshWorkerEntry.js"),
}

# A bare specifier in an emitted bundle means a dependency that a published skill -- which
# ships no node_modules -- cannot resolve. Only node: builtins may survive.
BARE_IMPORT_RE = re.compile(r"""(?:^|[\s;,{}()])(?:import|export)[^;\n]{0,200}?from\s*["']([^"'./][^"']*)["']""")


def builder_dir(skill: str) -> Path:
    return REPO_ROOT / "skills" / skill / "scripts" / "packages" / "cadjs" / "bin"


class NodeBuilderBundleTests(unittest.TestCase):
    def test_every_skill_ships_the_builders_its_producers_spawn(self) -> None:
        for skill, names in SKILL_BUILDERS.items():
            for name in names:
                path = builder_dir(skill) / name
                with self.subTest(skill=skill, builder=name):
                    self.assertTrue(
                        path.is_file(),
                        f"Missing Node builder {path.relative_to(REPO_ROOT)}. Run "
                        f"scripts/bundle/bundle-skill.sh {skill} and commit the output.",
                    )

    def test_builders_are_real_files_not_symlinks(self) -> None:
        # check-builds.sh enforces this over the whole generated tree; asserted here too so
        # the failure names the builder rather than an anonymous "first symlink".
        for skill, names in SKILL_BUILDERS.items():
            for name in (*names, "package.json"):
                path = builder_dir(skill) / name
                with self.subTest(skill=skill, builder=name):
                    self.assertFalse(
                        path.is_symlink(),
                        f"{path.relative_to(REPO_ROOT)} is a symlink; Codex's plugin installer "
                        "drops symlinks silently, so the published skill would lose it.",
                    )

    def test_builder_bundles_import_nothing_a_published_skill_cannot_resolve(self) -> None:
        for skill, names in SKILL_BUILDERS.items():
            for name in names:
                path = builder_dir(skill) / name
                if not path.is_file():
                    continue  # reported by test_every_skill_ships_...
                with self.subTest(skill=skill, builder=name):
                    unresolvable = sorted(
                        {
                            specifier
                            for specifier in BARE_IMPORT_RE.findall(path.read_text(encoding="utf-8"))
                            if not specifier.startswith("node:")
                        }
                    )
                    self.assertEqual(
                        [],
                        unresolvable,
                        f"{path.relative_to(REPO_ROOT)} still imports {unresolvable} by bare "
                        "specifier. A published skill ships no node_modules, so the bundle "
                        "must inline everything but node: builtins.",
                    )

    def test_emitted_builder_directory_is_marked_as_esm(self) -> None:
        # meshWorkerEntry.js is spawned by that exact basename, and a bare .js with no `type`
        # above it parses as CommonJS -- which would reject its `import` statements.
        for skill in SKILL_BUILDERS:
            manifest = builder_dir(skill) / "package.json"
            with self.subTest(skill=skill):
                self.assertTrue(manifest.is_file(), f"Missing {manifest.relative_to(REPO_ROOT)}")
                self.assertIn('"type": "module"', manifest.read_text(encoding="utf-8"))

    def test_builder_names_match_the_cadgen_constants_that_spawn_them(self) -> None:
        shipped = {name for names in SKILL_BUILDERS.values() for name in names}
        for name, (module_path, constant) in BUILDER_CONSTANTS.items():
            source = (REPO_ROOT / "packages" / "cadgen" / "src" / module_path).read_text(encoding="utf-8")
            with self.subTest(builder=name):
                self.assertIn(
                    f'{constant} = "{name}"',
                    source,
                    f"{module_path} no longer spawns {name}; the bundle scripts and this "
                    "test's SKILL_BUILDERS must be updated together.",
                )
                self.assertIn(name, shipped)

    def test_bundle_scripts_declare_the_builder_directory_as_a_generated_output(self) -> None:
        # check-builds.sh derives the paths it guards from --print-outputs, so a builder
        # directory that is not declared there is a builder directory nothing checks.
        for skill in SKILL_BUILDERS:
            script = REPO_ROOT / "scripts" / "bundle" / "skills" / f"bundle-{skill}.sh"
            with self.subTest(skill=skill):
                self.assertIn("BUILDERS_RUNTIME_DIR", script.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
