"""The sender and the receiver of telemetry name an agent app by one rule (schema 11's `app`).

The server detects the app a batch's counts came from (`cad_server._internal.engine_host.app`) and the receiver
works it out again for a batch of schema 10 or earlier from the MCP client's name it sent (`apps/api/src/events.mjs`,
`appOfClient`). Both read the same table of client names and reduce any other name the same way: held equal here,
the receiver's table read out of its source.
"""

from __future__ import annotations

import json
import re
import unittest

from tests.python.support.paths import REPO_ROOT, add_sources

add_sources()

from cad_server._internal import engine_host  # noqa: E402

RECEIVER = REPO_ROOT / "apps" / "api" / "src" / "events.mjs"


def _literal(name: str, opening: str, closing: str) -> str:
    text = RECEIVER.read_text(encoding="utf-8")
    found = re.search(rf"\b{name}\s*=\s*(?:new Set\()?\{opening}(.*?)\{closing}", text, re.S)
    if found is None:
        raise AssertionError(f"{RECEIVER} has no {name} literal")
    return found.group(1)


class TheAppRuleIsOne(unittest.TestCase):
    def test_the_client_names_table_is_the_receiver_s(self) -> None:
        body = _literal("AGENT_APPS", "{", "}")
        pairs = re.findall(r"""(?:['"]([^'"]+)['"]|([A-Za-z0-9_.-]+))\s*:\s*['"]([^'"]+)['"]""", body)
        self.assertEqual({quoted or bare: app for quoted, bare, app in pairs}, engine_host.APPS)
        names = json.loads("[" + _literal("NO_APP", "[", "]").replace("'", '"') + "]")
        self.assertEqual(set(names), set(engine_host.NO_APP))

    def test_any_other_name_is_reduced_to_a_token_and_the_shell_decides_none(self) -> None:
        self.assertEqual(engine_host.app("Claude-AI"), "claude-desktop")
        self.assertEqual(engine_host.app("  Zed Editor (preview) "), "zed-editor-preview-")
        self.assertEqual(engine_host.app("__vscode"), "vscode")
        # The names Gemini CLI, Grok Build and VS Code call themselves: their apps' canonical tokens.
        self.assertEqual([engine_host.app(name) for name in ("gemini-cli", "Grok-Build", "Visual Studio Code")],
                         ["gemini", "grok", "vscode"])
        self.assertEqual(engine_host.app("x" * 50), "x" * 40)
        # No client, the browser viewer, or a name with nothing left: the app whose shell markers are set, else none.
        for client in (None, "cad-viewer", "cadgen-viewer", "unknown", "!!!"):
            self.assertEqual(engine_host.app(client, {"CLAUDECODE": "1"}), "claude-code", client)
            self.assertIsNone(engine_host.app(client, {}), client)
        self.assertEqual(engine_host.app(None, {"CODEX_THREAD_ID": "t", "CLAUDECODE": "1"}), "codex")
        token = re.compile(r"[a-z0-9][a-z0-9._-]{0,39}")
        for value in [*engine_host.APPS.values(), *(name for name, _ in engine_host.SHELLS)]:
            self.assertRegex(value, token)


if __name__ == "__main__":
    unittest.main()
