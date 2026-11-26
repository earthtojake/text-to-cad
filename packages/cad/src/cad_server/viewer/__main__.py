"""``python -m cad_server.viewer``: the same launcher the ``cad viewer`` front door runs."""

import sys

from .main import main

sys.exit(main(sys.argv[1:], prog="python -m cad_server.viewer"))
