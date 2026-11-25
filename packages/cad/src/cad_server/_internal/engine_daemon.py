"""The server's engine process: the daemon, its HTTP application the server's (``cad_server.engine.daemon``,
``cad_server._internal.engine_host``). ``client.start`` runs it by this name, as releases 0.10.0 to 0.11.11 do. It
starts at once: cad's own update builds beside it and switches releases once nothing is in flight
(``cad_server._internal.auto_update``) -- but where that update has a release ready, the start is the switch to it,
begun by the daemon before it serves anything (``cad_server.engine.daemon.main``)."""
import sys

if __name__ == "__main__":
    from cad_server.engine.daemon import main

    raise SystemExit(main(sys.argv[1:]))
