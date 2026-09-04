"""cadgen must ship the Node builders its own producers spawn.

cadgen tessellates a DXF by spawning a Node child
(``cadgen._internal.node_runtime``), and finds that child through ``cadgen.assets.
node_builders_dir()`` -- the repo's live ``packages/cadgen-js/bin`` in a checkout, and the
packaged ``cadgen/_runtime/node`` in an installed wheel.

This is the regression guard for a failure that only ever appears at the far end: a
distribution that ships a producer but not its builder supports a format it cannot build,
and says so for the first time in the user's model directory. It asserts what an installed
cadgen needs and cannot get any other way -- the file is present, is a REAL file (a symlink
is dropped silently by Codex's plugin installer; see ``check-builds.sh``), and is
self-contained: no bare specifier survives that would need a ``node_modules`` the wheel
does not carry.

It used to assert the same thing per-skill, back when each skill vendored its own copy.
One copy inside cadgen replaced six, so the checks moved with them.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_DIR = REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "_runtime" / "node"

# Builder file name -> the cadgen module constant that names it, so a rename in either
# place has to be a rename in both.
BUILDER_CONSTANTS = {
    "dxf-mesh.mjs": ("cadgen/snapshot_cli.py", "DXF_MESH_BUILDER"),
}

REQUIRED_BUILDERS = (
    "dxf-mesh.mjs",
)

# A bare specifier in an emitted bundle means a dependency that an installed cadgen -- which
# ships no node_modules -- cannot resolve. Only node: builtins may survive.
BARE_IMPORT_RE = re.compile(
    r"""(?:^|[\s;,{}()])(?:import|export)[^;\n]{0,200}?from\s*["']([^"'./][^"']*)["']"""
)


class NodeBuilderBundleTests(unittest.TestCase):
    def test_cadgen_ships_every_builder_its_producers_spawn(self) -> None:
        for name in REQUIRED_BUILDERS:
            path = RUNTIME_DIR / name
            with self.subTest(builder=name):
                self.assertTrue(
                    path.is_file(),
                    f"Missing Node builder {path.relative_to(REPO_ROOT)}. Run "
                    "scripts/bundle/bundle-skill.sh cadgen-runtime and commit the output.",
                )

    def test_builders_are_real_files_not_symlinks(self) -> None:
        # check-builds.sh enforces this over the whole generated tree; asserted here too so
        # the failure names the builder rather than an anonymous "first symlink".
        for name in (*REQUIRED_BUILDERS, "package.json"):
            path = RUNTIME_DIR / name
            with self.subTest(builder=name):
                self.assertFalse(
                    path.is_symlink(),
                    f"{path.relative_to(REPO_ROOT)} is a symlink; Codex's plugin installer "
                    "drops symlinks silently, so the published tree would lose it.",
                )

    def test_builder_bundles_import_nothing_an_installed_cadgen_cannot_resolve(self) -> None:
        for name in REQUIRED_BUILDERS:
            path = RUNTIME_DIR / name
            if not path.is_file():
                continue  # reported by test_cadgen_ships_every_builder_...
            with self.subTest(builder=name):
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
                    "specifier. The wheel ships no node_modules, so the bundle must inline "
                    "everything but node: builtins.",
                )

    def test_emitted_builder_directory_is_marked_as_esm(self) -> None:
        # The emitted directory declares ESM, matching packages/cadgen-js itself, so a builder
        # emitted as a bare `.js` would still parse as a module rather than as CommonJS.
        manifest = RUNTIME_DIR / "package.json"
        self.assertTrue(manifest.is_file(), f"Missing {manifest.relative_to(REPO_ROOT)}")
        self.assertIn('"type": "module"', manifest.read_text(encoding="utf-8"))

    def test_builder_names_match_the_cadgen_constants_that_spawn_them(self) -> None:
        for name, (module_path, constant) in BUILDER_CONSTANTS.items():
            source = (REPO_ROOT / "packages" / "cadgen" / "src" / module_path).read_text(
                encoding="utf-8"
            )
            with self.subTest(builder=name):
                self.assertIn(
                    f'{constant} = "{name}"',
                    source,
                    f"{module_path} no longer spawns {name}; the bundle script and this "
                    "test's REQUIRED_BUILDERS must be updated together.",
                )
                self.assertIn(name, REQUIRED_BUILDERS)

    def test_the_bundle_declares_the_builder_directory_as_a_generated_output(self) -> None:
        # check-builds.sh derives the paths it guards from --print-outputs, so a builder
        # directory that is not declared there is a builder directory nothing checks.
        script = REPO_ROOT / "scripts" / "bundle" / "skills" / "bundle-cadgen-runtime.sh"
        self.assertIn("NODE_DIR", script.read_text(encoding="utf-8"))

    def test_no_skill_vendors_a_builder_any_more(self) -> None:
        """The thing this file used to assert must now never be true.

        A stray `skills/*/scripts/packages` would be shipped and imported ahead of the
        distribution, quietly pinning that skill to a stale builder.
        """
        strays = sorted(p.relative_to(REPO_ROOT).as_posix() for p in REPO_ROOT.glob("skills/*/scripts/packages"))
        self.assertEqual([], strays, f"skills must not vendor runtimes: {strays}")


if __name__ == "__main__":
    unittest.main()
