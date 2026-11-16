"""How a host presents CAD: the evidence its initialize and its calls carry, weighed.

A host's greeting does not always say whether it shows CAD cards: Codex greets the server as
``codex-mcp-client`` and declares no MCP Apps extension from its desktop app (which shows them as
tabs), from ``codex exec`` or from its terminal UI (which show none), and Claude Code's terminal
declares none either. The stdio transport that host started does say which host launched it, read
from its parent processes (``cad_mcp.host.launcher``), and hands it to the server with the host's
initialize (``launcher``).

What decides, strongest first (``presentation`` at initialize, then the server at each call): an
extension the host declares; a view that reached the server (only a host that shows cards draws
one); the call's own metadata (a ``codex exec`` turn says ``turn_trigger: exec``); the host that
launched the shim; and last the client's name, which never on its own claims that a tab opened.
"""
from __future__ import annotations

from typing import Any

UI_EXTENSION = "io.modelcontextprotocol/ui"
TABS_EXTENSION = "dev.texttocad/tabs"
TAB_ENTRYPOINTS = frozenset({"global", "thread", "file"})
MIME = "text/html;profile=mcp-app"  # an MCP App's page, which the ui extension lists
CODEX_CLIENT = "codex-mcp-client"
# Cursor's MCP client (``cursor-vscode``, from its cursor-mcp extension's ``createSdkClient``). Its card is
# handed a result Cursor rebuilt from its transcript, ``content`` and ``structuredContent`` alone, so a
# launch's ``_meta`` never reaches it: Cursor's card takes its capability from its tool's (``carries_capability``).
CURSOR_CLIENT = "cursor-vscode"

# Where a Codex call says its turn shows no app: ``codex exec`` (and its ``resume``) runs the turn
# headless, though it greets the server as the Codex app does. Seen from the 0.163 app server's
# binary; codex-cli 0.153 sends no such field, which is why the launcher is read too.
CODEX_TURN = "x-codex-turn-metadata"
HEADLESS_TRIGGERS = frozenset({"exec"})


def presentation(client: dict[str, Any], offered: dict[str, Any], launched: Any) -> tuple[str, bool | None, str]:
    """How a host presents CAD, from its initialize: ``(presentation, renders, why)``. ``presentation``
    is ``tabs``, ``inline`` or ``text``, the catalog the host is listed; ``renders`` whether it shows
    CAD cards, None where nothing says yet (a view reaching the server, or a call, will); ``why`` the
    evidence, in words for the log."""
    extensions = offered.get("extensions") if isinstance(offered.get("extensions"), dict) else {}
    declared = extensions.get(TABS_EXTENSION)
    entrypoints = declared.get("entrypoints") if isinstance(declared, dict) else None
    if isinstance(entrypoints, list) and TAB_ENTRYPOINTS <= set(entrypoints):
        return "tabs", True, "declared tabs"
    codex = client.get("name") == CODEX_CLIENT  # Codex presents what it renders as tabs, never inline
    if codex and not (isinstance(launched, dict) and str(launched.get("host", "")).startswith("codex")):
        launched = None  # a Codex client another program launched: that program says nothing of Codex
    ui = extensions.get(UI_EXTENSION)
    if isinstance(ui, dict) and MIME in (ui.get("mimeTypes") or []):
        return ("tabs" if codex else "inline"), True, "declared apps"
    renders = launched.get("renders") if isinstance(launched, dict) else None
    if renders is not None:
        shown = ("tabs" if codex else "inline") if renders else "text"
        return shown, renders, f"launched by {launched.get('host')}"
    if codex:
        return "tabs", None, "named codex, launched by " + (str(launched.get("host")) if isinstance(launched, dict) else "an unknown host")
    return "text", False, "no extension, no known launcher"


def carries_capability(client: dict[str, Any], presentation: str) -> bool:
    """Whether the launching tool's own metadata carries the page's capability: Cursor's inline cards alone.
    Cursor drops a tool result's ``_meta`` before its card sees it (it rebuilds the result from its
    transcript), and hands the card the tool that launched it in ``ui/initialize``'s host context
    (``toolInfo.tool``, its ``_meta`` whole). A tool's ``_meta`` is the host's, as a result's is: Cursor's agent
    reads its tools from descriptors that carry name, description and arguments, never ``_meta``. Every
    other host reads the capability from the launch's result, as before."""
    return client.get("name") == CURSOR_CLIENT and presentation == "inline"


def claude_code(transport: Any) -> bool:
    """Whether Claude Code started the session's transport, which then lists no tools: the transport saw
    ``CLAUDE_CODE_ENTRYPOINT`` in its own environment (``claudeCode``, which Claude Code sets for every server
    it starts, its terminal's and the desktop app's Code tab's), and was not told ``CAD_MCP_CARDS=1``
    (``cards``), which keeps CAD's tools there for testing. A server Claude Desktop starts from its own
    config, which its Code tab also offers, never sees the variable, so it keeps every tool."""
    if not isinstance(transport, dict):
        return False
    return bool(transport.get("claudeCode")) and transport.get("cards") is not True


def headless(meta: Any) -> bool:
    """Whether a Codex call comes from a turn that shows no app (``codex exec``)."""
    turn = meta.get(CODEX_TURN) if isinstance(meta, dict) else None
    return isinstance(turn, dict) and turn.get("turn_trigger") in HEADLESS_TRIGGERS
