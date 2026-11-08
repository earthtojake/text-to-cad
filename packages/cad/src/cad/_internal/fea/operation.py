"""The stress study every B-rep document type shares: ``cad.<type>.solve(source, study=..., out=...)``.

``model``, ``xbf`` and ``step`` each answer ``solve`` with the same function, made for the type here (``solve_for``):
its signature takes a source of the type and plain values alone, so it is the type's (the signature rule), and what
it runs is the integrations' -- the kernel reads the part, netgen meshes it (``cad.netgen``), CalculiX solves it
(``cad.calculix``) -- imported when it runs. A model, which the engine holds with no file, is written to an ``.xbf`` in
a temporary folder first, and the study reads that. One operation, one result (``cad.results.FeaResult``, a check's),
two uses:

- with no ``study``, the study's setup, which writes nothing: the parts, the pairs that touch and one part's
  faces, each with the ref a study names it by;
- with a ``study`` (a JSON file, inline JSON or a dict) and ``out``, a folder, the solve, which writes its results
  there (``cad._internal.fea.run``): ``result.json`` (the answer, as ``--json`` prints it), ``result.glb`` (the
  deformed surface coloured by stress, the fields as attributes), ``result.vtu`` (the volume and its fields),
  ``stress.png`` and ``displacement.png``, and with ``deck`` CalculiX's input, ``ccx.inp``.

An option of the other use is refused by name before anything is read (law 16): an ``ArgumentRefused``
(``cad._internal.refused``), which the server's command says as the command line's mistake, exit 2. The
standard library alone at import: the server's command resolves the options here before it starts an
environment that holds the integrations.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import FeaResult

__all__ = ["INTEGRATION", "options", "solve_for"]

#: The integration a study runs with: CalculiX solves, and its registry entry names the kernel, which reads the B-rep,
#: and netgen, which meshes it, ``alongside`` it, so the ``cad`` command runs a study in the environment of
#: ``cad[build123d,netgen,calculix]`` when its own does not hold all three (``cad_server.cli.document_types``).
INTEGRATION = "calculix"

def options(*, study: Any, out: Any, occurrence: str | None, deck: bool = False) -> None:
    """Refuse the options of the other use: ``out`` or ``deck`` with no study (a setup writes nothing), a study with no
    ``out`` or an ``out`` that is a file (it names the folder the results go into), and ``occurrence`` beside a study
    (a study names its parts and faces itself). ``ArgumentRefused`` (a ``ValueError``) naming the fix."""
    if study is None:
        given = [flag for flag, value in (("--out", out), ("--deck", deck or None)) if value is not None]
        if given:
            listed = ", ".join(given[:-1]) + (" and " if len(given) > 1 else "") + given[-1]
            raise ArgumentRefused(f"{listed} {'is' if len(given) == 1 else 'are'} a solve's: give --study too, or "
                                  "nothing to list the study's setup (its parts, pairs and faces)")
        return
    if occurrence is not None:
        raise ArgumentRefused("--occurrence lists one part's faces for a study's setup: a study names its parts and "
                              "faces itself, so give it no --occurrence")
    if out is None:
        raise ArgumentRefused("a solve writes its results into the folder --out names: give --out DIR (any folder, a "
                              "temporary one included; it is made when missing)")
    if Path(str(out)).expanduser().is_file():
        raise ArgumentRefused(f"--out names the folder a solve writes its results into, and {out} is a file")


def solve_for(document_type: str) -> Any:
    """``cad.<document_type>.solve``: the stress study, for a source of that type."""

    def solve(
        source: Path,
        *,
        study: str | dict | None = None,
        out: Path | None = None,
        occurrence: str | None = None,
        deck: bool = False,
        verbose: bool = False,
    ) -> FeaResult:
        """A linear static stress study of a part or an assembly bonded where its parts touch.

        With no study it lists what a study names, writing nothing: the document's parts, the pairs that touch
        (bonded by default) and one part's faces by ref with area, centre and a hint (`plane, normal -Z,
        largest`). With a study and --out it meshes (netgen), solves (CalculiX, from cad[calculix]; CAD_CCX names
        another) and writes its results into the folder --out names: result.json (every number, as --json prints
        it), result.glb (the deformed surface coloured by stress, any viewer opens it), result.vtu (the volume's
        fields, for meshio, PyVista or ParaView), stress.png and displacement.png (where a still can be drawn). Each
        part's peak stress and safety factor against its own material's yield are in the result. A part that yields
        or misses a check fails it, its results written all the same; a study whose answer would be wrong (a part
        nothing holds, a load no face takes) is refused. --json carries every number.

        source: the part or the assembly: a .step or .xbf, or a model's document id the engine holds (cad model
          solve), or the handle its call returns.
        study: the study: a JSON file path, inline JSON, or (a library caller) a dict: the fixed faces, the
          loads (forces, pressures, gravity, acceleration), a material where the model has none, an
          assembly's parts and connections and the checks to judge. Without it, the setup.
        out: the folder a solve writes its results into, made when missing; a study's alone.
        occurrence: the part whose faces the setup lists, by its name or ref, where the document holds several.
        deck: also write ccx.inp, the input CalculiX solved (the finer solve's when there were two); a study's alone.
        verbose: say every progress line and the timings on stderr. Without it a long solve still says how far
          it has got about every 10 s.
        """
        options(study=study, out=out, occurrence=occurrence, deck=deck)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        try:
            from cad._internal.fea import run
            from cad._internal.fea.mesh import require_fea_stack
        except ModuleNotFoundError as error:
            _missing(error)
            raise
        with _readable(document_type, source) as (target, label):
            if study is None:
                return run.setup(target, occurrence=occurrence, verbose=verbose, label=label)
            try:
                require_fea_stack()
            except ModuleNotFoundError as error:
                _missing(error)
                raise
            assert out is not None
            return run.solve_study(target, Path(out).expanduser(), study=study, deck=deck, verbose=verbose,
                                   label=label)

    solve.__module__ = f"cad.{document_type}"
    solve.__qualname__ = solve.__name__ = "solve"
    return solve


class _readable:
    """The file a study reads for ``source`` and what its result names it as: a file of its own type as it is; a
    model, written to an ``.xbf`` in a temporary folder that is removed once the study is done, named by its id."""

    def __init__(self, document_type: str, source: Any) -> None:
        self.document_type, self.source = document_type, source
        self.folder: tempfile.TemporaryDirectory | None = None

    def __enter__(self) -> tuple[Path, Path | None]:
        if self.document_type != "model":
            return Path(self.source), None
        from cad.engine.api import export

        ident = getattr(self.source, "id", None) or getattr(self.source, "name", None) or str(self.source)
        self.folder = tempfile.TemporaryDirectory(prefix="cad-solve-")
        target = Path(self.folder.name) / "model.xbf"
        export(self.source, target, progress=False)
        return target, Path(str(ident))

    def __exit__(self, *_exc: object) -> None:
        if self.folder is not None:
            self.folder.cleanup()


def _missing(error: ModuleNotFoundError) -> None:
    """An integration this process lacks, said in one line naming its extra (``cad._internal.integrations``)."""
    from cad._internal.integrations import missing

    said = missing(error)
    if said is not None:
        raise ModuleNotFoundError(said, name=error.name) from None
