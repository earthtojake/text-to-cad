"""A model must not declare one of its own outputs as a build input.

``read_step``, ``read_scene`` and ``declare_input`` put a file's content
hash in the model's closure. Pointed at a file the SAME model writes, that is
not a loop but an input that changes every time the model runs: the gate can
never say "current", every run is a full rebuild, and the geometry the model
produces depends on whatever the previous run happened to leave on disk. A
model whose body reads and re-wraps its own ``.step`` grows on every run and
exits 0 each time -- plausible-wrong output, which is the one outcome the
engine refuses to produce.

The skill reference states the rule ("Never ``read_step`` your own output ...
Input path and output path being different files is the whole rule"); this is
where it is enforced, at the two doors that record an input.
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
        f"{reader}: {resolved} is an output this model writes. Reading a file the "
        "model itself produces makes the model's own last run an input, so the gate "
        "can never say 'current' and the geometry depends on what is left on disk. "
        "Keep source documents where the model cannot write them (an 'imported/' "
        "folder beside the project), or -- when the geometry is something this "
        "project already builds -- call that model instead of reading its artifact."
    )
