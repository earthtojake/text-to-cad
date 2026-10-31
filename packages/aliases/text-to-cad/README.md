# text-to-cad

The text-to-cad library under the product's own name. This distribution holds nothing of its own: it
installs `cad`, the library, at the same release, which a model imports as `cad`;
`text-to-cad[build123d]` installs it with its CAD kernel, as `cad[build123d]` does.

Projects declare `cad`, pinned to the release they run (`cad==<release>`). The CAD server, the
CAD Viewer and the command that runs models are `cad-server`'s, installed by the install
command at https://texttocad.dev.
