# text-to-cad

The text-to-cad library under the product's own name. This distribution holds nothing of its own: it
installs `texttocad`, the library, at the same release, which a model imports as `cad`;
`text-to-cad[build123d]` installs it with its CAD kernel, as `texttocad[build123d]` does.

Projects declare `texttocad`. The CAD server, the CAD Viewer and the command that runs models are
`texttocad-server`'s, installed by the install command at https://texttocad.dev.
