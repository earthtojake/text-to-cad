"""``python -P -m cad._internal.fea.call VERB REQUEST ANSWER``: one :mod:`cad.fea` verb, run in the CAD kernel
environment for a ``cad fea`` command whose own environment does not carry the kernel (the server's
``cad_server._internal.kernel_call``).

REQUEST is the pickled call, ``(args, kwargs)``; ANSWER is where its outcome is pickled, ``("returned", result)``
or ``("raised", error)``, so the command reports it as it reports a call in its own process. The verb's progress
goes to stderr, as it writes it; stdout is the command's, so anything printed to it here goes to stderr too.
"""

from __future__ import annotations

import contextlib
import pickle
import sys
from pathlib import Path

USAGE = "usage: python -P -m cad._internal.fea.call VERB REQUEST ANSWER"
VERBS = ("faces", "parts", "solve")


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in VERBS:
        raise SystemExit(USAGE)
    verb, request, answer = argv
    args, kwargs = pickle.loads(Path(request).read_bytes())
    from cad import fea

    with contextlib.redirect_stdout(sys.stderr):
        try:
            outcome = ("returned", getattr(fea, verb)(*args, **kwargs))
        except Exception as error:  # noqa: BLE001 -- handed to the command, which reports it
            outcome = ("raised", error)
    try:
        data = pickle.dumps(outcome)
    except Exception:  # noqa: BLE001 -- an error that does not pickle is said in its words
        data = pickle.dumps(("raised", RuntimeError(f"{type(outcome[1]).__name__}: {outcome[1]}")))
    Path(answer).write_bytes(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
