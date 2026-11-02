"""``python -m cad_server.engine VERB ...``: the engine's verbs (``cli.VERBS``) as subcommands."""

import sys

from cad_server.engine.cli import main

sys.exit(main(prog="python -m cad_server.engine"))
