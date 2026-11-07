"""``cad.kicad``: the kicad integration -- our code for KiCad: kicad-cli and its IPC API, both kicode's.

KiCad's command line, ``kicad-cli``, is an external program our code runs (kind C), with a separate
process; its extra, ``cad[kicad]``, is kicode, which carries that program and KiPy, the IPC API's Python
client (as ``kicode``), one KiCad nightly's build of both. A person's own KiCad is never run. What is here:

* ``_program``: ``kicad-cli`` found and run, by the library's one helper for external programs
  (``cad._internal.programs``): ``CAD_KICAD_CLI``, refused unless it names a ``kicad-cli``, then
  kicode's; only ``kicad-cli`` itself is ever run, headless, in private homes (``kicode.environment``).
* ``_command``: ``cad run kicad-cli ARGS`` -- KiCad's own command line, the environment's (kicode's console
  script, else ``kicode.executable()``), headless in a private folder, its exit code kicad-cli's.
* ``_session``: what ``kicad_pcb.edit`` and ``kicad_sch.edit`` run, a ``with`` block -- a private
  ``kicad-cli api-server`` on the file (KiCad makes one not there yet), one per project, which the board's
  and the schematic's edits share; KiPy connected to it, the open document handed over (a schematic's
  project symbol libraries loaded first), saved at the block's end when it was changed and not when the
  block raises, the server stopped and its folder removed.
* ``_check``: KiCad's design rule check (``cad.kicad_pcb.drc``, ``cad kicad_pcb drc``).
* ``_export``: the board's fabrication, assembly and 3D outputs by ``kicad-cli`` (``EXPORTS``: gerbers,
  drill, pos, bom, step, glb, odb, ipc2581, pdf, dxf), which ``cad.kicad_pcb.export`` and the server's ``cad
  kicad_pcb export`` are written by.
* ``_schematic``: a schematic's electrical rules check and its outputs (``EXPORTS``: pdf, svg, netlist,
  bom) by ``kicad-cli``, from its project's root sheet (``cad.kicad_sch.erc`` and ``export``, ``cad
  kicad_sch erc`` and ``export``).
* ``route`` (``_route``, its search in ``_routing``): copper for the connections an agent names, in the order
  it names them, written into the board a ``kicad_pcb.edit`` block has open: KiPy's board in, the copper out
  through it, every rule the board's own; it answers a ``Routed``.

The board readers are the document type's (``cad.kicad_pcb``), our own code for the file format: viewing,
reading and drawing a board need no KiCad. Importing this package starts nothing and imports no kicode.
"""

from __future__ import annotations

from cad.kicad._route import Routed, route

__all__ = ["Routed", "route"]
