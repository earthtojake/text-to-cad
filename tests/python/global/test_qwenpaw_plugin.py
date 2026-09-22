"""The QwenPaw plugin mirrors the other agent plugin manifests.

`.qwenpaw-plugin/` sits beside `.claude-plugin/` and `.codex-plugin/` as an
installer-facing plugin package. Its manifest must carry the release version
(stamped from VERSION by `scripts/release/sync-version.mjs`), and its entry
point must import cleanly without QwenPaw installed — the QwenPaw loader
validates a plugin by importing the backend entry and requiring a `plugin`
instance, and a checkout has no `qwenpaw` package.

Unlike the repo-root plugin packages, the QwenPaw loader installs a plugin by
copying its one directory, so a skill tree cannot be referenced from outside
it. Nothing is duplicated in git for that purpose: the entry point resolves a
`skills/` tree at runtime, and these tests pin the resolution order and, more
importantly, that a configured path which fails to resolve is reported instead
of being quietly served by a stale copy.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_DIR = REPO_ROOT / ".qwenpaw-plugin"
MANIFEST_PATH = PLUGIN_DIR / "plugin.json"

VALID_QWENPAW_TYPES = {
    "tool",
    "provider",
    "hook",
    "command",
    "channel",
    "frontend",
    "app",
    "general",
}


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_entry(test: unittest.TestCase):
    """Import the plugin entry point, cleaned out of `sys.modules` afterwards.

    The resolver reads its own module-level `PLUGIN_DIR`, so tests that move it
    around must not leave the module cached with someone else's path in it.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_test_qwenpaw_plugin_entry", PLUGIN_DIR / "plugin.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    test.addCleanup(sys.modules.pop, "_test_qwenpaw_plugin_entry", None)
    return module


class QwenPawPluginManifestTest(unittest.TestCase):
    def test_manifest_exists(self) -> None:
        self.assertTrue(
            MANIFEST_PATH.is_file(),
            "missing .qwenpaw-plugin/plugin.json",
        )

    def test_manifest_has_the_required_fields(self) -> None:
        manifest = load_manifest()
        for field in ("id", "version", "name"):
            self.assertTrue(
                str(manifest.get(field, "")).strip(),
                f"plugin.json must declare a non-empty {field!r}",
            )

    def test_manifest_type_is_a_known_plugin_type(self) -> None:
        self.assertIn(load_manifest().get("type"), VALID_QWENPAW_TYPES)

    def test_backend_entry_is_declared(self) -> None:
        entry = load_manifest().get("entry") or {}
        self.assertTrue(
            entry.get("backend"),
            "entry.backend must name the Python entry file",
        )
        self.assertTrue(
            (PLUGIN_DIR / entry["backend"]).is_file(),
            "entry.backend must exist in the plugin directory",
        )

    def test_version_matches_the_canonical_release_version(self) -> None:
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(
            load_manifest().get("version"),
            version,
            ".qwenpaw-plugin/plugin.json version must equal VERSION "
            "(scripts/release/sync-version.mjs stamps it)",
        )

    def test_entry_imports_without_qwenpaw_installed(self) -> None:
        """The loader imports the entry and requires a `plugin` instance.

        The module must keep its importable surface stdlib-only (the
        qwenpaw import sits under `if TYPE_CHECKING`), so validation
        succeeds in a checkout and on any machine before dependencies
        are installed.
        """
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_test_qwenpaw_plugin_entry", PLUGIN_DIR / "plugin.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            self.assertTrue(hasattr(module, "plugin"), "must export `plugin`")
            self.assertTrue(hasattr(module.plugin, "register"))
        finally:
            sys.modules.pop("_test_qwenpaw_plugin_entry", None)

    def test_skills_dir_resolves_to_the_canonical_tree(self) -> None:
        """With no config and no generated copy, the checkout sibling resolves.

        This is the layout the repository itself now ships: one `skills/` tree,
        no second copy in git. An install that generated the bundled copy, or
        a config naming a path, is covered by the tests below.
        """
        module = load_entry(self)
        resolved = module._resolve_skills_dir()
        self.assertEqual(
            resolved,
            REPO_ROOT / "skills",
            "the checkout sibling must resolve",
        )
        self.assertEqual(
            module._SKILLS_STATE["resolved"],
            "checkout sibling",
            "the reported source must name what won, for /cad-setup",
        )

    def test_configured_skills_dir_outranks_local_candidates(self) -> None:
        """plugins.cad.skills_dir wins, which is what avoids the duplicate."""
        module = load_entry(self)
        with tempfile.TemporaryDirectory() as tmp:
            configured = Path(tmp) / "checkout" / "skills"
            (configured / "cad").mkdir(parents=True)
            (configured / "cad" / "SKILL.md").write_text("# cad\n", encoding="utf-8")
            self.assertEqual(
                module._resolve_skills_dir({"skills_dir": str(configured)}),
                configured,
            )
            self.assertEqual(module._SKILLS_STATE["resolved"], "configured")

    def test_bundled_copy_is_preferred_over_the_checkout_sibling(self) -> None:
        """An install that generated the copy uses it, not the repo tree.

        The copy is the documented answer for a user with no checkout to point
        at, so it has to win over whatever sibling happens to exist.
        """
        module = load_entry(self)
        original = module.PLUGIN_DIR
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "plugins" / "cad"
            for tree in (plugin_dir / "skills", plugin_dir.parent / "skills"):
                (tree / "cad").mkdir(parents=True)
                (tree / "cad" / "SKILL.md").write_text("# cad\n", encoding="utf-8")
            module.PLUGIN_DIR = plugin_dir
            try:
                self.assertEqual(
                    module._resolve_skills_dir(),
                    plugin_dir / "skills",
                )
                self.assertEqual(
                    module._SKILLS_STATE["resolved"],
                    "bundled copy",
                )
            finally:
                module.PLUGIN_DIR = original

    def test_stale_configured_path_is_reported_and_not_fallen_back_through(
        self,
    ) -> None:
        """A bad pointer is a misconfiguration, not a licence to serve a copy.

        Falling through to the bundled copy here would let a moved checkout keep
        provisioning skills nobody updated, with the error buried in a log line
        nobody reads. Resolution stops, and the state says so.
        """
        module = load_entry(self)
        original = module.PLUGIN_DIR
        with tempfile.TemporaryDirectory() as tmp:
            plugin_dir = Path(tmp) / "plugins" / "cad"
            (plugin_dir / "skills" / "cad").mkdir(parents=True)
            (plugin_dir / "skills" / "cad" / "SKILL.md").write_text(
                "# cad\n", encoding="utf-8"
            )
            module.PLUGIN_DIR = plugin_dir
            try:
                with self.assertLogs(module.logger, level="ERROR") as logs:
                    self.assertIsNone(
                        module._resolve_skills_dir(
                            {"skills_dir": str(Path(tmp) / "moved-away")}
                        )
                    )
                self.assertIn("not a skills tree", " ".join(logs.output))
                self.assertEqual(
                    module._SKILLS_STATE["resolved"],
                    "configured path invalid",
                )
                # The reported path is the whole thing: /x/moved-away/skills
                # shown as "skills" tells the user nothing about where to look.
                self.assertEqual(
                    module._SKILLS_STATE["path"],
                    str(Path(tmp) / "moved-away"),
                )
            finally:
                module.PLUGIN_DIR = original

    def test_skills_dir_missing_layout_does_not_crash_register(self) -> None:
        """A plugin copy with no skills/ anywhere near it must not raise.

        The loader's install hook silently no-ops on a missing skills_dir;
        if the resolver returned a nonexistent path, every startup would
        provision nothing and only a log line would say why. register()
        must take the skip branch and still register the rest.
        """
        import importlib.util
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            orphan = Path(tmp) / "plugin.py"
            orphan.write_text(
                (PLUGIN_DIR / "plugin.py").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            spec = importlib.util.spec_from_file_location(
                "_test_qwenpaw_plugin_orphan", orphan
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            try:
                self.assertIsNone(module._resolve_skills_dir())
                registered: list[str] = []

                class FakeApi:
                    def register_skill_provider(self, skills_dir, **kwargs):
                        registered.append("skills")

                    def register_slash_command(self, name, handler, **kwargs):
                        registered.append(f"slash:{name}")

                    def register_startup_hook(self, hook_name, callback, priority=100):
                        registered.append(f"hook:{hook_name}")

                    def register_workspace_created_hook(self, hook_name, callback, priority=100):
                        registered.append(f"wshook:{hook_name}")

                    def register_prompt_section(self, name, after, provider, **kwargs):
                        registered.append(f"prompt:{name}")

                module.plugin.register(FakeApi())
                self.assertNotIn(
                    "skills",
                    registered,
                    "no skills dir: skill registration must be skipped",
                )
                self.assertIn(
                    "slash:cad-setup",
                    registered,
                    "the preflight command registers regardless of skills",
                )
                self.assertNotIn(
                    "prompt:text_to_cad_setup_hint",
                    registered,
                    "no skills: the setup hint must not advertise them",
                )
            finally:
                sys.modules.pop("_test_qwenpaw_plugin_orphan", None)


if __name__ == "__main__":
    unittest.main()
