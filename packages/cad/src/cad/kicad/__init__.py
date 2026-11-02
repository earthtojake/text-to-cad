"""``cad.kicad``: the kicad integration -- our code for KiCad, kicad-cli and its IPC API.

KiCad (``kicad-cli``, a program the person installs) is an integration of kind C, an external program our
code runs, with a separate process; its extra, ``cad[kicad]``, is the IPC API's Python client, kipy
(``kicad-python``), which a persistent board script's function is handed a board of. What is here:

* ``_program``: ``kicad-cli`` found and run, by the library's one helper for external programs
  (``cad._internal.programs``): ``CAD_KICAD_CLI``, refused unless it names a ``kicad-cli``, then PATH,
  then the usual installation; only ``kicad-cli`` itself is ever run, headless, in private homes.
* ``_session``: what ``@kicad_pcb("board.kicad_pcb")`` runs -- a private ``kicad-cli api-server`` on the
  board, kipy connected to it, the function handed the open board, the board saved when it returns
  and not when it raises, the server stopped and its folder removed.
* ``_export``: the board's fabrication outputs by ``kicad-cli pcb export`` (gerbers, drill, pos, step),
  which the server's ``cad kicad_pcb export`` and the STEP a board script declares are written by.
* ``_producers``: the producers this integration registers (``cad.registry``): a board script makes a
  ``kicad_pcb``, and the ``step`` stacked on it.

The board readers are the document type's (``cad.kicad_pcb``), our own code for the file format: viewing,
reading and drawing a board need no KiCad. Importing this package starts nothing and imports no kipy.
"""

from __future__ import annotations

__all__: list[str] = []
