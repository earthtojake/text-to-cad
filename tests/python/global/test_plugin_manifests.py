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
import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_NAME = "text-to-cad"
MARKETPLACE_NAME = "earthtojake"

CLAUDE_PLUGIN_PATH = REPO_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MCP_PATH = REPO_ROOT / "codex.mcp.json"
CLAUDE_MCP_PATH = REPO_ROOT / "claude.mcp.json"
CURSOR_MCP_PATH = REPO_ROOT / "cursor.mcp.json"
CODEX_PLUGIN_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"
CURSOR_PLUGIN_PATH = REPO_ROOT / ".cursor-plugin" / "plugin.json"
GEMINI_EXTENSION_PATH = REPO_ROOT / "gemini-extension.json"
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
    def test_every_provider_plugin_manifest_exists_at_the_repo_root(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, CURSOR_PLUGIN_PATH):
            self.assertTrue(
                path.is_file(),
                f"missing plugin manifest: {path.relative_to(REPO_ROOT)}",
            )

    def test_plugin_manifests_name_the_plugin_consistently(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, CURSOR_PLUGIN_PATH):
            manifest = load_json(path)
            self.assertEqual(
                manifest.get("name"),
                PLUGIN_NAME,
                f"{path.relative_to(REPO_ROOT)} must declare name {PLUGIN_NAME!r}",
            )

    def test_plugin_manifests_describe_the_plugin_identically(self) -> None:
        # Each host lists the plugin by its manifest's description, and the README's intro and the
        # docs site's Overview say it too; they are one text, so an edit to one must reach them all.
        codex = load_json(CODEX_PLUGIN_PATH)
        marketplace = load_json(MARKETPLACE_PATH)
        descriptions = {
            "claude": load_json(CLAUDE_PLUGIN_PATH).get("description"),
            "codex": codex.get("description"),
            "codex interface": codex["interface"].get("longDescription"),
            "cursor": load_json(CURSOR_PLUGIN_PATH).get("description"),
            "gemini": load_json(GEMINI_EXTENSION_PATH).get("description"),
            "marketplace": next(e for e in marketplace["plugins"] if e.get("name") == PLUGIN_NAME).get("description"),
        }
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        descriptions["readme intro"] = " ".join(readme.split("\n# text-to-cad\n\n", 1)[1].split("\n\n", 1)[0].split())
        page = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        descriptions["docs overview"] = re.search(r'const pluginDescription =\s*"([^"]+)"', page).group(1)
        self.assertEqual(len(set(descriptions.values())), 1, descriptions)

    def test_the_readme_and_the_docs_site_install_alike(self) -> None:
        # The README and the docs site's homepage are one copy (apps/docs/README.md): the message an
        # agent is sent and every install command say the same, word for word, in both.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        page = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        message = re.search(r'const agentInstallMessage = "([^"]+)"', page).group(1)
        self.assertIn(f"```text\n{message}\n```", readme)
        commands = [command.replace("\\n", "\n") for command in re.findall(r'\bcommand:\s*"([^"]+)"', page)]
        self.assertGreaterEqual(len(commands), 6)
        for command in commands:
            with self.subTest(command=command.splitlines()[0]):
                self.assertIn(command, readme)

    def test_plugin_manifests_link_the_same_pages(self) -> None:
        # The listing links every directory shows: homepage, docs, support, privacy policy and terms.
        # Claude and Cursor spell them as top-level fields, Codex under `interface`.
        claude, cursor = load_json(CLAUDE_PLUGIN_PATH), load_json(CURSOR_PLUGIN_PATH)
        codex = load_json(CODEX_PLUGIN_PATH)["interface"]
        for claude_key, codex_key in (("homepage", "websiteURL"), ("supportUrl", "supportURL"),
                                      ("privacyPolicyUrl", "privacyPolicyURL"),
                                      ("termsOfServiceUrl", "termsOfServiceURL")):
            with self.subTest(claude_key):
                self.assertTrue(claude.get(claude_key, "").startswith("https://"), claude_key)
                self.assertEqual(cursor.get(claude_key), claude[claude_key])
                self.assertEqual(codex.get(codex_key), claude[claude_key])
        for key in ("documentationUrl", "repository", "author", "license"):
            with self.subTest(key):
                self.assertEqual(cursor.get(key), claude.get(key))

    def test_plugin_short_descriptions_match(self) -> None:
        # The one-line tagline a host shows beside the name: Codex's shortDescription and the
        # Claude marketplace's description. Cursor's manifest has no such field.
        marketplace = load_json(MARKETPLACE_PATH)
        shorts = {
            "codex": load_json(CODEX_PLUGIN_PATH)["interface"].get("shortDescription"),
            "marketplace": marketplace.get("description"),
            "marketplace metadata": marketplace.get("metadata", {}).get("description"),
        }
        self.assertEqual(set(shorts.values()), {"Design 3D models"}, shorts)

    def test_plugin_manifests_point_at_the_canonical_skills_directory(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, CURSOR_PLUGIN_PATH):
            manifest = load_json(path)
            self.assertIn(
                manifest.get("skills"),
                VALID_SKILLS_POINTERS,
                f"{path.relative_to(REPO_ROOT)} must point at ./skills/",
            )

    def test_codex_icons_are_plain_square_pngs_in_the_package(self) -> None:
        # Codex draws the plugin's tab, sidebar entry and chips from these; without them it draws a
        # placeholder. Installers clone without git-lfs, so an icon kept in LFS would arrive as a
        # pointer file: each must be a real PNG in the package.
        interface = load_json(CODEX_PLUGIN_PATH)["interface"]
        for key in ("composerIcon", "logo"):
            with self.subTest(key=key):
                path = (REPO_ROOT / interface[key]).resolve()
                self.assertTrue(path.is_relative_to(REPO_ROOT) and path.is_file(), f"{key}: {interface[key]}")
                data = path.read_bytes()
                self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", f"{key} is not a PNG (an LFS pointer?)")
                width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
                self.assertTrue(width == height >= 48, f"{key} is {width}x{height}: square, 48px or more")

    def test_claude_icon_meets_the_directory_rules(self) -> None:
        # claude.ai's plugin directory takes its listing icon from .claude-plugin/icon.png: a square
        # PNG of 512 to 2048 px under 2 MB (SVG and WebP are refused).
        data = (REPO_ROOT / ".claude-plugin" / "icon.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n", "the Claude icon is not a PNG")
        width, height = int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
        self.assertTrue(width == height and 512 <= width <= 2048, f"the Claude icon is {width}x{height}")
        self.assertLess(len(data), 2 * 1024 * 1024, "the Claude icon is 2 MB or more")

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

    def test_codex_starts_the_cad_server_pinned_in_the_threads_workspace(self) -> None:
        # One uniquely named server (a host allowlists servers by name), run by uvx from the
        # runtime this plugin version pins. Not offline: the first start after an install or an
        # update downloads that runtime, given the time to (an offline start of an uncached pin
        # fails, which left every update without CAD until setup ran again). No `cwd`: Codex
        # then starts each thread's server in that thread's workspace, which is how the
        # server knows where the thread's files are before the agent says anything.
        manifest = load_json(CODEX_PLUGIN_PATH)
        self.assertEqual(manifest.get("mcpServers"), "./codex.mcp.json")
        # Codex resolves the onboarding skill as a path from the plugin root, to its SKILL.md.
        self.assertEqual(manifest.get("extensions", {}).get("com.openai", {}).get("onboardingSkill"), "./skills/cad-setup/SKILL.md")
        self.assertTrue((SKILLS_ROOT / "cad-setup" / "SKILL.md").is_file())
        servers = load_json(CODEX_MCP_PATH)["mcpServers"]
        self.assertEqual(list(servers), ["cad"])
        server = servers["cad"]
        self.assertNotIn("cwd", server)
        self.assertEqual(server["command"], "uvx")
        args = server["args"]
        self.assertNotIn("--offline", args)
        self.assertGreaterEqual(server.get("startup_timeout_sec", 0), 300)
        self.assertIn("--no-config", args)
        self.assertEqual(args[-2:], ["cadgen", "mcp"])
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(args[args.index("--from") + 1], f"cadgen=={version}")

    def test_claude_starts_the_cad_server_pinned_to_this_release(self) -> None:
        # Every plugin ships the skills with CAD's server, even where the host can only take its
        # links. Claude Code starts the server the manifest names: Codex's command without its
        # startup timeout, which Claude's config has no field for. Never a root .mcp.json, which
        # Claude Code would also offer to anyone who opens this repository as a project.
        self.assertEqual(load_json(CLAUDE_PLUGIN_PATH).get("mcpServers"), "./claude.mcp.json")
        self.assertFalse((REPO_ROOT / ".mcp.json").exists())
        servers = load_json(CLAUDE_MCP_PATH)["mcpServers"]
        self.assertEqual(list(servers), ["cad"])
        self.assertEqual(servers["cad"]["command"], "uvx")
        args = servers["cad"]["args"]
        self.assertIn("--no-config", args)
        self.assertEqual(args[-2:], ["cadgen", "mcp"])
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(args[args.index("--from") + 1], f"cadgen=={version}")

    def test_cursor_starts_claudes_server_and_shows_its_icon(self) -> None:
        # Cursor reads only .cursor-plugin/plugin.json. Its MCP config format is Claude's, and it starts
        # the same pinned server from a config of its own, which names the Cursor Marketplace as its
        # channel: the marketplace reads main. Its logo must be a relative path inside the plugin
        # tree: Cursor resolves it to that commit's raw file.
        manifest = load_json(CURSOR_PLUGIN_PATH)
        self.assertEqual(manifest.get("mcpServers"), "./cursor.mcp.json")
        cursor, claude = load_json(CURSOR_MCP_PATH)["mcpServers"]["cad"], load_json(CLAUDE_MCP_PATH)["mcpServers"]["cad"]
        self.assertEqual({**cursor, "env": None}, {**claude, "env": None})
        logo = manifest.get("logo", "")
        self.assertFalse(logo.startswith(("/", "..")) or "://" in logo, logo)
        self.assertEqual(logo, ".claude-plugin/icon.png")

    def test_gemini_extension_names_the_plugin_and_starts_claudes_server(self) -> None:
        # Gemini CLI reads gemini-extension.json at the root (and its skills/), and runs servers
        # from the manifest itself: Claude's server, pinned to this release, under the same name.
        manifest = load_json(GEMINI_EXTENSION_PATH)
        self.assertEqual(manifest.get("name"), PLUGIN_NAME)
        self.assertEqual(manifest.get("mcpServers"), load_json(CLAUDE_MCP_PATH)["mcpServers"])
        # Gemini loads the extension's GEMINI.md (or contextFileName) as the user's context; the
        # repository's own guidance (AGENTS.md) must not become it.
        self.assertNotIn("contextFileName", manifest)
        self.assertFalse((REPO_ROOT / "GEMINI.md").exists())

    def test_every_server_runs_the_one_launch_command(self) -> None:
        # The plugins' servers and the skills run cadgen as one command (cadgen._internal.launch),
        # so they share one installation and one warm daemon: no config may spell it differently.
        import sys

        sys.path.insert(0, str(REPO_ROOT / "packages" / "cadgen" / "src"))
        from cadgen._internal.launch import LAUNCHER

        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        expected = [*LAUNCHER[1:], f"cadgen=={version}", "cadgen", "mcp"]
        for path in (CLAUDE_MCP_PATH, CODEX_MCP_PATH, CURSOR_MCP_PATH, GEMINI_EXTENSION_PATH):
            with self.subTest(path=path.name):
                server = load_json(path)["mcpServers"]["cad"]
                self.assertEqual((server["command"], server["args"]), (LAUNCHER[0], expected))
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('"args": [' + ", ".join(json.dumps(arg) for arg in expected) + "]", readme)

    def test_every_package_on_main_names_its_install_channel(self) -> None:
        # Where an install came from is written into the package itself, in its server's environment
        # (cadgen's CADGEN_INSTALL_CHANNEL), never worked out at runtime. Everything installed from
        # main by hand is `github`; the Cursor Marketplace reads main, so its own config says so. The
        # plugin branch's Claude config (claude.ai's directory) and the OpenAI ZIP stamp their own.
        channels = {path.name: load_json(path)["mcpServers"]["cad"]["env"]["CADGEN_INSTALL_CHANNEL"]
                    for path in (CLAUDE_MCP_PATH, CODEX_MCP_PATH, CURSOR_MCP_PATH, GEMINI_EXTENSION_PATH)}
        self.assertEqual(channels, {"claude.mcp.json": "github", "codex.mcp.json": "github",
                                    "cursor.mcp.json": "cursor-marketplace", "gemini-extension.json": "github"})
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('"env": {"CADGEN_INSTALL_CHANNEL": "github"}', readme)

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

    def test_skills_sh_groups_every_skill_once(self) -> None:
        # skills.sh lists skills it has seen installed, removed ones included, and puts any
        # skill no group names under "Other skills" with them. A new skill left out of
        # skills.sh.json would land beside the removed ones.
        groups = load_json(REPO_ROOT / "skills.sh.json")["groupings"]
        listed = [skill for group in groups for skill in group["skills"]]
        shipped = sorted(path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md"))
        self.assertEqual(sorted(listed), shipped)


if __name__ == "__main__":
    unittest.main()
