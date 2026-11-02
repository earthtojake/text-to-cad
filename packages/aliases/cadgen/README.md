# cadgen

The text-to-cad library under its earlier name. This distribution holds nothing of its own: it
installs `cad`, the library, at the same release, which a model imports as `cad` and, under
this earlier name, as `cadgen` too (`from cadgen import model` works as `from cad import model`
does). `cadgen[build123d]` installs the library with its CAD kernel, as `cad[build123d]` does;
`cadgen[kernel]`, its 0.8 spelling, installs the same.

New projects declare `cad`, pinned to the release they run (`cad==<release>`). The CAD server, the
CAD Viewer and the command that runs models are `cad-server`'s, installed by the install
command at https://texttocad.dev.
