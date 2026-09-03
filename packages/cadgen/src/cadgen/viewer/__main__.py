"""``python -m cadgen.viewer``: the same launcher the ``cadgen viewer`` front door runs."""

import sys

from .main import main

sys.exit(main(sys.argv[1:], prog="python -m cadgen.viewer"))
