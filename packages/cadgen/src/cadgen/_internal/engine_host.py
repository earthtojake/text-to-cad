"""Attach cadgen's applications to the standalone engine through its host factory.

The engine imports only itself. The distribution supplies the HTTP application and its
launcher when the engine's client/daemon modules are imported; model workers load neither app.
It also says where the user's state folder is, which the engine's registry of documents lives
in (``cadgen.engine.registry.FACTORY``: the state directory, ``cadgen.viewer.recents.state_dir``),
and the cache folder its documents' bytes are cached in (``cadgen.viewer.recents.cache_dir``).
And it makes the environment the engine's kernel processes run in (``cadgen.engine.daemon.KERNEL``:
the installation's base, ``cadgen._internal.base``), tells a process that runs in a base an
installation made which installation that is (``cadgen.engine.daemon.HOME``), and says which
installation's engine a client starts: the current one (``cadgen.engine.daemon.ENGINE``,
``cadgen._internal.installations.current``).
"""
from __future__ import annotations

import os
import sys


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


def registry():
    """The registry of documents in the user's state folder, and the cache folder its documents'
    bytes are kept in, where they are now (``CADGEN_STATE_DIR`` and ``CADGEN_CACHE_DIR`` are read
    each time)."""
    from cadgen.engine.registry import Registry
    from cadgen.viewer.recents import cache_dir, state_dir

    return Registry(state_dir(), cache=cache_dir())


_MODULES = {"cadgen.engine.client", "cadgen.engine.daemon", "cadgen.engine.registry"}


# The agent hosts whose shells run in a sandbox that refuses the loopback port the engine's HTTP
# server needs, by the variable each sets there: Codex's Seatbelt, in its default workspace-write mode.
SANDBOXES = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)


# The variables an agent host sets in the shells it runs a command in, which name it there as
# ``cadgen.mcp.host.family`` names it from its process: Codex's (seen with ``env`` in codex-cli
# 0.163's ``exec`` and ``sandbox`` shells), then Claude Code's. Codex first: a Codex started from a
# Claude Code shell inherits Claude Code's. The ``cadgen`` command reads it (``proxy``).
SHELLS = (("codex", ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_TOOL_CALL_ID", "CODEX_SANDBOX")),
          ("claude code", ("CLAUDECODE",)))


def shell(environ=None) -> str | None:
    """The host whose shell this is, from its environment (``SHELLS``), or None."""
    environ = os.environ if environ is None else environ
    for name, variables in SHELLS:
        if any(environ.get(variable) for variable in variables):
            return name
    return None


def kernel(make):
    """The environment the engine's kernel processes run in (``cadgen._internal.base.kernel``)."""
    from cadgen._internal.base import kernel as made

    return made(make)


def engine():
    """The installation whose engine a client starts (``cadgen.engine.daemon.ENGINE``): the current one
    (``cadgen._internal.installations.current``), read now, its Python and its environment; None with
    none current."""
    from cadgen._internal.installations import current

    try:
        found = current()
    except (OSError, ValueError):
        return None
    return None if found is None else {"python": found["python"], "prefix": found["prefix"], "version": found["version"]}


def _attach(module):
    if module.__name__ == "cadgen.engine.client":
        module.DAEMON_MODULE = "cadgen._internal.engine_daemon"
        module.SANDBOXES = SANDBOXES
    elif module.__name__ == "cadgen.engine.registry":
        module.FACTORY = registry
    else:
        module.HTTP_FACTORY = http_factory
        # The base the engine's kernel processes run in, and, in a base an installation made, that
        # installation: its engine is this process's.
        from cadgen._internal.base import home

        module.KERNEL = kernel
        module.HOME = home()
        module.ENGINE = engine


class _Loader:
    def __init__(self, loader):
        self.loader = loader

    def __getattr__(self, name):
        return getattr(self.loader, name)

    def create_module(self, spec):
        return self.loader.create_module(spec)

    def exec_module(self, module):
        self.loader.exec_module(module)
        _attach(module)


class _Attach:
    def find_spec(self, fullname, path=None, target=None):
        if fullname not in _MODULES:
            return None
        from importlib.machinery import PathFinder

        spec = PathFinder.find_spec(fullname, path, target)
        if spec is not None and spec.loader is not None:
            spec.loader = _Loader(spec.loader)
        return spec


def install():
    for name in sorted(_MODULES):
        if name in sys.modules:
            _attach(sys.modules[name])
    if not any(isinstance(finder, _Attach) for finder in sys.meta_path):
        sys.meta_path.insert(0, _Attach())

