# texttocad-server

The CAD server for text-to-cad, imported as `cad_server`: the computer's one daemon that builds, keeps and
serves CAD documents; the CAD Viewer and the CAD app's MCP endpoint on its listener; the environment the
CAD kernel runs in; the installations and the one that is current; and the command that runs and
installs them all.

Models are written against the library, `texttocad` (imported as `cad`), which the server imports without
its CAD kernel: the kernel lives in the environment the server makes for models and its own kernel
processes, `texttocad[kernel]` at the server's own release.

The mechanisms its laws constrain are [`src/cad_server/engine/README.md`](src/cad_server/engine/README.md).
