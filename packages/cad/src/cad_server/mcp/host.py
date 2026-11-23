"""Which apps are offered CAD's tools, from what their initialize and their calls carry.

CAD's tools show models as views in the app, and the one app whose CAD view is verified is the Codex app (a
tab beside the thread). So the Codex app alone is offered them: every other app, whatever it declares, is
offered no tools at all and shows a model the way it shows any web page (the ``cad viewer`` link).

The Codex app greets the server as ``codex-mcp-client``, and so do ``codex exec`` and the Codex terminal UI,
which show no views; from 0.169 the app and perhaps the others declare the ``io.modelcontextprotocol/ui``
extension too, so neither the name nor the declaration tells them apart. The stdio transport that Codex
started says which program launched it, read from its parent processes (``cad_mcp.host.launcher``), and hands
it to the server with the initialize (``launcher``): that decides. Where it cannot be read (Windows, a
wrapper), a Codex is offered tabs, and a call made in a ``codex exec`` turn says so in its metadata
(``headless``), which comes before any declaration.

``CAD_MCP_PRESENTATION=inline|tabs|text`` in the transport's environment (``told``) forces a presentation on
any client: a development switch, for testing the page's other ways of being shown.
"""
from __future__ import annotations

from typing import Any

UI_EXTENSION = "io.modelcontextprotocol/ui"
MIME = "text/html;profile=mcp-app"  # an MCP App's page, which the ui extension lists
CODEX_CLIENT = "codex-mcp-client"
# Cursor's MCP client (``cursor-vscode``, from its cursor-mcp extension's ``createSdkClient``). Its card is
# handed a result Cursor rebuilt from its transcript, ``content`` and ``structuredContent`` alone, so a
# launch's ``_meta`` never reaches it: Cursor's card takes its capability from its tool's (``carries_capability``).
# Reached only through the development switch: Cursor is offered no tools.
CURSOR_CLIENT = "cursor-vscode"
# The presentations the development switch can force (``told``).
PRESENTATIONS = frozenset({"inline", "tabs", "text"})

# Where a Codex call says its turn shows no app: ``codex exec`` (and its ``resume``) runs the turn
# headless, though it greets the server as the Codex app does. Seen from the 0.163 app server's
# binary; codex-cli 0.153 sends no such field, which is why the launcher is read too.
CODEX_TURN = "x-codex-turn-metadata"
HEADLESS_TRIGGERS = frozenset({"exec"})


def _declares_views(offered: dict[str, Any]) -> bool:
    extensions = offered.get("extensions") if isinstance(offered.get("extensions"), dict) else {}
    ui = extensions.get(UI_EXTENSION)
    return isinstance(ui, dict) and MIME in (ui.get("mimeTypes") or [])


def presentation(client: dict[str, Any], offered: dict[str, Any], launched: Any,
                 told: Any = None) -> tuple[str, bool | None, str]:
    """How an app is served CAD, from its initialize: ``(presentation, renders, why)``. ``presentation`` is
    ``tabs`` (the Codex app's catalog), ``inline`` (the development switch alone) or ``text`` (no tools);
    ``renders`` whether it shows CAD views, None where nothing says yet (a Codex whose launcher is unknown and
    that declares nothing: a view reaching the server, or a call, will); ``why`` the evidence, in words for the
    log."""
    if told in PRESENTATIONS:
        return told, told != "text", f"CAD_MCP_PRESENTATION={told}"
    if client.get("name") != CODEX_CLIENT:
        return "text", False, "not the Codex app: only its CAD view is verified"
    if isinstance(launched, dict) and str(launched.get("host", "")).startswith("codex"):
        renders = launched.get("renders")
        if renders is False:
            return "text", False, f"named codex, launched by {launched.get('host')}, which shows no CAD views"
        why = f"named codex, launched by {launched.get('host')}"
    else:
        renders, why = None, "named codex, launched by an unknown host"  # another program's word says nothing of Codex
    if renders is None and _declares_views(offered):
        renders, why = True, f"{why}, declares MCP Apps"
    return "tabs", renders, why


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
