"""The server's engine process: the daemon, its HTTP application the server's (``cad_server.engine.daemon``,
``cad_server._internal.engine_host``). ``client.start`` runs it by this name, as releases 0.10.0 to 0.11.11 do.

First, before anything of the server is imported, cad's own update where it is due (``auto_update.at_start``): then
this process exits ``UPDATING`` and the update starts the server."""
import sys

if __name__ == "__main__":
    from cad_server._internal import auto_update

    if auto_update.at_start():
        raise SystemExit(auto_update.UPDATING)
    from cad_server.engine.daemon import main

    raise SystemExit(main(sys.argv[1:]))
