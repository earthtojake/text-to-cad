"""The server's engine process: the daemon, its HTTP application the server's (``cad_server.engine.daemon``,
``cad_server._internal.engine_host``)."""
from cad_server.engine.daemon import main

if __name__ == "__main__":
    raise SystemExit(main())
