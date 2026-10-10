"""A simulation run drawn as a picture: one panel per quantity, in a fixed palette, the same bytes each time."""

from __future__ import annotations

import io
import math
from pathlib import Path
from typing import Any

from cadgen.kicad.design import DesignError
from cadgen.kicad.waveform import Waveform

__all__ = ["plot_run"]

# A categorical palette in a fixed order (never cycled), validated for colour-vision
# deficiency on the light surface, and the chart's ink.
_SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948")
_SURFACE, _INK, _INK_2, _MUTED, _GRID, _AXIS_LINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
_SI = ((1e9, "G"), (1e6, "M"), (1e3, "k"), (1.0, ""), (1e-3, "m"), (1e-6, "\u00b5"), (1e-9, "n"), (1e-12, "p"), (1e-15, "f"))
_PLOT_SUFFIXES = (".png", ".svg", ".pdf")


def _si_scale(peak: float) -> tuple[float, str]:
    if not math.isfinite(peak) or peak <= 0:
        return 1.0, ""
    for scale, prefix in _SI:
        if peak >= scale * 0.999:
            return scale, prefix
    return _SI[-1]


def plot_run(run: Any, path: Path, voltages: list[Waveform], currents: list[Waveform], *, title: str) -> Path:
    """Draw ``run``'s waveforms: one panel per quantity (never two y-scales on one panel)."""
    import numpy
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    if path.suffix.lower() not in _PLOT_SUFFIXES:
        raise DesignError(f"plot() writes {', '.join(_PLOT_SUFFIXES)}; {path.name} has none of those suffixes")
    series = [*voltages, *currents]
    if not series:
        raise DesignError("plot() has nothing to draw: name nets=[...] or currents=[...]")
    if len(series) > len(_SERIES):
        raise DesignError(
            f"plot() draws at most {len(_SERIES)} waveforms at once, so each keeps its own colour; "
            f"this one has {len(series)}: choose them with nets=[...]"
        )
    colour = {wave.name: _SERIES[index] for index, wave in enumerate(series)}
    if run.kind == "ac":
        rows = [("Magnitude", "dB", [(wave.name, wave.db) for wave in series]), ("Phase", "deg", [(wave.name, wave.phase) for wave in series])]
    else:
        rows = ([("Voltage", "V", [(wave.name, wave) for wave in voltages])] if voltages else []) + (
            [("Current", "A", [(wave.name, wave) for wave in currents])] if currents else []
        )
    figure = Figure(figsize=(8.0, 1.0 + 2.6 * len(rows)), dpi=144, facecolor=_SURFACE, layout="constrained")
    FigureCanvasAgg(figure)
    axes = figure.subplots(len(rows), 1, sharex=True, squeeze=False)[:, 0]
    x = numpy.asarray(run.x, dtype=float)
    x_scale, x_prefix = (1.0, "") if run.kind == "ac" else _si_scale(float(numpy.max(numpy.abs(x))) if len(x) else 0.0)
    for ax, (quantity, unit, waves) in zip(axes, rows):
        ax.set_facecolor(_SURFACE)
        finite = [numpy.asarray(wave.values, dtype=float) for _name, wave in waves]
        peak = max((float(numpy.nanmax(numpy.abs(values[numpy.isfinite(values)]))) for values in finite if numpy.isfinite(values).any()), default=0.0)
        y_scale, y_prefix = _si_scale(peak) if unit in ("V", "A") else (1.0, "")
        for (name, wave), values in zip(waves, finite):
            ax.plot(x / x_scale, values / y_scale, color=colour[name], linewidth=1.0, solid_joinstyle="round", solid_capstyle="round", label=name)
        if run.kind == "ac":
            ax.set_xscale("log")
        for side in ("top", "right"):
            ax.spines[side].set_visible(False)
        for side in ("left", "bottom"):
            ax.spines[side].set_color(_AXIS_LINE)
            ax.spines[side].set_linewidth(0.5)
        ax.grid(True, which="major", color=_GRID, linewidth=0.5)
        ax.set_axisbelow(True)
        ax.tick_params(colors=_MUTED, labelcolor=_INK_2, labelsize=8, length=0)
        label = waves[0][0] if len(waves) == 1 else quantity
        ax.set_ylabel(f"{label} ({y_prefix}{unit})", color=_INK_2, fontsize=9)
        if len(waves) >= 2:
            ax.legend(loc="lower left", bbox_to_anchor=(0.0, 1.0), ncol=min(len(waves), 4), frameon=False, fontsize=8, labelcolor=_INK_2, handlelength=1.6, borderaxespad=0.2)
        if len(waves) <= 4 and run.kind != "ac":
            _end_labels(ax, x / x_scale, [(name, values / y_scale) for (name, _wave), values in zip(waves, finite)], colour, f"{y_prefix}{unit}")
    axis_label = {"transient": f"Time ({x_prefix}s)", "ac": "Frequency (Hz)", "dc_sweep": f"Swept source ({x_prefix}{run._axis[1]})"}[run.kind]
    axes[-1].set_xlabel(axis_label, color=_INK_2, fontsize=9)
    figure.suptitle(title, color=_INK, fontsize=11, x=0.01, ha="left")
    from cadgen._internal.atomic_replace import write_bytes_atomic

    picture = io.BytesIO()
    kind = path.suffix[1:].lower()
    # No "Software" stamp: the same run draws the same bytes.
    figure.savefig(picture, format=kind, facecolor=_SURFACE, metadata={"Software": None} if kind == "png" else None)
    path = path.expanduser()
    write_bytes_atomic(path, picture.getvalue())  # a failed draw leaves no file at the path
    return path


def _end_labels(ax: Any, x: Any, waves: list[tuple[str, Any]], colour: dict[str, str], unit: str) -> None:
    """Name each line and its final value at its end, unless the ends crowd each other."""
    import numpy

    if not len(x):
        return
    end = int(numpy.argmax(x))  # the right-hand end, whichever way a sweep ran
    ax.relim()
    ax.autoscale_view()
    low, high = ax.get_ylim()
    span = (high - low) or 1.0
    # A value a millionth of the axis from zero is zero as drawn (an off LED's picoamps).
    ends = [(name, 0.0 if abs(float(values[end])) < 1e-6 * span else float(values[end])) for name, values in waves if numpy.isfinite(values[end])]
    spots = sorted((value - low) / span for _name, value in ends)
    if any(later - earlier < 0.08 for earlier, later in zip(spots, spots[1:])):
        return  # converging ends: the legend names them
    for name, value in ends:
        ax.plot([x[end]], [value], marker="o", markersize=4.5, color=colour[name], markeredgecolor=_SURFACE, markeredgewidth=1.0, clip_on=False)
        ax.annotate(f"{name} {value:.4g} {unit}", xy=(x[end], value), xytext=(6, 0), textcoords="offset points", va="center", fontsize=8, color=_INK_2, annotation_clip=False)
