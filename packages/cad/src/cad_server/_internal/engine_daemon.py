"""The server's engine process: the daemon, its HTTP application the server's (``cad_server.engine.daemon``,
``cad_server._internal.engine_host``). ``client.start`` runs it by this name, as releases 0.10.0 to 0.11.10 do."""
import sys

from cad_server.engine.daemon import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
