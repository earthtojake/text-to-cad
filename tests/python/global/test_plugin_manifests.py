"""Policy checks for the repo-root agent plugin package.

The repository root *is* the plugin: `.claude-plugin/plugin.json` and
`.codex-plugin/plugin.json` sit beside `.claude-plugin/marketplace.json`, and
the plugin's skills are the canonical `skills/` directory rather than a
generated copy. Publish Release builds the `latest` branch, the plugin alone, from
this tree (scripts/release/plugin_branch.py). These checks replace the manifest validation that used to live
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
QODER_MCP_PATH = REPO_ROOT / "qoder.mcp.json"
CLAUDE_MCP_PATH = REPO_ROOT / "claude.mcp.json"
CURSOR_MCP_PATH = REPO_ROOT / "cursor.mcp.json"
MCP_PATH = REPO_ROOT / "mcp.json"
CODEX_PLUGIN_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"
QODER_PLUGIN_PATH = REPO_ROOT / ".qoder-plugin" / "plugin.json"
CURSOR_PLUGIN_PATH = REPO_ROOT / ".cursor-plugin" / "plugin.json"
PLUGIN_PATH = REPO_ROOT / "plugin.json"
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
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, QODER_PLUGIN_PATH, CURSOR_PLUGIN_PATH, PLUGIN_PATH):
            self.assertTrue(
                path.is_file(),
                f"missing plugin manifest: {path.relative_to(REPO_ROOT)}",
            )

    def test_plugin_manifests_name_the_plugin_consistently(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, QODER_PLUGIN_PATH, CURSOR_PLUGIN_PATH, PLUGIN_PATH):
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
            "qoder": load_json(QODER_PLUGIN_PATH).get("description"),
            "codex interface": codex["interface"].get("longDescription"),
            "cursor": load_json(CURSOR_PLUGIN_PATH).get("description"),
            "agent plugins": load_json(PLUGIN_PATH).get("description"),
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
        # agent is sent, what it sends, and every install, update and remove command say the same, word
        # for word, in both.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        page = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        message = re.search(r'const agentInstallMessage = "([^"]+)"', page).group(1)
        self.assertIn(f"```text\n{message}\n```", readme)
        # What it sends, said under the message: the same sentence, however the README wraps it.
        note = re.search(r'const telemetryNote =\s*"([^"]+)"', page).group(1)
        self.assertIn(note, " ".join(readme.split()))
        commands = [command.replace("\\n", "\n")
                    for command in re.findall(r'\b(?:command|update|remove):\s*"([^"]+)"', page)]
        self.assertGreaterEqual(len(commands), 16)
        for command in commands:
            with self.subTest(command=command.splitlines()[0]):
                self.assertIn(command, readme)

    def test_the_update_cards_instructions_link_reaches_the_docs_install_section(self) -> None:
        # cadgen's update card links to texttocad.dev/install; the docs site redirects that to its
        # Install section, so renaming the section or dropping the redirect breaks every card.
        updates = (REPO_ROOT / "packages" / "cadgen" / "src" / "cadgen" / "updates.py").read_text(encoding="utf-8")
        self.assertIn('INSTRUCTIONS = "https://www.texttocad.dev/install"', updates)
        config = (REPO_ROOT / "apps" / "docs" / "next.config.ts").read_text(encoding="utf-8")
        self.assertIn('{ source: "/install", destination: "/#install"', config)
        page = (REPO_ROOT / "apps" / "docs" / "src" / "app" / "page.tsx").read_text(encoding="utf-8")
        self.assertIn('<section id="install"', page)

    def test_plugin_manifests_link_the_same_pages(self) -> None:
        # The listing links every directory shows: homepage, docs, support, privacy policy and terms.
        # Claude and Cursor spell them as top-level fields, Codex under `interface`.
        claude, qoder, cursor = load_json(CLAUDE_PLUGIN_PATH), load_json(QODER_PLUGIN_PATH), load_json(CURSOR_PLUGIN_PATH)
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
        for key in ("homepage", "repository", "author", "license", "keywords"):
            with self.subTest(f"qoder {key}"):
                self.assertEqual(qoder.get(key), claude.get(key))
        standard = load_json(PLUGIN_PATH)
        for key in ("homepage", "repository", "author", "license"):
            with self.subTest(f"agent plugins {key}"):
                self.assertEqual(standard.get(key), claude.get(key))

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
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, QODER_PLUGIN_PATH, CURSOR_PLUGIN_PATH):
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

    def test_main_installs_as_itself(self) -> None:
        # Installs always work from main (AGENTS.md): a command that names no branch installs main as
        # it is. So no manifest or config here points an installer at another branch or repository.
        def keys(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    yield key
                    yield from keys(item)
            elif isinstance(value, list):
                for item in value:
                    yield from keys(item)

        for path in (MARKETPLACE_PATH, CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, QODER_PLUGIN_PATH,
                     CURSOR_PLUGIN_PATH, GEMINI_EXTENSION_PATH, PLUGIN_PATH, CLAUDE_MCP_PATH,
                     CODEX_MCP_PATH, QODER_MCP_PATH, CURSOR_MCP_PATH, MCP_PATH):
            with self.subTest(path=path.name):
                self.assertFalse({"ref", "sha"} & set(keys(load_json(path))), f"{path.name} names a git ref")
        for entry in load_json(MARKETPLACE_PATH)["plugins"]:
            self.assertIn(entry.get("source"), VALID_ROOT_SOURCES)

    def test_the_documented_commands_install_latest(self) -> None:
        # The preferred install is `latest`, the plugin alone, written once a release is on PyPI: every
        # command in the README and on the docs site names it, each in its app's own syntax.
        commands = (
            "claude plugin marketplace add earthtojake/text-to-cad#latest",
            "codex plugin marketplace add earthtojake/text-to-cad --ref latest",
            "qoder plugins marketplace add earthtojake/text-to-cad#latest",
            "git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad",
            "grok plugin install earthtojake/text-to-cad@latest",
            "gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest",
            "npx skills add earthtojake/text-to-cad#latest",
        )
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        site = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        for command in commands:
            with self.subTest(command=command):
                self.assertIn(command, readme)
                self.assertIn(command, site)

    def test_codex_starts_the_cad_server_pinned_in_the_threads_workspace(self) -> None:
        # One uniquely named server (a host allowlists servers by name), run by uvx from the
        # runtime this plugin version pins. Not offline: the first start after an install or an
        # update downloads that runtime, given the time to (an offline start of an uncached pin
        # fails). No `cwd`: Codex then starts each thread's server in that thread's workspace.
        manifest = load_json(CODEX_PLUGIN_PATH)
        self.assertEqual(manifest.get("mcpServers"), "./codex.mcp.json")
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

    def test_qoder_starts_the_cad_server_and_loads_canonical_skills(self) -> None:
        manifest = load_json(QODER_PLUGIN_PATH)
        self.assertEqual(manifest.get("skills"), "./skills/")
        self.assertEqual(manifest.get("mcpServers"), "./qoder.mcp.json")
        qoder, claude = load_json(QODER_MCP_PATH)["mcpServers"]["cad"], load_json(CLAUDE_MCP_PATH)["mcpServers"]["cad"]
        self.assertEqual(list(load_json(QODER_MCP_PATH)["mcpServers"]), ["cad"])
        self.assertEqual({**qoder, "env": None}, {**claude, "env": None})

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

    def test_the_agent_plugins_manifest_starts_claudes_server(self) -> None:
        # plugin.json and mcp.json are the Agent Plugins standard's (agent-plugins.org), whose schemas are
        # closed: the manifest takes only these fields, and mcp.json names each server's transport. VS Code
        # reads them before Claude's manifest. Cursor reads .cursor-plugin/plugin.json first, and merges a root
        # mcp.json into the config that manifest names, keeping the manifest's server of the same name: both
        # name it `cad`, so Cursor starts one. The server's channel is the standard's, not an app's.
        manifest = load_json(PLUGIN_PATH)
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        self.assertLessEqual(set(manifest), {"$schema", "name", "version", "description", "author", "homepage",
                                             "repository", "license", "keywords", "extensions"})
        self.assertLessEqual(set(manifest["author"]), {"name", "email", "url"})
        self.assertEqual(manifest["keywords"], load_json(CURSOR_PLUGIN_PATH)["keywords"])
        config = load_json(MCP_PATH)
        self.assertEqual(config, {"$schema": "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json",
                                  "mcpServers": config["mcpServers"]})
        self.assertEqual(list(config["mcpServers"]), list(load_json(CURSOR_MCP_PATH)["mcpServers"]))
        server, claude = config["mcpServers"]["cad"], load_json(CLAUDE_MCP_PATH)["mcpServers"]["cad"]
        self.assertEqual({**server, "env": None}, {**claude, "type": "stdio", "env": None})
        self.assertEqual(load_json(CURSOR_PLUGIN_PATH).get("mcpServers"), "./cursor.mcp.json")

    def test_gemini_extension_names_the_plugin_and_starts_claudes_server(self) -> None:
        # Gemini CLI reads gemini-extension.json at the root (and its skills/), and runs servers
        # from the manifest itself: Claude's server, pinned to this release, under the same name,
        # naming its own channel.
        manifest = load_json(GEMINI_EXTENSION_PATH)
        self.assertEqual(manifest.get("name"), PLUGIN_NAME)
        gemini, claude = manifest["mcpServers"]["cad"], load_json(CLAUDE_MCP_PATH)["mcpServers"]["cad"]
        self.assertEqual(list(manifest["mcpServers"]), ["cad"])
        self.assertEqual({**gemini, "env": None}, {**claude, "env": None})
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
        for path in (CLAUDE_MCP_PATH, CODEX_MCP_PATH, QODER_MCP_PATH, CURSOR_MCP_PATH, MCP_PATH,
                     GEMINI_EXTENSION_PATH):
            with self.subTest(path=path.name):
                server = load_json(path)["mcpServers"]["cad"]
                self.assertEqual((server["command"], server["args"]), (LAUNCHER[0], expected))
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn('"args": [' + ", ".join(json.dumps(arg) for arg in expected) + "]", readme)

    def test_every_plugin_on_main_names_its_own_channel(self) -> None:
        # Each plugin's startup config names where its installs come from, in its server's
        # environment, and CADGEN_AUTO_UPDATED=1 where something keeps the copy up to date: the Cursor
        # Marketplace, which reads main, and Gemini, which updates its extension. Environment, not
        # flags: main pins the last release, and a cadgen ignores a variable it does not know but
        # refuses a flag. Nothing is worked out at runtime (cadgen's _internal/channel.py); the plugin
        # branch and the OpenAI ZIP stamp their own.
        import sys

        sys.path.insert(0, str(REPO_ROOT / "packages" / "cadgen" / "src"))
        from cadgen._internal.channel import is_channel

        said = {path.name: load_json(path)["mcpServers"]["cad"]["env"]
                for path in (CLAUDE_MCP_PATH, CODEX_MCP_PATH, QODER_MCP_PATH, CURSOR_MCP_PATH,
                             MCP_PATH, GEMINI_EXTENSION_PATH)}
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        said["README.md"] = json.loads(re.search(r'"env": (\{"CADGEN_INSTALL_CHANNEL"[^}]*\})', readme).group(1))
        self.assertEqual(said, {
            "claude.mcp.json": {"CADGEN_INSTALL_CHANNEL": "claude-github"},
            "codex.mcp.json": {"CADGEN_INSTALL_CHANNEL": "codex-github"},
            "qoder.mcp.json": {"CADGEN_INSTALL_CHANNEL": "qoder-github"},
            "cursor.mcp.json": {"CADGEN_INSTALL_CHANNEL": "cursor-marketplace", "CADGEN_AUTO_UPDATED": "1"},
            "mcp.json": {"CADGEN_INSTALL_CHANNEL": "agent-plugins"},
            "gemini-extension.json": {"CADGEN_INSTALL_CHANNEL": "gemini-github", "CADGEN_AUTO_UPDATED": "1"},
            "README.md": {"CADGEN_INSTALL_CHANNEL": "claude-desktop"},
        })
        # Every channel any package names is one the analytics receiver takes.
        receiver = (REPO_ROOT / "apps" / "api" / "src" / "events.mjs").read_text(encoding="utf-8")
        named = {env["CADGEN_INSTALL_CHANNEL"] for env in said.values()} | {"claude-directory", "cursor-github",
                                                                           "openai-directory", "dev"}
        for channel in sorted(named):
            with self.subTest(channel=channel):
                self.assertTrue(is_channel(channel))
                self.assertIn(f"'{channel}'", receiver)

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

    def test_the_docs_site_lists_only_skills_that_ship(self) -> None:
        # The site's catalog is its own copy, not read from skills/, and its build does not check
        # the links: a renamed or retired skill would leave it pointing at nothing.
        content = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        listed = re.findall(r'path: "skills/([a-z0-9-]+)"', content)
        self.assertTrue(listed, "no skill paths found in the docs site's catalog")
        self.assertEqual([name for name in listed if not (SKILLS_ROOT / name / "SKILL.md").is_file()], [])

    def test_skill_handoffs_name_skills_that_ship(self) -> None:
        # `$cad`, `$dxf`: one skill hands the agent to another by name (shell variables are upper case).
        dangling = []
        for document in sorted(SKILLS_ROOT.rglob("*.md")):
            for name in sorted(set(re.findall(r"\$([a-z][a-z0-9-]*)\b", document.read_text(encoding="utf-8")))):
                if not (SKILLS_ROOT / name / "SKILL.md").is_file():
                    dangling.append(f"{document.relative_to(REPO_ROOT)} -> ${name}")
        self.assertEqual(dangling, [])


if __name__ == "__main__":
    unittest.main()
