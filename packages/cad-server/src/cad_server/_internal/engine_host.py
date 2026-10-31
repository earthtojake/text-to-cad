"""The server's composition root: the CAD Viewer's and the CAD app's HTTP application on the engine's
listener, and the environment the engine's kernel processes run in, which the engine makes when it is
absent.

Neither the Viewer's application nor the CAD app's server is imported by anything outside them but this
(they are the server's leaves). The engine's daemon takes its application from here
(``cad_server.engine.daemon.HTTP_FACTORY``) and tells the library's processes where the engine's kernel
processes run (``cad.engine.places.KERNEL``: the installation's base, ``cad_server._internal.base``). A
model's own process and its worker -- in the CAD kernel environment, where only the library is -- load
none of it.
"""
from __future__ import annotations

import os


def http_factory(server, host, port):
    from cad_server._internal.update import UPDATE
    from cad_server.viewer.engine_app import EngineApp
    from cad_server.viewer.handler import CadHTTPServer, make_handler_class

    from cad_server.mcp.http import Sessions

    # An update whose switch failed moments ago started this release's engine again: said as failed to the
    # page that followed it through the restart (``cad_server._internal.update.Update.recall``).
    try:
        UPDATE.recall()
    except Exception:  # noqa: BLE001 - a note for the page, never a reason the engine does not serve
        pass
    app = EngineApp(server, host, session_factory=Sessions)
    server.clients_active = app.active
    server.clients_working = app.working
    server.on_close = app.close
    server.on_hold_end = app.hold_ended
    try:
        return CadHTTPServer((host, port), make_handler_class(app), app)
    except BaseException:
        app.close()  # its analytics recorder, started with it, ends with the failed bind
        raise


def kernel(make):
    """The environment the engine's kernel processes run in (``cad_server._internal.base.kernel``)."""
    from cad_server._internal.base import kernel as made

    return made(make)


def making():
    """The engine's making of that environment when it is absent (``cad_server._internal.base.MAKING``)."""
    from cad_server._internal.base import MAKING

    return MAKING


def automatic(daemon):
    """The engine's automatic update, asked for as it tends itself (``cad_server._internal.update.Update.automatic``)."""
    try:
        from cad_server._internal.update import UPDATE

        UPDATE.automatic(daemon)
    except Exception:  # noqa: BLE001 - the engine's tending never fails for an update
        pass


def update():
    """Where the engine's update is, for its ``status`` (``cad_server._internal.update.Update.status``)."""
    try:
        from cad_server._internal.update import UPDATE

        return UPDATE.status()
    except Exception:  # noqa: BLE001 - a status line, never a reason status fails
        return None


def halt():
    """The uv commands the engine runs now stopped, as it stops (``cad_server._internal.base.halt``)."""
    from cad_server._internal.base import halt as stop

    stop()


# The variables an agent host sets in the shells it runs a command in, which name it there as
# ``cad_server.mcp.host.family`` names it from its process: Codex's (seen with ``env`` in codex-cli
# 0.163's ``exec`` and ``sandbox`` shells), then Claude Code's. Codex first: a Codex started from a
# Claude Code shell inherits Claude Code's.
SHELLS = (("codex", ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_TOOL_CALL_ID", "CODEX_SANDBOX")),
          ("claude code", ("CLAUDECODE",)))


def shell(environ=None) -> str | None:
    """The host whose shell this is, from its environment (``SHELLS``), or None."""
    environ = os.environ if environ is None else environ
    for name, variables in SHELLS:
        if any(environ.get(variable) for variable in variables):
            return name
    return None
