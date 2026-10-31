# Packages

Three Python distributions, released together at one version, and two shared JavaScript packages
that support the applications in `apps/docs`, `apps/web` and `apps/mcp`:

| Directory | Identity | Responsibility |
| --- | --- | --- |
| [texttocad](texttocad/README.md) | Python distribution `texttocad`, imported as `cad` | The library: what a model imports and what runs in a worker -- the model API, the kernel-side engine, the document model and the protocol a client speaks; the CAD kernel is its `kernel` extra |
| [texttocad-server](texttocad-server/README.md) | Python distribution `texttocad-server`, imported as `cad_server` | The server: the engine's daemon, the command, the CAD Viewer's and the CAD app's servers, the installations, and the bundled runtime outputs |
| [texttocad-mcp](texttocad-mcp/README.md) | Python distribution `texttocad-mcp`, imported as `cad_mcp` | The shim: the stdio transport an agent app starts, the standard library alone |
| `aliases/` | Python distributions `cadgen` and `text-to-cad` | The library under its earlier and the product's names: each a pin of `texttocad` at the same release, nothing of its own |
| [core](core/README.md) | `@text-to-cad/core` | Framework-independent JS/TS geometry, rendering and explicit CAD service client |
| [ui](ui/README.md) | `@text-to-cad/ui` | Complete shared FileViewer, injectable renderers, navigation, controls and styles |

The web app and the CAD app (`apps/mcp`) both consume the same FileViewer; their
adapters own browser and host services and application state. Docs consumes core for
its hero, an animated GLB cadgen exported.

Apps import compiled public package exports. UI may depend on core; core never
depends on React or UI. Shared packages never import application source, and
applications never import one another. The root npm workspace and lockfile own
JavaScript installation; `npm run build:packages` builds core before UI.

The server's wheel assembles the built CAD Viewer client and CAD app page. That build dependency does
not let Python engine code reach into app source.
Each wheel works outside this repository, so its own Markdown must also stand
alone -- not even linking another distribution's files, which its wheel does not carry; repository
development instructions belong in `CONTRIBUTING.md`.
