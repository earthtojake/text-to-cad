"""KiCad's refill of a board's zones, on a copy: what the plot draws its pours from (``formats.kicad.poured``).

``refill(board, out_dir)`` copies the board, and its ``.kicad_pro`` and ``.kicad_dru`` (the rules a fill
keeps clear by), into ``out_dir``, opens the copy in a private headless ``kicad-cli api-server``
(``_session``: kicode's kicad-cli and KiPy), refills every zone and saves the copy; the person's file is
never opened by KiCad. ``python -m cad.kicad._refill BOARD OUT_DIR`` runs it for the engine, in the
environment of ``cad[kicad]``, and prints the refilled file's path.
"""

from __future__ import annotations

import contextlib
import io
import shutil
import sys
from pathlib import Path

__all__ = ["REFILL_SECONDS", "refill"]

#: How long KiCad may take to refill a board's zones.
REFILL_SECONDS = 600.0

_BESIDE = (".kicad_pro", ".kicad_dru")


def refill(board: Path | str, out_dir: Path | str) -> Path:
    """KiCad's refill of ``board``'s zones, written as a copy in ``out_dir``: the copy's path."""
    from ._session import BoardScript, run

    board, out_dir = Path(board).resolve(), Path(out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    copy = out_dir / board.name
    shutil.copyfile(board, copy)
    for suffix in _BESIDE:
        if board.with_suffix(suffix).is_file():
            shutil.copyfile(board.with_suffix(suffix), copy.with_suffix(suffix))

    def refilled(opened) -> None:
        opened.refill_zones(block=True, max_poll_seconds=REFILL_SECONDS)

    # The copy is saved in the format of the KiCad that ran it, which a copy needs no word about.
    with contextlib.redirect_stderr(io.StringIO()):
        run(BoardScript(refilled, copy))
    return copy


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 2:
        print("usage: python -m cad.kicad._refill BOARD OUT_DIR", file=sys.stderr)
        return 2
    try:
        print(refill(args[0], args[1]))
    except Exception as error:  # noqa: BLE001 - the engine says it in the payload
        print(str(error).strip() or type(error).__name__, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
