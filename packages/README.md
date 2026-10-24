# Packages

Three shared packages support the applications in `apps/docs` and `apps/web`:

| Directory | Identity | Responsibility |
| --- | --- | --- |
| [cadgen](cadgen/README.md) | Python distribution `cadgen` | The CAD engine and its daemon, the CLI, the CAD Viewer's and the CAD app's servers, and bundled runtime outputs |
| [core](core/README.md) | `@text-to-cad/core` | Framework-independent JS/TS geometry, rendering and explicit CAD service client |
| [ui](ui/README.md) | `@text-to-cad/ui` | Complete shared FileViewer, injectable renderers, navigation, controls and styles |

This migration is a pure refactor. All apps retain their existing UI, UX and
functionality. Web and desktop both consume the same FileViewer; their adapters
own browser/native services and application state. Docs consumes core for its
hero, a static GLB.

Apps import compiled public package exports. UI may depend on core; core never
depends on React or UI. Shared packages never import application source, and
applications never import one another. The root npm workspace and lockfile own
JavaScript installation; `npm run build:packages` builds core before UI.

The Python wheel assembles the built headless browser bundle and the built CAD
Viewer client and CAD app page. That build dependency does not
let Python engine code reach into app source.
The wheel works outside this repository, so its own Markdown must also stand
alone; repository development instructions belong in `CONTRIBUTING.md`.
