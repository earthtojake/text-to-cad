# cad.engine

A **document** is what a person reviews. Its kind is either a file format the viewer reads (STEP, XBF, STL, GLB,
3MF, DXF, URDF, SRDF) or something derived from code: a model, built by this engine. A document exists so that a
person can review the subjective output of an agent, a design, and answer it through the viewer's tools:
annotate, select, quick edit. These pages are how the engine makes, holds and serves documents.

The laws are the package README's (**The design laws**), and these pages restate none of them: they
describe the mechanism the laws constrain and cite them by that README's numbers.

Each page is one mechanism: read the one you are changing, not the set. A name in bold in parentheses,
such as (**Kinematics**) or (**Starting and updating**), is a page below or a named paragraph of one, and
the last column says which page holds each.

| Page | What it covers | Named in it |
| --- | --- | --- |
| [Models](docs/models.md) | What a model is and what its script declares: the file decorators and `@model`, the handle a call returns, `@memo`, materials, joints and mechanism states, posed copies |  |
| [Architecture](docs/architecture.md) | One server per computer and what it owns; document ids; the HTTP listener and its token; how a release starts, joins or replaces the server; the version feed and cad's own update | A link outlives its engine; Starting and updating |
| [Running a model](docs/running-a-model.md) | Where a model runs: the base environment, `cad run` as `uv run` with cad pinned, the environment of each set of integrations, the worker contract | The base; What an environment holds; One per distinct set, never changed once made; Its releases; An integration built for one Python; What cannot be done is said in one line; A Python of the script's own |
| [Layout](docs/layout.md) | The modules of the engine, one line each |  |
| [CLI](docs/cli.md) | Every command and its arguments; help; consent for a command that destroys; the failure contract and its reasons | Help; Consent; The failure contract |
| [Document types and integrations](docs/document-types-and-integrations.md) | How the registry, a type's object, producers and edits work; each check and export an integration runs (manufacturing, interference, stress, KiCad, MuJoCo, convex hulls, Blender) | The registry; A type's object; Producers; Edits; The commands; The manufacturing check; A B-rep's check is measured in the engine's checks processes; The interference check; The kept results; The stress study; The KiCad board's DRC, the schematic's ERC and their exports; A MuJoCo model's check; OrcaSlicer's presets (deprecated); A part's convex hulls; A GLB in Blender's scene; Running a model |
| [Profiling](docs/profiling.md) | Function timings of a build as it ran: `build(profile=True)` |  |
| [The engine server and its workers](docs/server-and-workers.md) | The daemon's life, the caps on workers and memory, the services it supervises and their protocol, the meshing pool, what `cad server status` says | Services; The protocol |
| [The door](docs/door.md) | How a client reaches the daemon: named pipes on POSIX, the engine folder, starting the engine, holds | Starting the engine; A hold |
| [Document lifetime](docs/document-lifetime.md) | What the engine keeps of a document and for how long: the two kinds, handed-over shapes, the registry and the cache, eviction under one memory budget, delete, the rebuild command | Two kinds; Shapes handed over; The registry; Re-attachment; Identity migration; The cache; The last run; Kept until deleted; Delete; Drain; One budget; Pressure; The rebuild command |
| [Progress](docs/progress.md) | The one progress event every job reports, the stages of each kind of job, and the page's route | A build's stages; An export's, a snapshot's and a measurement's stages; The page's route |
| [The viewer and the snapshot](docs/viewer-and-snapshot.md) | How a page reads a document, the look, `cad <type> snapshot` and its jobs, the OCCT stills and KiCad's own | The look; A job; Native KiCad stills; The OCCT stills |
| [Exports](docs/exports.md) | The viewer's Export action and the translation formats: STEP, GLB (motions and keys), STL, 3MF, DXF; what a file decorator writes and when | Viewer exports; Translation formats; Motions in a GLB; GLB keys; File decorators require `out`; Every model that runs writes its files; Functions |
| [Kinematics](docs/kinematics.md) | How joints become the document's AP242 mechanism: pairing, what AP242 cannot hold, couplings, the viewer's Position | What AP242 cannot hold is refused or left out, never patched; Couplings; A pinion that holds no part; The viewer's Position |
| [Configuration sequences](docs/configuration-sequences.md) | A motion: states over time, as the model declares it and the document keeps it |  |
| [Animations](docs/animations.md) | A GLB's own animation, and how sequences and animations are baked into one | The bake |
| [Materials](docs/materials.md) | Materials and looks; what a model declares for a robot description (mass, the zero pose, couplings and loops, physics and units, appearance) | What a model declares for a robot description; Mass; The zero, the scene and what an export says; Couplings and loops in a robot description; Physics and units; Appearance |
| [Imports](docs/imports.md) | Reading STEP, XBF and STL into a model; why an xbf is the fast input; the reader process | The fast input is an xbf; A STEP is parsed in a reader process; A STEP is the file it is |
| [Placements](docs/placements.md) | One prototype placed many times: how a part used ten times stays one part |  |
| [Mesh](docs/mesh.md) | The one tessellation tolerance, an export's own, edge classes, and what an inspection costs | What an inspection costs |
| [Wire format](docs/wire-format.md) | The HTTP API under `/api/v1` and the buffers a page reads | The HTTP API |
| [Element names](docs/element-names.md) | How every face, edge and vertex is named from the feature history that made it |  |
| [References](docs/references.md) | A ref to a part, an assembly or an element, and how it resolves against the latest build | A model never reads a file its own build writes |
| [Body retention](docs/body-retention.md) | What a body's key is made of, and when a model's or a `@memo` function's body is replayed instead of run |  |
| [Queries](docs/queries.md) | Questions a model asks of what it made, memoized as operations are |  |
| [Memo functions](docs/memo-functions.md) | `@memo`: what marking a function does, and when to mark one | When to mark a function |
| [Known and accepted](docs/known-and-accepted.md) | The two byte-level drifts that are accepted, and on what condition |  |
| [Build closure](docs/build-closure.md) | What an xbf records of the code and inputs that built it, the document's key, and compatibility as the toolchain or the format moves | When the toolchain or the format moves; Document compatibility |
| [In-memory models](docs/in-memory-models.md) | `@model`: a model with no files |  |
| [Parameters](docs/parameters.md) | A model's parameters: declared in its script, recorded in its document, served with whether each is writable, set into the script by the viewer's Save, and a page's preview before it saves | Declaring; Recording; Which a model has; The document; Held while the worker lives; What the page reads; Setting; Previewing |
