"""Migration error for the removed inspect module entry point."""
from cadgen.cli.step_inspect.cli import main

raise SystemExit(main())
