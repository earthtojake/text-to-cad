# cadgen

**Deprecated: install and import `cad`.** `cadgen` is the deprecated alias of the text-to-cad
library, still published at every release for backwards compatibility. This distribution holds
nothing of its own: it installs `cad`, the library, at the same release. A model that imports
`cadgen` still runs (`from cadgen import model` is `from cad import model`), and says so once per
process: `CadDeprecationWarning: cadgen is deprecated; use cad`.

`cadgen[build123d]` installs the library with its CAD kernel, as `cad[build123d]` does;
`cadgen[kernel]`, its 0.8 spelling, installs the same.

New projects declare `cad`, pinned to the release they run (`cad==<release>`). The CAD server, the
CAD Viewer and the command that runs models are `cad-server`'s, installed by the install
command at https://texttocad.dev.
