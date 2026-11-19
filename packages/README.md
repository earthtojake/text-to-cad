# Packages

One Python distribution, `cad`, with three empty aliases released beside it at the same version, and
two shared JavaScript packages that support the applications in `apps/docs`, `apps/web` and `apps/mcp`:

| Directory | Identity | Responsibility |
| --- | --- | --- |
| [cad](cad/README.md) | Python distribution `cad`, imported as `cad`, `cad_server` and `cad_mcp` | The library (`cad`): what a model imports and what runs in a worker -- the model API, the kernel-side engine, the document model and the protocol a client speaks; the CAD kernel is its `build123d` extra. The server and the `cad` command (`cad_server`): the engine's daemon, the viewer's and the CAD app's servers, cad's own update, and the bundled runtime outputs. The transport an agent app starts (`cad_mcp`, run as `cad mcp`) |
| `aliases/` | Python distributions `cad-server`, `cad-mcp` and `cadgen` | Empty aliases, still published at every release so older installs keep working: each installs `cad` at the same release, nothing of its own but the commands it shipped (`cad-server` keeps `cad`, so a uv tool installed by that name keeps its command; `cad-mcp` keeps `cad-mcp`; `cadgen` is the library's deprecated name) |
| [core](core/README.md) | `@cad/core` | Framework-independent JS/TS geometry, rendering and explicit CAD service client |
| [ui](ui/README.md) | `@cad/ui` | Complete shared FileViewer, injectable renderers, navigation, controls and styles |

The web app and the CAD app (`apps/mcp`) both consume the same FileViewer; their
adapters own browser and host services and application state. Docs consumes core for
its hero, an animated GLB the engine exported.

Apps import compiled public package exports. UI may depend on core; core never
depends on React or UI. Shared packages never import application source, and
applications never import one another. The root npm workspace and lockfile own
JavaScript installation; `npm run build:packages` builds core before UI.

The `cad` wheel assembles the built viewer client and CAD app page. That build dependency does
not let Python engine code reach into app source.
Each wheel works outside this repository, so its own Markdown must also stand
alone -- not even linking another distribution's files, which its wheel does not carry; repository
development instructions belong in `CONTRIBUTING.md`.
