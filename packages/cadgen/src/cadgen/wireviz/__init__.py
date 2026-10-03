"""WireViz: the harness tool cadgen drives, as KiCad is the board tool.

``@harness`` models are written in Python (``cadgen.harness``); this package
turns them into WireViz documents and asks WireViz's own command line,
``wireviz``, for what cadgen must never reimplement: the diagram (drawn with
Graphviz's ``dot``) and the bill of materials. WireViz is GPL-3.0 and a
separate program: nothing here imports it, and cadgen never installs it; the
documents are files, and ``wireviz`` is a program cadgen runs.

Modules, each importing nothing heavy at module scope:

- ``colors``: WireViz's colour codes and the standard colour sequences.
- ``design``: the authoring model (``Harness``, connectors, cables, wires) and
  the checks a build makes.
- ``document``: the harness as deterministic WireViz YAML.
- ``install``: find ``wireviz`` and Graphviz's ``dot``.
- ``cli``: run ``wireviz`` on a staged copy of a document.
- ``plot``: the diagram as the CAD Viewer's plot payload.
- ``bom``: the bill of materials, as CSV.
"""
