"""The r5 clipping booleans: build123d's, never cleaned (no same-domain unification),
as the native contact booleans they replace ran, whatever the caller's SkipClean."""
import build123d as bd


def _unclean(operation):
    # SkipClean's exit turns cleaning back on: set the flag and put back what it was.
    previous = bd.SkipClean.clean
    bd.SkipClean.clean = False
    try:
        return operation()
    finally:
        bd.SkipClean.clean = previous


def common(a, b):
    return _unclean(lambda: a & b)


def cut(a, b):
    return _unclean(lambda: a - b)
