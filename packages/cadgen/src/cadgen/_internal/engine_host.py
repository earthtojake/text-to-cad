"""Attach cadgen's applications to the standalone engine through its host factory.

The engine imports only itself. The distribution supplies the HTTP application and its
launcher when the engine's client/daemon modules are imported; model workers load neither app.
It also says where the user's state folder is, which the engine's registry of documents lives
in (``cadgen.engine.registry.FACTORY``: the state directory, ``cadgen.viewer.recents.state_dir``),
and the cache folder its documents' bytes are cached in (``cadgen.viewer.recents.cache_dir``). And
it gives the daemon its background work (``cadgen.engine.daemon.STARTED``): the self-update's
thread (``cadgen._internal.auto_update``). And the release the device runs, which the engine cannot
read itself (law 3): whether a newer one supersedes this engine (``cadgen.engine.daemon
.SUPERSEDED``: ``installations.newer``), what starts that release's engine in its place while pages
watch it (``cadgen.engine.daemon.SUCCESSOR``: ``auto_update.successor``), and the console script a
client's start brings up instead of its own engine (``cadgen.engine.client.CURRENT``).
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
    server.clients_quiet = app.quiet
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


def auto_update(port):
    """The self-update's thread, for the engine on ``port`` (``cadgen._internal.auto_update.start``)."""
    from cadgen._internal.auto_update import start

    return start(port)


def successor(port):
    """The current release's engine started on ``port`` in this one's place, or why not
    (``cadgen._internal.auto_update.successor``)."""
    from cadgen._internal.auto_update import successor as start

    return start(port)


def superseded():
    """Whether the device runs a release newer than this engine's (``installations.newer``)."""
    from cadgen._internal.installations import newer

    return newer() is not None


def current_script():
    """The console script of the release the device runs, when it is newer than this process's."""
    from cadgen._internal.installations import newer

    found = newer()
    return found["cadgen"] if found else None


def diagnostics_inventory():
    """The provider adapter's read-only inventory, loaded only for an explicit doctor report."""
    from cadgen.mcp.diagnostics import inventory

    return inventory()


_MODULES = {"cadgen.engine.client", "cadgen.engine.daemon", "cadgen.engine.registry", "cadgen._internal.diagnostics"}


# The agent hosts whose shells run in a sandbox that refuses the loopback port the engine's HTTP
# server needs, by the variable each sets there: Codex's Seatbelt, in its default workspace-write mode.
SANDBOXES = (("CODEX_SANDBOX_NETWORK_DISABLED", "1"),)


def _attach(module):
    if module.__name__ == "cadgen.engine.client":
        module.DAEMON_MODULE = "cadgen._internal.engine_daemon"
        module.SANDBOXES = SANDBOXES
        module.CURRENT = current_script
    elif module.__name__ == "cadgen.engine.registry":
        module.FACTORY = registry
    elif module.__name__ == "cadgen._internal.diagnostics":
        module.HOST_INVENTORY = diagnostics_inventory
    else:
        module.HTTP_FACTORY = http_factory
        module.STARTED = (auto_update,)
        module.SUCCESSOR = successor
        module.SUPERSEDED = superseded


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

