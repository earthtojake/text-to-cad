"""Policy checks for the repo-root agent plugin package.

The repository root *is* the plugin: `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json` sit beside `.claude-plugin/marketplace.json`, and
the plugin's skills are the canonical `skills/` directory rather than a
generated copy. These checks replace the manifest validation that used to live
in `scripts/bundle/bundle-plugin.sh` back when the plugin was a subdirectory
package with its own duplicated `skills/` tree.

Version fields are deliberately not checked here; `scripts/release/sync-version.mjs`
owns stamping every derived version from the canonical `VERSION` file, and
`--check` enforces it in CI.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_NAME = "cad"
MARKETPLACE_NAME = "earthtojake"

CLAUDE_PLUGIN_PATH = REPO_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MCP_PATH = REPO_ROOT / "codex.mcp.json"
CODEX_PLUGIN_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"
MARKETPLACE_PATH = REPO_ROOT / ".claude-plugin" / "marketplace.json"
SKILLS_ROOT = REPO_ROOT / "skills"

# A plugin manifest may point at its skills directory in any of these forms.
VALID_SKILLS_POINTERS = {"./skills/", "./skills", "skills"}

# Codex resolves a repo-root plugin source from exactly these two spellings
# (codex-rs/core-plugins/src/marketplace.rs). Anything else is treated as a
# subdirectory path and would not resolve to the repository root.
VALID_ROOT_SOURCES = {"./", "."}


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class PluginManifestPolicyTest(unittest.TestCase):
    def test_both_provider_plugin_manifests_exist_at_the_repo_root(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH):
            self.assertTrue(
                path.is_file(),
                f"missing plugin manifest: {path.relative_to(REPO_ROOT)}",
            )

    def test_plugin_manifests_name_the_plugin_consistently(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH):
            manifest = load_json(path)
            self.assertEqual(
                manifest.get("name"),
                PLUGIN_NAME,
                f"{path.relative_to(REPO_ROOT)} must declare name {PLUGIN_NAME!r}",
            )

    def test_plugin_manifests_point_at_the_canonical_skills_directory(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH):
            manifest = load_json(path)
            self.assertIn(
                manifest.get("skills"),
                VALID_SKILLS_POINTERS,
                f"{path.relative_to(REPO_ROOT)} must point at ./skills/",
            )

    def test_codex_icons_are_plain_square_pngs_in_the_package(self) -> None:
        # Codex draws the plugin's tab, sidebar entry and chips from these; without them it draws a
        # placeholder. Installers clone without git-lfs, so an icon under the LFS-tracked assets/
        # would arrive as a pointer file: each must be a real PNG in the package.
        interface = load_json(CODEX_PLUGIN_PATH)["interface"]
        for key in ("composerIcon", "logo"):
            with self.subTest(key=key):
                path = (REPO_ROOT / interface[key]).resolve()
                self.assertTrue(path.is_relative_to(REPO_ROOT) and path.is_file(), f"{key}: {interface[key]}")
                data = path.read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", f"{key} is not a PNG (an LFS pointer?)")
                width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
                self.assertTrue(width == height >= 48, f"{key} is {width}x{height}: square, 48px or more")

    def test_marketplace_lists_the_plugin_at_the_repository_root(self) -> None:
        marketplace = load_json(MARKETPLACE_PATH)
        self.assertEqual(marketplace.get("name"), MARKETPLACE_NAME)

        plugins = marketplace.get("plugins")
        self.assertIsInstance(plugins, list, "marketplace plugins must be an array")

        entries = [
            entry
            for entry in plugins
            if isinstance(entry, dict) and entry.get("name") == PLUGIN_NAME
        ]
        self.assertEqual(
            len(entries),
            1,
            f"marketplace must contain exactly one {PLUGIN_NAME!r} entry",
        )
        self.assertIn(
            entries[0].get("source"),
            VALID_ROOT_SOURCES,
            "marketplace entry must source the plugin from the repository root",
        )

    def test_codex_starts_the_cad_server_pinned_offline_in_the_threads_workspace(self) -> None:
        # One uniquely named server (a host allowlists servers by name), run by uvx from the
        # runtime this plugin version pins, never downloading at startup. No `cwd`: Codex
        # then starts each thread's server in that thread's workspace, which is how the
        # server knows where the thread's files are before the agent says anything.
        manifest = load_json(CODEX_PLUGIN_PATH)
        self.assertEqual(manifest.get("mcpServers"), "./codex.mcp.json")
        self.assertEqual(manifest.get("extensions", {}).get("com.openai", {}).get("onboardingSkill"), "setup")
        self.assertTrue((SKILLS_ROOT / "setup" / "SKILL.md").is_file())
        servers = load_json(CODEX_MCP_PATH)["mcpServers"]
        self.assertEqual(list(servers), ["text_to_cad"])
        server = servers["text_to_cad"]
        self.assertNotIn("cwd", server)
        self.assertEqual(server["command"], "uvx")
        args = server["args"]
        self.assertIn("--offline", args)
        self.assertIn("--no-config", args)
        self.assertEqual(args[-2:], ["cadgen", "mcp"])
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(args[args.index("--from") + 1], f"cadgen=={version}")

    def test_no_stale_plugin_subdirectory_package_remains(self) -> None:
        # The generated `plugins/cad/skills` copy is what the repo-root move
        # removed. If it reappears, the duplicate would silently go stale.
        self.assertFalse(
            (REPO_ROOT / "plugins").exists(),
            "plugins/ was replaced by the repo-root plugin package",
        )

    def test_every_skill_directory_is_a_loadable_skill(self) -> None:
        # The plugin ships `skills/` directly, so any directory without a
        # SKILL.md would be published as a broken skill.
        for path in sorted(SKILLS_ROOT.iterdir()):
            if not path.is_dir() or path.name.startswith("."):
                continue
            self.assertTrue(
                (path / "SKILL.md").is_file(),
                f"missing skill manifest: skills/{path.name}/SKILL.md",
            )


if __name__ == "__main__":
    unittest.main()
