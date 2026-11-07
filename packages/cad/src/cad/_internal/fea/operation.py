"""The stress study every B-rep document type shares: ``cad.<type>.fea(source, study=..., out=...)``.

``xbf`` and ``step`` each answer ``fea`` with the same function, made for the type here (``fea_for``): its
signature takes a file of the type and plain values alone, so it is the type's (the signature rule), and what
it runs is the integrations' -- netgen meshes (``cad.netgen``), CalculiX solves (``cad.calculix``) -- imported
when it runs. One operation, one result (``cad.results.FeaResult``, a check's), two uses:

- with no ``study``, the study's setup, which writes nothing: the parts, the pairs that touch and one part's
  faces, each with the ref a study names it by;
- with a ``study`` (a JSON file, inline JSON or a dict) and ``out`` (the result ``.glb``), the solve: the one
  file it writes (and a ``.vtu`` beside it with ``vtu``), every number in the result.

An option of the other use is refused by name before anything is read (law 16): an ``ArgumentRefused``
(``cad._internal.refused``), which the server's command says as the command line's mistake, exit 2. The
standard library alone at import: the server's command resolves the options here before it starts an
environment that holds the integrations.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from cad._internal.refused import ArgumentRefused
from cad.results import FeaResult

__all__ = ["INTEGRATION", "fea_for", "options"]

#: The integration a study runs with: netgen meshes, and its registry entry names the kernel, which reads the B-rep,
#: ``alongside`` it, so the ``cad`` command runs a study in the environment of ``cad[build123d,netgen]`` when its own
#: holds neither (``cad_server.cli.document_types``). CalculiX, the third, is a program the person installs: its
#: probe finds it (``cad.calculix._program``).
INTEGRATION = "netgen"


def options(*, study: Any, out: Any, occurrence: str | None, vtu: bool) -> None:
    """Refuse the options of the other use: ``out`` or ``vtu`` with no study (a setup writes nothing), a study with
    no ``out`` or an ``out`` that is no ``.glb``, and ``occurrence`` beside a study (a study names its parts and
    faces itself). ``ArgumentRefused`` (a ``ValueError``) naming the fix."""
    if study is None:
        given = [flag for flag, value in (("--out", out), ("--vtu", vtu or None)) if value is not None]
        if given:
            raise ArgumentRefused(f"{' and '.join(given)} {'is' if len(given) == 1 else 'are'} a solve's: give --study "
                                  "too, or nothing to list the study's setup (its parts, pairs and faces)")
        return
    if occurrence is not None:
        raise ArgumentRefused("--occurrence lists one part's faces for a study's setup: a study names its parts and "
                              "faces itself, so give it no --occurrence")
    if out is None:
        raise ArgumentRefused("a solve writes its result GLB where --out names it: give --out RESULT.glb")
    if Path(str(out)).suffix.lower() != ".glb":
        raise ArgumentRefused(f"--out names the result GLB and must end in .glb, not {out}")


def fea_for(document_type: str) -> Any:
    """``cad.<document_type>.fea``: the stress study, for a source of that type."""

    def fea(
        source: Path,
        *,
        study: str | dict | None = None,
        out: Path | None = None,
        occurrence: str | None = None,
        vtu: bool = False,
        verbose: bool = False,
    ) -> FeaResult:
        """A linear static stress study of a part or an assembly bonded where its parts touch.

        With no study it lists what a study names, writing nothing: the document's parts, the pairs that touch
        (bonded by default) and one part's faces by ref with area, centre and a hint (`plane, normal -Z,
        largest`). With a study and --out it meshes (netgen), solves (CalculiX, which the person installs:
        CAD_CCX names it, else ccx on PATH, else FreeCAD's) and writes the result GLB the viewer draws, and
        nothing else; each part's peak stress and safety factor against its own material's yield are in the
        result. A part that yields or misses a check fails it, its GLB written all the same; a study whose
        answer would be wrong (a part nothing holds, a load no face takes) is refused. --json carries every
        number.

        source: the .step or .xbf holding the part or the assembly.
        study: the study: a JSON file path, inline JSON, or (a library caller) a dict: the fixed faces, the
          loads (forces, pressures, gravity, acceleration), a material where the model has none, an
          assembly's parts and connections and the checks to judge. Without it, the setup.
        out: the result .glb a solve writes; a study's alone.
        occurrence: the part whose faces the setup lists, by its name or ref, where the document holds several.
        vtu: also write a .vtu of the result beside the GLB, for ParaView; a study's alone.
        verbose: say every progress line and the timings on stderr. Without it a long solve still says how far
          it has got about every 10 s.
        """
        options(study=study, out=out, occurrence=occurrence, vtu=vtu)
        from cad._internal.document_type import refuse_other

        refuse_other(document_type, source)
        try:
            from cad._internal.fea import run
            from cad._internal.fea.mesh import require_fea_stack
        except ModuleNotFoundError as error:
            _missing(error)
            raise
        if study is None:
            return run.setup(Path(source), occurrence=occurrence, verbose=verbose)
        try:
            require_fea_stack()
        except ModuleNotFoundError as error:
            _missing(error)
            raise
        assert out is not None
        return run.solve_study(Path(source), Path(out), study=study, vtu=vtu, verbose=verbose)

    fea.__module__ = f"cad.{document_type}"
    fea.__qualname__ = fea.__name__ = "fea"
    return fea


def _missing(error: ModuleNotFoundError) -> None:
    """An integration this process lacks, said in one line naming its extra (``cad._internal.integrations``)."""
    from cad._internal.integrations import missing

    said = missing(error)
    if said is not None:
        raise ModuleNotFoundError(said, name=error.name) from None
