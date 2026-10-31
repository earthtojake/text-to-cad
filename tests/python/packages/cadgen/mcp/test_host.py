"""Which host launched the stdio transport, read from its parent processes (``cad_mcp.host``), and what
decides how a host presents CAD (the server's ``cadgen.mcp.host``)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest

from cad_mcp import host as launcher
from cadgen.mcp import host

# Parent chains as the hosts start the server, nearest first (measured on macOS, 2026-10-24).
UVX = ["/Users/u/.local/bin/uv", "tool", "uvx", "--no-config", "--managed-python", "--python", "3.13", "--from",
       "cadgen==0.8.0", "cadgen", "mcp"]
NPM_CODEX = "/Users/u/.local/lib/node_modules/@openai/codex/node_modules/@openai/codex-darwin-arm64/vendor/aarch64-apple-darwin/bin/codex"
CODEX_EXEC = [[NPM_CODEX, "exec", "--skip-git-repo-check", "-c", "mcp_servers.cad.command=\"uvx\"", "Model a cube"],
              ["node", "/Users/u/.local/bin/codex", "exec", "--skip-git-repo-check", "Model a cube"], ["/bin/zsh"]]
CODEX_TUI = [[NPM_CODEX, "-c", "mcp_servers.cad.command=\"uvx\""], ["node", "/Users/u/.local/bin/codex"], ["/bin/zsh"]]
CODEX_APP = [["/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex", "-c",
              "features.code_mode_host=true", "app-server", "--analytics-default-enabled"],
             ["/Applications/ChatGPT.app/Contents/MacOS/ChatGPT"]]
CLAUDE_CLI = "/Users/u/Library/Application Support/Claude/claude-code/2.1.299/4fa9694b7975/claude.app/Contents/MacOS/claude"
CLAUDE_CODE = [[CLAUDE_CLI, "--output-format", "stream-json", "--verbose"],
               ["/Applications/Claude.app/Contents/Helpers/disclaimer", "--pgroup", "--", CLAUDE_CLI],
               ["/Applications/Claude.app/Contents/MacOS/Claude"]]
CLAUDE_DESKTOP = [["/Applications/Claude.app/Contents/Frameworks/Claude Helper.app/Contents/MacOS/Claude Helper",
                   "--type=utility", "--utility-sub-type=node.mojom.NodeService"], ["/Applications/Claude.app/Contents/MacOS/Claude"]]


class LauncherTest(unittest.TestCase):
    def test_each_host_is_named_by_its_program_and_subcommand_past_what_launched_the_server(self) -> None:
        for chain, named, renders in (
                (CODEX_EXEC, "codex exec", False),
                ([["/bin/sh", "-c", "uvx cadgen mcp"], UVX, *CODEX_EXEC], "codex exec", False),
                ([CODEX_EXEC[1]], "codex exec", False),  # an npm install's node script, where it runs codex itself
                (CODEX_TUI, "codex", False),
                ([[NPM_CODEX, "--model", "gpt-6-astra", "make a cube"]], "codex", False),  # a prompt is not a subcommand
                ([[NPM_CODEX, "resume", "--last"]], "codex resume", False),
                ([UVX, *CODEX_APP], "codex app-server", True),
                ([["codex", "app-server"]], "codex app-server", True),
                ([UVX, *CLAUDE_CODE], "claude code", False),
                (CLAUDE_DESKTOP, "claude desktop", True),
                (CLAUDE_DESKTOP[1:], "claude desktop", True),
                ([[], *CODEX_EXEC], "codex exec", False),  # a parent exiting as it was read: past it  # its own program nearest: never Claude Code
                ([["/opt/homebrew/bin/python3.13", "-m", "unittest"], *CLAUDE_CODE], "python3.13", None)):
            with self.subTest(named=named, nearest=chain[0][:1]):
                found = launcher.host_of(chain)
                self.assertEqual((found["host"], found["renders"]), (named, renders))
        self.assertIsNone(launcher.host_of([UVX, ["/bin/zsh"]]))
        self.assertIsNone(launcher.host_of([]))

    def test_a_container_whose_entrypoint_is_the_host_names_it(self) -> None:
        import io
        from unittest import mock

        # /proc as a container shows it: the server's parent is uv, whose parent is pid 1, the host.
        proc = {7: (b"/root/.local/bin/uv\0tool\0uvx\0cadgen\0mcp\0", b"7 (uv) S 1 7 7 0"),
                1: (b"codex\0app-server\0", b"1 (codex) S 0 1 1 0")}

        def read(path: str, _mode: str = "r"):
            _root, _proc, pid, kind = path.split("/")
            return io.BytesIO(proc[int(pid)][0 if kind == "cmdline" else 1])

        with mock.patch.object(launcher, "open", read, create=True):
            chain = launcher._ancestors_linux(7)
        self.assertEqual(chain, [["/root/.local/bin/uv", "tool", "uvx", "cadgen", "mcp"], ["codex", "app-server"]])
        self.assertEqual(launcher.host_of(chain)["host"], "codex app-server")
        # An init the walk ends at, which started the launcher, is no host: none is known.
        for init in (["/sbin/init", "splash"], ["/usr/lib/systemd/systemd", "--switched-root"], ["/sbin/tini", "--"]):
            self.assertIsNone(launcher.host_of([UVX, init]), init)

    @unittest.skipUnless(sys.platform == "darwin" or sys.platform.startswith("linux"), "read on macOS and Linux")
    def test_a_parent_is_read_with_its_arguments_exactly(self) -> None:
        child = "import json; from cad_mcp.host import ancestors; print(json.dumps(ancestors()[0]))"
        parent = f"import subprocess, sys; sys.exit(subprocess.run([sys.executable, '-c', {child!r}]).returncode)"
        done = subprocess.run([sys.executable, "-c", parent, "exec", "two words"], capture_output=True, text=True, timeout=30)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)[-3:], [parent, "exec", "two words"])


class PresentationTest(unittest.TestCase):
    CODEX = {"name": "codex-mcp-client", "title": "Codex"}
    OTHER = {"name": "some-host"}
    UI = {"extensions": {host.UI_EXTENSION: {"mimeTypes": [host.MIME]}}}
    TABS = {"extensions": {host.TABS_EXTENSION: {"entrypoints": ["global", "thread", "file"]}}}

    def test_a_declaration_then_the_launcher_then_the_name_and_the_name_never_claims_a_tab(self) -> None:
        # What the transport reads of each launcher (``cad_mcp.host.host_of``), as it hands it to the server.
        execd = {"host": "codex exec", "renders": False}
        app = {"host": "codex app-server", "renders": True}
        claude = {"host": "claude code", "renders": False}
        for client, offered, launched, expected in (
                (self.OTHER, self.TABS, execd, ("tabs", True)),      # what a host declares wins
                (self.CODEX, self.UI, execd, ("tabs", True)),        # Codex shows what it renders as tabs
                (self.OTHER, self.UI, claude, ("inline", True)),     # Claude Code with CLAUDE_CODE_MCP_APPS_HOST=1
                (self.CODEX, {}, execd, ("text", False)),            # codex exec, whatever its calls carry
                (self.CODEX, {}, {"host": "codex", "renders": False}, ("text", False)),
                (self.CODEX, {}, app, ("tabs", True)),               # the Codex app
                (self.CODEX, {}, None, ("tabs", None)),              # the name alone: Codex's catalog, no claim
                (self.CODEX, {}, claude, ("tabs", None)),            # a launcher that is not Codex says nothing of it
                (self.OTHER, {}, claude, ("text", False)),
                (self.OTHER, {}, None, ("text", False))):
            with self.subTest(client=client["name"], offered=list(offered.get("extensions", {})), launched=(launched or {}).get("host")):
                self.assertEqual(host.presentation(client, offered, launched)[:2], expected)

    def test_a_codex_exec_turn_is_told_by_its_metadata(self) -> None:
        self.assertTrue(host.headless({"x-codex-turn-metadata": {"turn_trigger": "exec"}}))
        self.assertFalse(host.headless({"x-codex-turn-metadata": {"sandbox": "seatbelt"}}))
        self.assertFalse(host.headless({}))


if __name__ == "__main__":
    unittest.main()
