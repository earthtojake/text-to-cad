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
import subprocess
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_NAME = "text-to-cad"
MARKETPLACE_NAME = "earthtojake"

CLAUDE_PLUGIN_PATH = REPO_ROOT / ".claude-plugin" / "plugin.json"
CODEX_MCP_PATH = REPO_ROOT / "codex.mcp.json"
CODEX_PLUGIN_PATH = REPO_ROOT / ".codex-plugin" / "plugin.json"
CURSOR_PLUGIN_PATH = REPO_ROOT / ".cursor-plugin" / "plugin.json"
GROK_PLUGIN_PATH = REPO_ROOT / ".grok-plugin" / "plugin.json"
GEMINI_EXTENSION_PATH = REPO_ROOT / "gemini-extension.json"
ANTIGRAVITY_PLUGIN_PATH = REPO_ROOT / ".antigravity-plugin" / "plugin.json"
KIMI_PLUGIN_PATH = REPO_ROOT / ".kimi-plugin" / "plugin.json"
DEVIN_PLUGIN_PATH = REPO_ROOT / ".devin-plugin" / "plugin.json"
MUSE_PLUGIN_PATH = REPO_ROOT / ".muse-plugin" / "plugin.json"
MUSE_MARKETPLACE_PATH = REPO_ROOT / ".muse-plugin" / "marketplace.json"
# Every app's manifest named `text-to-cad`.
MANIFESTS = (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, CURSOR_PLUGIN_PATH, GROK_PLUGIN_PATH,
             ANTIGRAVITY_PLUGIN_PATH, KIMI_PLUGIN_PATH, DEVIN_PLUGIN_PATH, MUSE_PLUGIN_PATH)
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
        for path in MANIFESTS:
            self.assertTrue(
                path.is_file(),
                f"missing plugin manifest: {path.relative_to(REPO_ROOT)}",
            )

    def test_plugin_manifests_name_the_plugin_consistently(self) -> None:
        for path in MANIFESTS:
            manifest = load_json(path)
            self.assertEqual(
                manifest.get("name"),
                PLUGIN_NAME,
                f"{path.relative_to(REPO_ROOT)} must declare name {PLUGIN_NAME!r}",
            )

    def test_plugin_manifests_describe_the_plugin_identically(self) -> None:
        # Each host lists the plugin by its manifest's description, and the docs site keeps it as
        # its copy (llms.txt); they are one text, so an edit to one must reach them all.
        codex = load_json(CODEX_PLUGIN_PATH)
        marketplace = load_json(MARKETPLACE_PATH)
        descriptions = {
            "claude": load_json(CLAUDE_PLUGIN_PATH).get("description"),
            "codex": codex.get("description"),
            "codex interface": codex["interface"].get("longDescription"),
            "cursor": load_json(CURSOR_PLUGIN_PATH).get("description"),
            "grok": load_json(GROK_PLUGIN_PATH).get("description"),
            "gemini": load_json(GEMINI_EXTENSION_PATH).get("description"),
            "marketplace": next(e for e in marketplace["plugins"] if e.get("name") == PLUGIN_NAME).get("description"),
            "antigravity": load_json(ANTIGRAVITY_PLUGIN_PATH).get("description"),
            "kimi": load_json(KIMI_PLUGIN_PATH).get("description"),
            "kimi interface": load_json(KIMI_PLUGIN_PATH)["interface"].get("longDescription"),
            "devin": load_json(DEVIN_PLUGIN_PATH).get("description"),
            "muse": load_json(MUSE_PLUGIN_PATH).get("description"),
            "muse marketplace": next(e for e in load_json(MUSE_MARKETPLACE_PATH)["plugins"]
                                     if e.get("name") == PLUGIN_NAME).get("description"),
        }
        page = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        descriptions["docs copy"] = re.search(r'const pluginDescription =\s*"([^"]+)"', page).group(1)
        self.assertEqual(len(set(descriptions.values())), 1, descriptions)

    def test_the_readme_and_the_docs_site_install_alike(self) -> None:
        # The README and the docs site's homepage are one copy (apps/docs/README.md): the install
        # command for each system, first in Quickstart, what it does, what text-to-cad sends and the page
        # for installing by hand say the same, word for word, in both.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        page = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        commands = re.findall(r'system: "([^"]+)", language: "([^"]+)", command: "([^"]+)"', page)
        self.assertEqual([command for _, _, command in commands],
                         ["curl -fsSL https://texttocad.dev/install.sh | sh", "irm https://www.texttocad.dev/install.ps1 | iex"])
        install = readme.split("\n## 🚀 Quickstart\n\n", 1)[1]
        self.assertTrue(install.startswith(f"{commands[0][0]}:\n"), "the README's Quickstart leads with the command")
        for system, language, command in commands:
            with self.subTest(system=system):
                self.assertIn(f"{system}:\n\n```{language}\n{command}\n```", install)
        # What it does: the same sentence, however the README wraps it.
        for name in ("installSummary",):
            with self.subTest(copy=name):
                self.assertIn(re.search(rf'const {name} =\s*"([^"]+)"', page).group(1), " ".join(readme.split()))
        label, path = re.search(r'const manualInstall = \{ label: "([^"]+)", path: "([^"]+)" \}', page).groups()
        self.assertIn(f"{label}: [{path}]({path})", readme)
        self.assertTrue((REPO_ROOT / path).is_file(), path)

    def test_the_install_short_link_reaches_the_homepage_install_box(self) -> None:
        # texttocad.dev/install is the short link to the install box in the hero (`#install`): the docs
        # site redirects it, so moving the anchor or dropping the redirect breaks the link.
        config = (REPO_ROOT / "apps" / "docs" / "next.config.ts").read_text(encoding="utf-8")
        self.assertIn('{ source: "/install", destination: "/#install"', config)
        hero = (REPO_ROOT / "apps" / "docs" / "src" / "components" / "hero-section.tsx").read_text(encoding="utf-8")
        self.assertIn('id="install"', hero)

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
            "kimi": load_json(KIMI_PLUGIN_PATH)["interface"].get("shortDescription"),
            "muse marketplace": load_json(MUSE_MARKETPLACE_PATH).get("description"),
        }
        self.assertEqual(set(shorts.values()), {"Design 3D models"}, shorts)

    def test_plugin_manifests_point_at_the_canonical_skills_directory(self) -> None:
        for path in (CLAUDE_PLUGIN_PATH, CODEX_PLUGIN_PATH, CURSOR_PLUGIN_PATH, GROK_PLUGIN_PATH):
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
        # Muse's catalog is Claude's in its own folder: the same names, the plugin at the root.
        muse = load_json(MUSE_MARKETPLACE_PATH)
        self.assertEqual(muse.get("name"), MARKETPLACE_NAME)
        self.assertEqual([(entry["name"], entry["source"]) for entry in muse["plugins"]], [(PLUGIN_NAME, "./")])
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

        for path in (MARKETPLACE_PATH, MUSE_MARKETPLACE_PATH, *MANIFESTS, GEMINI_EXTENSION_PATH, CODEX_MCP_PATH):
            with self.subTest(path=path.name):
                self.assertFalse({"ref", "sha"} & set(keys(load_json(path))), f"{path.name} names a git ref")
        for entry in load_json(MARKETPLACE_PATH)["plugins"] + load_json(MUSE_MARKETPLACE_PATH)["plugins"]:
            self.assertIn(entry.get("source"), VALID_ROOT_SOURCES)

    def test_the_documented_commands_install_latest(self) -> None:
        # Installing by hand takes `latest`, the plugin alone, written once a release is on PyPI: every
        # app's command on the install page that can name a branch names it, each in its app's own syntax,
        # as the install script runs it (scripts/install/install.py).
        commands = (
            "claude plugin marketplace add earthtojake/text-to-cad#latest",
            "codex plugin marketplace add earthtojake/text-to-cad --ref latest",
            "git clone --depth 1 --branch latest https://github.com/earthtojake/text-to-cad",
            "grok plugin install earthtojake/text-to-cad@latest",
            "gemini extensions install https://github.com/earthtojake/text-to-cad --ref latest",
            "qwen extensions install https://github.com/earthtojake/text-to-cad --ref latest",
            "copilot plugin marketplace add earthtojake/text-to-cad#latest",
            "pi install git:github.com/earthtojake/text-to-cad@latest",
            "/plugins install https://github.com/earthtojake/text-to-cad/tree/latest",
        )
        page = (REPO_ROOT / "docs" / "install.md").read_text(encoding="utf-8")
        for command in commands:
            with self.subTest(command=command):
                self.assertIn(command, page)

    def test_codex_starts_the_cad_server_of_its_release(self) -> None:
        # One uniquely named server (a host allowlists servers by name): uvx runs cad at this plugin's release, as
        # `cad mcp`, from uv's cache, installing nothing. Not offline: the first start downloads that release. No
        # `cwd`: Codex then starts each thread's server in that thread's workspace. Every copy carries this line.
        manifest = load_json(CODEX_PLUGIN_PATH)
        self.assertEqual(manifest.get("mcpServers"), "./codex.mcp.json")
        version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        self.assertEqual(load_json(CODEX_MCP_PATH), {"mcpServers": {"cad": {
            "command": "uvx",
            "args": ["--no-config", "--managed-python", "--python", "3.14", f"cad@{version}", "mcp"],
            "startup_timeout_sec": 300,
        }}})

    def test_no_manifest_declares_a_hook(self) -> None:
        # Nothing of ours runs when a session starts: no manifest, no catalog entry and no hooks/hooks.json (Claude
        # Code, Cursor and Codex all read one there by default) declares a hook. A `cad` command that needs the
        # server and finds none says to run `cad server start`; Codex's server line starts it as `cad mcp`.
        catalogs = (MARKETPLACE_PATH, MUSE_MARKETPLACE_PATH)
        for path in (*MANIFESTS, GEMINI_EXTENSION_PATH, *catalogs):
            manifest = load_json(path)
            for entry in [manifest, *(manifest.get("plugins", []) if path in catalogs else [])]:
                with self.subTest(path=str(path.relative_to(REPO_ROOT)), entry=entry.get("name")):
                    self.assertNotIn("hooks", entry)
        tracked = subprocess.run(["git", "-C", str(REPO_ROOT), "ls-files"], check=True, capture_output=True,
                                 text=True).stdout.splitlines()
        self.assertEqual([path for path in tracked if path == "hooks/hooks.json" or path.endswith("/hooks/hooks.json")], [])
        self.assertFalse((REPO_ROOT / "hooks").exists())

    def test_only_codex_s_manifest_starts_a_server(self) -> None:
        # Browser first: the CAD server ships to the one app whose CAD view is verified, the Codex app (a tab beside
        # the thread). Every other app gets the skills alone and shows a model in its own browser or by a link. No
        # server config but Codex's own: not the Agent Plugins standard's root mcp.json, which Cursor and VS Code
        # read too, and not a root .mcp.json, which Claude Code would offer to anyone who opens this repository as a
        # project. No root plugin.json either: Codex takes a folder with the Agent Plugins standard's manifest for
        # an Agent Plugin, whose server it reads from ./mcp.json alone, and ignores codex.mcp.json.
        for path in (*MANIFESTS, GEMINI_EXTENSION_PATH):
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                manifest = load_json(path)
                if path == CODEX_PLUGIN_PATH:
                    self.assertEqual(manifest.get("mcpServers"), "./codex.mcp.json")
                else:
                    self.assertFalse(manifest.get("mcpServers") or manifest.get("capabilities", {}).get("mcpServers"))
        self.assertEqual(sorted(path.name for path in REPO_ROOT.glob("*mcp*.json")), ["codex.mcp.json"])
        self.assertFalse((REPO_ROOT / ".mcp.json").exists())
        self.assertFalse((REPO_ROOT / "plugin.json").exists())

    def test_grok_build_reads_its_own_manifest_with_claude_s_fields(self) -> None:
        # Grok Build reads .grok-plugin/plugin.json before Claude's manifest, from its own install of latest and
        # from the copy Claude Code installed.
        grok, claude = load_json(GROK_PLUGIN_PATH), load_json(CLAUDE_PLUGIN_PATH)
        self.assertEqual(grok, {key: claude[key] for key in grok})

    def test_cursor_shows_its_icon(self) -> None:
        # Cursor reads only .cursor-plugin/plugin.json. Its logo must be a relative path inside the plugin tree:
        # Cursor resolves it to that commit's raw file.
        logo = load_json(CURSOR_PLUGIN_PATH).get("logo", "")
        self.assertFalse(logo.startswith(("/", "..")) or "://" in logo, logo)
        self.assertEqual(logo, ".claude-plugin/icon.png")

    def test_gemini_extension_names_the_plugin(self) -> None:
        # Gemini CLI reads gemini-extension.json at the root, and its skills/.
        manifest = load_json(GEMINI_EXTENSION_PATH)
        self.assertEqual(manifest.get("name"), PLUGIN_NAME)
        # Gemini loads the extension's GEMINI.md (or contextFileName) as the user's context; the
        # repository's own guidance (AGENTS.md) must not become it.
        self.assertNotIn("contextFileName", manifest)
        self.assertFalse((REPO_ROOT / "GEMINI.md").exists())

    def test_no_plugin_file_names_a_channel(self) -> None:
        # Every copy behaves the same: no line names a channel or who updates the copy (the variables 0.11.11
        # and earlier read, which a copy of those releases still sets, are ignored).
        for path in (*MANIFESTS, MARKETPLACE_PATH, MUSE_MARKETPLACE_PATH, GEMINI_EXTENSION_PATH, CODEX_MCP_PATH):
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                text = path.read_text(encoding="utf-8")
                for word in ("--channel", "channel", "CAD_INSTALL_CHANNEL", "CAD_AUTO_UPDATED", "--startup-timeout"):
                    self.assertNotIn(word, text)

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

    def test_the_other_apps_manifests(self) -> None:
        # Each app's own manifest, in its own documented fields, the skills alone (only Codex is given the CAD
        # server). Pi reads the skills/ folder by convention, and Hermes is given the skills in its own folder:
        # no file of their own.
        claude = load_json(CLAUDE_PLUGIN_PATH)
        antigravity = load_json(ANTIGRAVITY_PLUGIN_PATH)
        # Antigravity's schema is closed (additionalProperties: false): only its documented fields.
        self.assertLessEqual(set(antigravity), {"$schema", "name", "displayName", "description", "version", "logo",
                                                "author", "suggestedPrompts", "skills", "disabled", "homepage",
                                                "repository", "license", "keywords", "extensions"})
        self.assertRegex(antigravity["name"], r"^[a-z0-9]+(-[a-z0-9]+)*$")
        self.assertEqual(antigravity["suggestedPrompts"], load_json(CODEX_PLUGIN_PATH)["interface"]["defaultPrompt"])
        for manifest in (antigravity, load_json(DEVIN_PLUGIN_PATH)):
            self.assertEqual(manifest["logo"], ".claude-plugin/icon.png")
            self.assertNotIn("skills", manifest)  # skills/ is each one's default
        kimi = load_json(KIMI_PLUGIN_PATH)
        self.assertEqual(kimi["skills"], "./skills/")  # without it Kimi takes a root SKILL.md as the one skill
        for path in (ANTIGRAVITY_PLUGIN_PATH, KIMI_PLUGIN_PATH, DEVIN_PLUGIN_PATH):
            with self.subTest(path=str(path.relative_to(REPO_ROOT))):
                manifest = load_json(path)
                for key in ("homepage", "license", "keywords"):
                    self.assertEqual(manifest[key], claude[key], key)
        # Muse lists each skill by id and path.
        muse = load_json(MUSE_PLUGIN_PATH)
        shipped = sorted(path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md"))
        self.assertEqual(muse["capabilities"]["skills"],
                         [{"id": name, "path": f"skills/{name}/SKILL.md"} for name in shipped])
        self.assertEqual(muse["compat"], {"source": "native", "manifestDir": ".muse-plugin"})
        self.assertFalse((REPO_ROOT / "skills.sh.json").exists())

    def test_the_features_link_every_skill_and_only_pages_that_exist(self) -> None:
        # The site's Features are their own copy, not read from skills/, and its build does not check
        # the links: a renamed or retired skill would leave a feature pointing at nothing, and a new
        # skill no feature links would go unmentioned.
        content = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        # A feature links its own page and any skill its summary links inline (Fabrication services).
        paths = re.findall(r'path: "(skills/[^"#]+)(?:#[^"]*)?"', content)
        paths += re.findall(r'\]\((skills/[^)#]+)(?:#[^)]*)?\)', content)
        self.assertTrue(paths, "no feature paths found in the docs site's copy")
        self.assertEqual([path for path in paths if not (REPO_ROOT / path).is_file()], [])
        shipped = sorted(path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md"))
        self.assertEqual(sorted({path.split("/")[1] for path in paths}), shipped)

    def test_the_readme_and_the_docs_site_list_the_same_features(self) -> None:
        # The README's Features and the site's are one list (apps/docs/README.md): each feature's
        # name, the page it links and what it does, in the same order, word for word.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        content = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        page = re.findall(r'name: "([^"]+)",\s*path: "([^"]+)",\s*summary:\s*"([^"]+)"', content)
        self.assertTrue(page, "no features found in the docs site's copy")
        section = readme.split("\n## ✨ Features\n\n", 1)[1].split("\n## ", 1)[0]
        intro = re.search(r'const featuresIntro = "([^"]+)"', content).group(1)
        self.assertTrue(section.startswith(f"{intro}\n"), "the README's Features open with the site's intro")
        self.assertEqual(re.findall(r"^- \[\*\*([^*]+)\*\*\]\(([^)]+)\): (.+)$", section, re.M), page)

    def test_the_readme_and_the_docs_site_list_the_community_alike(self) -> None:
        # The README's Community and the site's are one copy (apps/docs/README.md): the intro, then a
        # bullet per project: its name, what it is, and its links side by side.
        readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        content = (REPO_ROOT / "apps" / "docs" / "src" / "lib" / "content.ts").read_text(encoding="utf-8")
        block = content.split("export const community = {", 1)[1].split("\n};", 1)[0]
        intro = re.search(r'intro: "([^"]+)"', block).group(1)
        items = re.findall(r'title: "([^"]+)",\s+body: "([^"]+)",\s+links: \[(.*?)\n      \],', block, re.S)
        self.assertTrue(items, "no Community projects found in the docs site's copy")
        lines = []
        for title, body, listed in items:
            links = re.findall(r'\{ text: "([^"]+)", href: "([^"]+)" \}', listed)
            lines.append(f"- **{title}**: {body} " + " · ".join(f"[{text}]({href})" for text, href in links))
        section = readme.split("\n## ✨ Features\n", 1)[1].split("\n## ", 2)[1]
        self.assertEqual(section.strip().split("\n"), ["🌐 Community", "", intro, "", *lines],
                         "the README's Community follows Features and lists what the site does")

    def test_skill_handoffs_name_skills_that_ship(self) -> None:
        # `$cad`, `$sendcutsend`: one skill hands the agent to another by name (shell variables are upper case).
        dangling = []
        for document in sorted(SKILLS_ROOT.rglob("*.md")):
            for name in sorted(set(re.findall(r"\$([a-z][a-z0-9-]*)\b", document.read_text(encoding="utf-8")))):
                if not (SKILLS_ROOT / name / "SKILL.md").is_file():
                    dangling.append(f"{document.relative_to(REPO_ROOT)} -> ${name}")
        self.assertEqual(dangling, [])


if __name__ == "__main__":
    unittest.main()
