"""The QwenPaw plugin mirrors the other agent plugin manifests.

`.qwenpaw-plugin/` is the third installer-facing plugin package beside
`.claude-plugin/` and `.codex-plugin/`. Its manifest must carry the release
version (stamped from VERSION by `scripts/release/sync-version.mjs`), and its
entry point must import cleanly without QwenPaw installed — the QwenPaw loader
validates a plugin by importing the backend entry and requiring a `plugin`
instance, and a checkout has no `qwenpaw` package.
"""

from __future__ import annotations

import json
import sys
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
        saved = [k for k in sys.modules if k == "qwenpaw" or k.startswith("qwenpaw.")]
        sys.modules.pop("qwenpaw", None)
        try:
            import importlib.util

            spec = importlib.util.spec_from_file_location(
                "_test_qwenpaw_plugin_entry", PLUGIN_DIR / "plugin.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(hasattr(module, "plugin"), "must export `plugin`")
            self.assertTrue(hasattr(module.plugin, "register"))
        finally:
            for key in [k for k in sys.modules if k.startswith("_test_qwenpaw_plugin_entry")]:
                sys.modules.pop(key, None)
            for key in saved:
                sys.modules.setdefault(key, sys.modules.get(key))

    def test_skills_dir_resolves_from_checkout_and_installed_copy(self) -> None:
        """The loader copies only .qwenpaw-plugin/ into ~/.qwenpaw/plugins/<id>/.

        The plugin therefore bundles its own skills/ copy, generated from the
        canonical tree; the checkout sibling is the fallback. Both layouts
        must resolve, and the bundled copy must match the canonical tree —
        a stale copy would ship different skills to QwenPaw than every other
        installer ships.
        """
        import filecmp
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "_test_qwenpaw_plugin_entry", PLUGIN_DIR / "plugin.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        try:
            resolved = module._resolve_skills_dir()
            self.assertIsNotNone(resolved, "checkout layout must resolve")
            # The resolver prefers the bundled copy; the canonical tree is the
            # fallback. What matters is that whichever it picks has content
            # matching the canonical tree, asserted by the snapshot below.
            self.assertIn(
                resolved.resolve(),
                {
                    (REPO_ROOT / "skills").resolve(),
                    (PLUGIN_DIR / "skills").resolve(),
                },
                "the skill provider must resolve to a skills tree",
            )
        finally:
            sys.modules.pop("_test_qwenpaw_plugin_entry", None)

        canonical = REPO_ROOT / "skills"
        bundled = PLUGIN_DIR / "skills"
        self.assertTrue(bundled.is_dir(), "missing generated copy .qwenpaw-plugin/skills/")

        def snapshot(root: Path) -> dict[str, bytes]:
            return {
                str(p.relative_to(root)): p.read_bytes()
                for p in sorted(root.rglob("*"))
                if p.is_file()
                and "__pycache__" not in p.parts
                and p.name not in (".DS_Store", "Thumbs.db")
            }

        left, right = snapshot(canonical), snapshot(bundled)
        self.assertEqual(
            sorted(left),
            sorted(right),
            ".qwenpaw-plugin/skills/ file set diverged from skills/ — "
            "regenerate the copy (see .qwenpaw-plugin/README.md)",
        )
        drift = [
            name
            for name, data in left.items()
            if name in right and data != right[name]
        ]
        self.assertEqual(
            [],
            drift,
            ".qwenpaw-plugin/skills/ content diverged from skills/ — "
            "regenerate the copy (see .qwenpaw-plugin/README.md)",
        )
        self.assertTrue(
            left,
            "the skills snapshot found no files; the glob is broken",
        )

    def test_skills_dir_missing_layout_does_not_crash_register(self) -> None:
        """A plugin copy with no skills/ anywhere near it must not raise.

        The loader's install hook silently no-ops on a missing skills_dir;
        if the resolver returned a nonexistent path, every startup would
        provision nothing and only a log line would say why. register()
        must take the skip branch and still register the rest.
        """
        import importlib.util
        import tempfile

        saved = [k for k in sys.modules if k == "qwenpaw" or k.startswith("qwenpaw.")]
        sys.modules.pop("qwenpaw", None)
        with tempfile.TemporaryDirectory() as tmp:
            orphan = Path(tmp) / "plugin.py"
            orphan.write_text((PLUGIN_DIR / "plugin.py").read_text(encoding="utf-8"))
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
                for key in saved:
                    sys.modules.setdefault(key, sys.modules.get(key))

    def test_skills_dir_missing_layout_does_not_crash_register(self) -> None:
        """A plugin copy with no skills/ anywhere near it must not raise.

        The loader's install hook silently no-ops on a missing skills_dir;
        if the resolver returned a nonexistent path, every startup would
        provision nothing and only a log line would say why. register()
        must take the skip branch and still register the rest.
        """
        import importlib.util
        import tempfile

        saved = [k for k in sys.modules if k == "qwenpaw" or k.startswith("qwenpaw.")]
        sys.modules.pop("qwenpaw", None)
        with tempfile.TemporaryDirectory() as tmp:
            orphan = Path(tmp) / "plugin.py"
            orphan.write_text((PLUGIN_DIR / "plugin.py").read_text(encoding="utf-8"))
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
                for key in saved:
                    sys.modules.setdefault(key, sys.modules.get(key))


if __name__ == "__main__":
    unittest.main()
