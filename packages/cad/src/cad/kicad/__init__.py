"""``cad.kicad``: the kicad integration -- our code for KiCad: kicad-cli and its IPC API, both kicode's.

KiCad's command line, ``kicad-cli``, is an external program our code runs (kind C), with a separate
process; its extra, ``cad[kicad]``, is kicode, which carries that program and KiPy, the IPC API's Python
client (as ``kicode``), one KiCad nightly's build of both. A person's own KiCad is never run. What is here:

* ``_program``: ``kicad-cli`` found and run, by the library's one helper for external programs
  (``cad._internal.programs``): ``CAD_KICAD_CLI``, refused unless it names a ``kicad-cli``, then
  kicode's; only ``kicad-cli`` itself is ever run, headless, in private homes (``kicode.environment``).
* ``_session``: what ``@kicad_pcb("board.kicad_pcb")`` runs -- a private ``kicad-cli api-server`` on the
  board, KiPy connected to it, the function handed the open board, the board saved when it returns
  and not when it raises, the server stopped and its folder removed.
* ``_check``: KiCad's design rule check (``cad.kicad_pcb.drc``, ``cad kicad_pcb drc``).
* ``_export``: the board's fabrication, assembly and 3D outputs by ``kicad-cli`` (``EXPORTS``: gerbers,
  drill, pos, bom, step, glb, odb, ipc2581, pdf, dxf), which ``cad.kicad_pcb.export``, the server's ``cad
  kicad_pcb export`` and the STEP a board script declares are written by.
* ``_schematic``: a schematic's electrical rules check and its outputs (``EXPORTS``: pdf, svg, netlist,
  bom) by ``kicad-cli``, from its project's root sheet (``cad.kicad_sch.erc`` and ``export``, ``cad
  kicad_sch erc`` and ``export``).
* ``_producers``: the producers this integration registers (``cad.registry``): a board script makes a
  ``kicad_pcb``, and the ``step`` stacked on it.

The board readers are the document type's (``cad.kicad_pcb``), our own code for the file format: viewing,
reading and drawing a board need no KiCad. Importing this package starts nothing and imports no kicode.
"""

from __future__ import annotations

__all__: list[str] = []
