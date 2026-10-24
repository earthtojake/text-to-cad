"""Attach cadgen's applications to the standalone engine through its host factory.

The engine imports only itself. The distribution supplies the HTTP application and its
launcher when the engine's client/daemon modules are imported; model workers load neither app.
It also says where the user's state folder is, which the engine's registry of documents lives
in (``cadgen.engine.registry.FACTORY``: the state directory, ``cadgen.viewer.recents.state_dir``),
and the cache folder its documents' bytes are cached in (``cadgen.viewer.recents.cache_dir``).
"""
from __future__ import annotations

import sys


def http_factory(server, host, port):
    from cadgen.viewer.engine_app import EngineApp
    from cadgen.viewer.handler import CadHTTPServer, make_handler_class

    from cadgen.mcp.http import Sessions

    app = EngineApp(server, host, session_factory=Sessions)
    server.clients_active = app.active
    server.on_close = app.close
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


def _attach(module):
    if module.__name__ == "cadgen.engine.client":
        module.DAEMON_MODULE = "cadgen._internal.engine_daemon"
    elif module.__name__ == "cadgen.engine.registry":
        module.FACTORY = registry
    else:
        module.HTTP_FACTORY = http_factory


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

