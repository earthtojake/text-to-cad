"""The server's engine process: the daemon, its HTTP application the server's (``cadgen.engine.daemon``,
``cadgen._internal.engine_host``)."""
from cadgen.engine.daemon import main

if __name__ == "__main__":
    raise SystemExit(main())
