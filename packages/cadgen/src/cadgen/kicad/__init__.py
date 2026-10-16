"""KiCad: the PCB kernel cadgen drives, as build123d drives OpenCascade.

A ``@pcb`` script (:mod:`cadgen.pcb`) fills a board through KiCad's own API
client, kicad-python (vendored as :mod:`cadgen.kipy`), on a headless server the
build starts and stops (``kicad-cli api-server``, KiCad 10.99 or newer). Every
board file is KiCad's, written by KiCad; cadgen writes no KiCad document itself
and reads the saved ones for the viewer.

Modules, each importing nothing heavy at module scope:

- ``install``: find ``kicad-cli`` (``CADGEN_KICAD_CLI``, ``PATH``, the
  installers' folders) and judge its version.
- ``cli``: run ``kicad-cli pcb drc`` on a saved board and read its report, the
  one check the API does not offer: every build's last step, and ``cadgen pcb drc``.
- ``sexpr``: read the S-expression syntax every KiCad file uses.
- ``geometry`` / ``naming``: the frames, shapes and names the readers share.
- ``board_index`` / ``refs``: a saved board read back from its file as what a
  person points at, and board references (``#U3.9``, ``#net:VIN``...)
  answered.
- ``plot``: the viewer's picture of a board, geometry per layer, from the file.
"""
