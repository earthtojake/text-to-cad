"""Which apps are offered CAD's tools, from what their initialize and their calls carry.

CAD's tools show models as views in the app (tabs or cards), so an app is offered them only when it says it
shows MCP Apps: it declares the ``io.modelcontextprotocol/ui`` extension with CAD's page type, or
``dev.texttocad/tabs``. An app that declares neither is offered no tools at all, and shows models the way it
shows any web page (the ``cad viewer`` link).

Codex is the one exception: its desktop app shows CAD tabs and declares nothing, and so do ``codex exec`` and
its terminal UI, which show none, all greeting the server as ``codex-mcp-client``. The stdio transport that
Codex started says which program launched it, read from its parent processes (``cad_mcp.host.launcher``), and
hands it to the server with the initialize (``launcher``); a call made in a ``codex exec`` turn says so in its
metadata (``headless``).

An app on the tested-as-broken list (``BROKEN``) is offered no tools whatever it declares.
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

# The apps tested to show no CAD views, whatever they declare: offered no tools until their views are verified,
# by the name their MCP client gives. Claude Code (its terminal, and the desktop app's Code tab, which runs it)
# is also told by ``CLAUDE_CODE_ENTRYPOINT``, which it sets in every server it starts (``broken``).
BROKEN = {"claude-code": "Claude Code"}

# Where a Codex call says its turn shows no app: ``codex exec`` (and its ``resume``) runs the turn
# headless, though it greets the server as the Codex app does. Seen from the 0.163 app server's
# binary; codex-cli 0.153 sends no such field, which is why the launcher is read too.
CODEX_TURN = "x-codex-turn-metadata"
HEADLESS_TRIGGERS = frozenset({"exec"})


def presentation(client: dict[str, Any], offered: dict[str, Any], launched: Any) -> tuple[str, bool | None, str]:
    """How an app is served CAD, from its initialize: ``(presentation, renders, why)``. ``presentation`` is
    ``tabs`` or ``inline`` (the catalog it is offered) or ``text`` (no tools); ``renders`` whether it shows CAD
    views, None where nothing says yet (a Codex whose launcher is unknown: a view reaching the server, or a
    call, will); ``why`` the evidence, in words for the log."""
    extensions = offered.get("extensions") if isinstance(offered.get("extensions"), dict) else {}
    declared = extensions.get(TABS_EXTENSION)
    entrypoints = declared.get("entrypoints") if isinstance(declared, dict) else None
    if isinstance(entrypoints, list) and TAB_ENTRYPOINTS <= set(entrypoints):
        return "tabs", True, "declared tabs"
    codex = client.get("name") == CODEX_CLIENT  # Codex presents what it renders as tabs, never inline
    ui = extensions.get(UI_EXTENSION)
    if isinstance(ui, dict) and MIME in (ui.get("mimeTypes") or []):
        return ("tabs" if codex else "inline"), True, "declared apps"
    if not codex:
        return "text", False, "declares no MCP Apps support"
    if not (isinstance(launched, dict) and str(launched.get("host", "")).startswith("codex")):
        return "tabs", None, "named codex, launched by an unknown host"  # another program's word says nothing of Codex
    renders = launched.get("renders")
    if renders is False:
        return "text", False, f"named codex, launched by {launched.get('host')}, which shows no CAD views"
    return "tabs", renders, f"named codex, launched by {launched.get('host')}"


def broken(client: dict[str, Any], transport: Any) -> str | None:
    """The app's name where it is on the tested-as-broken list (``BROKEN``), else None: by its client's name, or
    Claude Code by ``CLAUDE_CODE_ENTRYPOINT`` in the transport's environment (``claudeCode``). ``CAD_MCP_CARDS=1``
    there (``cards``) keeps the tools, for testing."""
    transport = transport if isinstance(transport, dict) else {}
    if transport.get("cards") is True:
        return None
    name = client.get("name")
    if isinstance(name, str) and name in BROKEN:
        return BROKEN[name]
    return "Claude Code" if transport.get("claudeCode") else None


def carries_capability(client: dict[str, Any], presentation: str) -> bool:
    """Whether the launching tool's own metadata carries the page's capability: Cursor's inline cards alone.
    Cursor drops a tool result's ``_meta`` before its card sees it (it rebuilds the result from its
    transcript), and hands the card the tool that launched it in ``ui/initialize``'s host context
    (``toolInfo.tool``, its ``_meta`` whole). A tool's ``_meta`` is the host's, as a result's is: Cursor's agent
    reads its tools from descriptors that carry name, description and arguments, never ``_meta``. Every
    other host reads the capability from the launch's result, as before."""
    return client.get("name") == CURSOR_CLIENT and presentation == "inline"


def headless(meta: Any) -> bool:
    """Whether a Codex call comes from a turn that shows no app (``codex exec``)."""
    turn = meta.get(CODEX_TURN) if isinstance(meta, dict) else None
    return isinstance(turn, dict) and turn.get("turn_trigger") in HEADLESS_TRIGGERS
