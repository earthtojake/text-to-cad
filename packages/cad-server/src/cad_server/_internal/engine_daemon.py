"""The server's engine process: the daemon, its HTTP application the server's (``cad_server.engine.daemon``,
``cad_server._internal.engine_host``). ``--proof``: its start sequence up to ready to serve, then gone
(``daemon.proof``, a version's proof before its channel moves to it)."""
import sys

from cad_server.engine.daemon import main, proof

if __name__ == "__main__":
    raise SystemExit(proof() if sys.argv[1:] == ["--proof"] else main())
