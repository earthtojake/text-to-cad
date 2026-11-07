"""``cad.xcaf_pmi``: the xcaf_pmi integration -- our code for xcaf-pmi, Paul Fremantle's AP242 writer.

xcaf-pmi (https://github.com/pzfreo/xcaf-pmi, Apache-2.0) writes an ``.xbf``'s PMI to a STEP with haecceity
(quiddity's) instead of the kernel's writer: the same semantic PMI, with callouts drawn as text and notes in
the file. It is a Python package with a command line, run in a separate process; its extra, ``cad[xcaf_pmi]``,
is xcaf-pmi and what it needs. What is here:

* ``_command``: ``cad run xcaf-pmi ARGS`` -- its own command line, the environment's, its exit code xcaf-pmi's.

The default STEP is the engine's, which this changes nothing of: this is a second writer a person asks for.
"""
