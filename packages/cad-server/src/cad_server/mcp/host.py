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


def headless(meta: Any) -> bool:
    """Whether a Codex call comes from a turn that shows no app (``codex exec``)."""
    turn = meta.get(CODEX_TURN) if isinstance(meta, dict) else None
    return isinstance(turn, dict) and turn.get("turn_trigger") in HEADLESS_TRIGGERS
