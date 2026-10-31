# cadgen

The text-to-cad library under its earlier name. This distribution holds nothing of its own: it
installs `texttocad`, the library, at the same release, which a model imports as `cad` and, under
this earlier name, as `cadgen` too (`from cadgen import model` works as `from cad import model`
does). `cadgen[kernel]` installs the library with its CAD kernel, as `texttocad[kernel]` does.

New projects declare `texttocad`. The CAD server, the CAD Viewer and the command that runs models
are `texttocad-server`'s, installed by the install command at https://texttocad.dev.
