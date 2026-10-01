"""A model must not read one of its own outputs as geometry.

A file the SAME model writes is not an input: the build records its own outputs
as written, never read. What ``read_step`` / ``read_scene`` would hand back is
whatever the previous run happened to leave on disk, so a model whose body reads
and re-wraps its own ``.step`` grows on every run and exits 0 each time --
plausible-wrong output, which is the one outcome the engine refuses to produce.

The skill reference states the rule ("Never ``read_step`` your own output ...
Input path and output path being different files is the whole rule"); this is
where it is enforced, at cadgen's two STEP readers.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["refuse_own_output"]


def _declared_outputs() -> list[Path]:
    from cadgen.authoring import current_frame

    frame = current_frame()
    if frame is None or frame.script_path is None:
        return []
    from cadgen.metadata import declared_output_paths

    return declared_output_paths(frame.script_path, function=frame.function)


def refuse_own_output(resolved: Path, *, reader: str) -> None:
    """Raise when ``resolved`` is an output of the model currently building."""
    if not any(output == resolved for output in _declared_outputs()):
        return
    raise ValueError(
        f"{reader}: {resolved} is an output this model writes. Reading it builds the "
        "model from whatever its previous run left on disk, so each run can grow on "
        "the last. "
        "Keep source documents where the model cannot write them (an 'imported/' "
        "folder beside the project), or -- when the geometry is something this "
        "project already builds -- call that model instead of reading its artifact."
    )
