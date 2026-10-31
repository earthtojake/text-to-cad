"""The server's composition root: the CAD Viewer's and the CAD app's HTTP application on the engine's
listener, and the environment the engine's kernel processes run in.

Neither the Viewer's application nor the CAD app's server is imported by anything outside them but this
(they are the server's leaves). The engine's daemon takes its application from here
(``cadgen.engine.daemon.HTTP_FACTORY``) and tells the library's processes where the engine's kernel
processes run (``cadgen.engine.places.KERNEL``: the installation's base, ``cadgen._internal.base``). A
model's own process and its worker -- in the CAD kernel environment, where only the library is -- load
none of it.
"""
from __future__ import annotations

import os


def http_factory(server, host, port):
    from cadgen.viewer.engine_app import EngineApp
    from cadgen.viewer.handler import CadHTTPServer, make_handler_class

    from cadgen.mcp.http import Sessions

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
    """The environment the engine's kernel processes run in (``cadgen._internal.base.kernel``)."""
    from cadgen._internal.base import kernel as made

    return made(make)


# The variables an agent host sets in the shells it runs a command in, which name it there as
# ``cadgen.mcp.host.family`` names it from its process: Codex's (seen with ``env`` in codex-cli
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
