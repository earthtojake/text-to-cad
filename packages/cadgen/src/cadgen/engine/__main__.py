"""``python -m cadgen.engine VERB ...``: the engine's verbs (``cli.VERBS``) as subcommands."""

import sys

from cadgen.engine.cli import main

sys.exit(main(prog="python -m cadgen.engine"))
