"""One PDF of pages drawn by matplotlib, written whole or not at all: ``@eng_drawing``'s and
``@work_instruction``'s.

The PDF is the document, so a missing renderer is a failure, not a downgrade: an exit 0 with no
document is the one outcome a build cannot recover from. The pages carry no creation date, so the
bytes are a function of the content, and the render goes to a temporary file that is renamed on
success, so a failed run never leaves a half-written document behind and an earlier one stays
byte for byte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

# A page: its width and height in millimetres, and what draws it onto an axes in millimetres.
Page = tuple[float, float, Callable[[Any], None]]


def matplotlib_pdf(decorator: str) -> tuple[Any, Any]:
    """matplotlib's pyplot and ``PdfPages``, on the Agg backend; a missing one is refused, naming
    the ``decorator`` that writes the PDF."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_pdf import PdfPages
    except ImportError as exc:
        raise RuntimeError(
            f"{decorator} writes a PDF and its renderer is missing: {exc}. "
            "Install cadgen's dependencies (pip install matplotlib pillow)."
        ) from exc
    return plt, PdfPages


def write_pages(path: Path, pages: Iterable[Page], *, decorator: str) -> None:
    """Draw each page and write them to ``path``, renamed into place once every page is drawn."""
    plt, PdfPages = matplotlib_pdf(decorator)
    from cadgen._internal.atomic_replace import temp_suffix

    path.parent.mkdir(parents=True, exist_ok=True)
    # A temp_suffix name, so a model listing this folder leaves it out while it exists.
    partial = path.with_name(f".{path.name}{temp_suffix()}")
    try:
        # CreationDate=None drops the one field matplotlib stamps from the clock.
        with PdfPages(partial, metadata={"CreationDate": None}) as pdf:
            for width, height, draw in pages:
                fig = plt.figure(figsize=(width / 25.4, height / 25.4))
                ax = fig.add_axes([0, 0, 1, 1])
                ax.set_xlim(0, width)
                ax.set_ylim(0, height)
                draw(ax)
                ax.set_xlim(0, width)  # what was drawn may have moved them
                ax.set_ylim(0, height)
                ax.set_aspect("equal")
                ax.axis("off")
                pdf.savefig(fig)
                plt.close(fig)
        partial.replace(path)
    finally:
        partial.unlink(missing_ok=True)
