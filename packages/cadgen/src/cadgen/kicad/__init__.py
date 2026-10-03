"""KiCad: the PCB kernel cadgen drives, as build123d drives OpenCascade.

``@pcb`` models are written in Python (``cadgen.pcb``); this package turns
them into KiCad documents and asks KiCad's own command line, ``kicad-cli``, for
the operations cadgen must never reimplement: filling copper zones, the
electrical and design rule checks, plots and fabrication exports. Nothing here
talks to a running KiCad or imports KiCad's Python bindings; the documents
are files, and ``kicad-cli`` is a program cadgen runs.

Modules, each importing nothing heavy at module scope:

- ``sexpr``: read and write the S-expression syntax every KiCad file uses.
- ``install``: find ``kicad-cli``, the symbol/footprint/3D libraries and
  ngspice.
- ``library``: load a symbol or footprint by its ``Library:Name``; search them.
- ``design``: the authoring model (``Board``, parts, nets, copper, rules).
- ``fabs``: each fab's limits for its standard service (``pcb.JLCPCB``, ``pcb.PCBWAY``...).
- ``outline`` / ``ids``: a build123d outline as board edges; stable UUIDs.
- ``board_writer`` / ``schematic_writer`` / ``project_writer`` / ``project``:
  the documents.
- ``cli``: run ``kicad-cli`` and read its JSON reports.
- ``check``: a build's fill, ERC and DRC; ``cadgen pcb validate``'s checks.
- ``plot`` / ``solid`` / ``fab``: the viewer's plots, the populated board in
  3D, and the manufacturing files.
- ``spice`` / ``ngspice`` / ``sim``: simulation -- the netlist from KiCad's
  ``Sim.*`` fields, the simulator KiCad ships, and the ``Testbench``.
- ``specctra`` / ``route``: autorouting -- a board as Freerouting's Specctra
  DSN and its routed session read back, and running Freerouting (a separate
  program, GPL-3.0) for ``board.autoroute()``.
"""
