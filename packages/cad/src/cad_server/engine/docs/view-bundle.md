# View bundle

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

A page shows a document by asking the engine for each thing it draws (**Wire format**), and the engine
makes some of those answers when asked. A **view bundle** is the same answers made ahead of time and
written as files in one folder, so that a page can show the document with no engine and no kernel behind
it. It is a share's view: `cad share` has the running server write the shared file's bundle into that file's
folder of cad's cache, `documents/<id>/view/`, and uploads its files, sending only the ones its share does not
hold yet (**Sharing**); the hosted viewer opens it from the share service. Nothing else writes one: it is no
export (no `cad <type> export` destination names one, and a `.view` folder is refused as any suffix no
export knows), and the engine writes one only when a file is shared (law 2). The library's half of it is
`api.bundle(path, folder)`, the request `{"op": "bundle", "path", "folder"}`; its answer is what was written:
the folder, its `document`, how many `files` it holds, and the paths this writing `written` and `removed`.

A KiCad board or schematic has no view bundle yet: its `export` is KiCad's own (`--to`, into a folder, run
by the kicad integration) and names no such destination. What one waits on is said under **Writing one**.

## Layout

A file is an HTTP answer, byte for byte, at the path of its route below the document's API
(`/api/v1/documents/<kind>/<id>/`), with an extension for what it is. The engine's own reads, the same
for every document, are at the root likewise. So a reader maps each read of a page to one path:

| A page's read | In the bundle | Held by |
| --- | --- | --- |
| `GET /api/v1/documents/<id>` (the envelope) | `manifest.json`'s `document` (below) | every bundle |
| `GET <api>/structure` | `structure.json`, read once every part is meshed, so it names each part's `unmeshed` faces; of a model, an `.xbf` and a STEP, its mechanism and each prototype's element names held apart (below) | a model, an `.xbf`, a STEP; a robot description |
| `GET <api>/parts/<key>?tessellation=<tessellation>` | `parts/<key>/<tessellation>.xbm`: the part's `XBM2` buffer | each part of a model, an `.xbf`, a STEP |
| `GET <api>/parts/<key>/faces\|edges\|vertices/<ordinal>` | `parts/<key>/elements.json`, under `faces`, `edges` or `vertices`, by the ordinal | each part of one |
| `GET <api>/parts/<key>/groups` | `parts/<key>/elements.json`'s `groups` | each part of one |
| `GET <api>/parts/<key>/volume`, `GET <api>/measure` | `measure.json`: every part's volume, solids and box, by key | a model, an `.xbf`, a STEP |
| `GET <api>/kinematics` | `kinematics.json`, which the structure leaves out | one with joints |
| `GET /api/v1/look`, `GET /api/v1/look/environment` | `look.json`, `look/environment.hdr` (the look names its environment by the API's path, as answered) | a model, an `.xbf`, a STEP |
| `GET <api>/source` | `source.stl`, `source.glb`, `source.3mf`: the file, which its page parses | an STL, a GLB, a 3MF |
| `GET <api>/drawing` | `drawing.json` | a DXF |
| `GET <api>/parts/<digest>` | `parts/<digest>.glb`: a primitive cad meshed | a robot description |
| `GET /api/v1/local/files?path=<a link's mesh>` | `meshes/<sha256>.<format>`: the mesh file, named by its bytes | a robot description |
| `GET /api/v1/documents/<id>/thumbnail` | `thumbnail.png` | a document whose page kept a picture |

Nothing else a page asks has a file: a version to wait on, a pose, a mesh run, a model's parameters set or
previewed, an export and everything under `/api/v1/local` need an engine. A bundle is one document as it
stood, so its reader offers none of them, and reads a parameter's `writable` as said of the engine that
answered.

`<key>`, `<tessellation>` and `<digest>` are path segments: ASCII letters, digits, `.`, `_` and `-` as
they are, every other byte `~` and its two hex digits (a STEP part's key `step-0a1b-0:1:2` is
`step-0a1b-0~3A1~3A2`), so a segment is a file name on every system and reads the same in a URL as on a
disk.

**One table per part, not a file per element.** A page asks the engine for an element's facts when a person
picks it (`parts/<key>/faces|edges|vertices/<ordinal>`) and for a part's groups when a selection first
grows (`parts/<key>/groups`); the engine measures them then. A bundle holds them whole: `elements.json` is
`{"faces", "edges", "vertices", "groups"}`, each of the first three every element's facts by its ordinal (as
text), exactly what asking for that one answers, and `groups` the groups' answer. It is a route of the
engine's too, so it is an HTTP answer like the rest. It is a function of the part's geometry alone, so two
things a per-element answer adds about its document are not in it: a face's `meshed`, which the
structure's `unmeshed` and the buffer's face table say, and a model's `made_by`, which is served live and
never written (law 7).

**Where a file is not the answer.** A bundle holds no path of the computer it was made on, no source code
and nothing a kernel must read (no `.xbf`, no STEP, no shape: a share carries a model's `.xbf` among its files,
never in its view). Three answers say something of that computer, and each is the answer but for that:

- A structure's `path` is the file's name alone, where the engine's answer names where the file is; a
  model's is its id, as a live worker answers it, whether a worker holds the model or its `.xbf` is read, so a
  model's bundle is the same after a restart.
- A model's structure has no `closure`: the build closure names the code that built the model, its script
  and modules by path, their names and its inputs (**Build closure**). It stays with the engine and the
  `.xbf`.
- A robot's structure names each visual's mesh by its path in the bundle (`mesh.url`: `parts/<digest>.glb`,
  `meshes/<sha256>.<format>`, relative to the bundle's root) where the engine's answer names the URL it
  serves it at, and the `path` a link's facts give a mesh file is the file's name alone. A mesh file that
  names other files (a GLB's external buffer or texture) is bundled as it is, without them.

A JSON file that would still name the folder its document came from fails the writing rather than being
written (law 16): what is left is the document's own text (a label, a note) or a mistake. Nothing in a
bundle is the document's envelope, which says where things are on one computer: the manifest says what a
reader needs of it. `thumbnail.png` is the picture a page last kept, which may be of an earlier version.

**Held once.** The structure of a model, an `.xbf` or a STEP holds two things apart, and a reader puts
both back before it answers the structure:

- Its mechanism: `kinematics.json` is the structure's `kinematics`, the same object, so where the bundle
  holds that file, `structure.json` has none.
- Each prototype's element names (`faceNames`, `edgeNames`, `vertexNames`, whichever it has), in
  `names/<sha256>.json`: compact JSON of an object holding them, every key sorted, named by the SHA-256 of
  its own bytes, which the prototype names in their place (`"names": "names/<sha256>.json"`; a prototype
  with none of the three has none). Prototypes can share a part's key and name its elements apart (one
  geometry made by two functions), so a names file is named by what it holds, never by the key, and
  prototypes named alike (one function's parts of two geometries) share one.

So `structure.json` is the tree, the placements and the looks alone, which an edit of a colour or a
placement changes, and a prototype's names are a file of their own, which changes only with them.

**Named by content.** A part's two files are named by its geometry key, and its buffer by the
tessellation it was meshed at, as their URLs are; a prototype's names and a robot's meshes are named by
their bytes. So they are the same bytes in every bundle that holds them, and a server may keep them for
ever. The files at the bundle's root are the document's own and change with it.

## The manifest

```json
{
 "format": "view-bundle/1",
 "document": {"id": "64e0eca9-…", "kind": "model", "name": "arm", "version": "2d7477b07ccdfa4c"},
 "made": {"tool": "cad", "release": "0.11.17"},
 "files": {
  "structure.json": {"bytes": 4082, "sha256": "…", "type": "application/json"},
  "parts/18385ab0…/0.25-28.5.xbm": {"bytes": 6084, "sha256": "…", "type": "application/octet-stream"}
 }
}
```

`format` names the layout: a change within `view-bundle/1` only adds, and a reader of another number reads
none of it (law 14, tier 4). `document` is the document's `id`, its `kind` (the API's: `model`, `step`,
`stl`, `glb`, `3mf`, `dxf`, `urdf`, `srdf`; a reader takes `xbf` too, an `.xbf`'s kind while it was a type of its
own), its `name` and the `version` its files are of (the structure's, for a model and a STEP; else the
envelope's). `files` is every other file of the
bundle by its path, with its size, its SHA-256 and the content type its answer was sent with, which a file
server that knows no `.xbm` or `.hdr` is told from here. The manifest holds no time and no path: a document
the engine holds gives the same manifest each time it is written. A model built again has a new
`version`, whatever changed.

## Writing one

The writer is the server's (`viewer/bundle.py`), since the answers are: it opens the document as a page
does, asks the page's own application, in process, for each read, and puts each answer's bytes at its
path. It makes no answer itself, so what a bundle holds is what a page is told, and kernel work stays in
the engine's own processes (law 19): the parts are meshed by the meshing pool into the one mesh cache a
page reads from, and each table is one job of the pool's facts queue (`mesh.Topology.elements`), made once
and kept by the part's geometry key as its facts are, in memory alone (`serve.Server.table`), so no part's
table is made twice while the engine runs, whichever document holds it. A document's part files are asked
at once, twice as many at a time as the pool has processes, so a first bundle's tables are made on every
core the engine uses. The library's half is one request through the door (`api.bundle`,
`{"op": "bundle", "path", "folder"}`): there is no bundle without a server to ask.

Every answer is gathered into a folder made beside the bundle's before the bundle's own is touched, so a
writing that fails leaves what was there as it was (law 16). A new bundle is then that folder, renamed. A
bundle written over an earlier one by the same release keeps each of the earlier one's content-named files
whose bytes are still what its manifest says, asking the engine for nothing of that part; it moves in the
files whose bytes changed, then the manifest, last, then removes the files the earlier manifest named and
this one does not. So after an edit of one part a bundle costs that part's mesh and table, and a folder
whose manifest names a file holds it. Those moves are one file at a time: a bundle read while it is written
over can hold a root file newer than its manifest says, until the manifest lands.

A folder that holds anything but a bundle is refused before anything is asked, as is a file the engine
does not read, and a type no bundle is made of. A document that changes while it is read (a model built
again, a file rewritten) is read again from the start, three times at most, then the writing fails saying
so.

**What a KiCad bundle waits on.** A board's page reads its `plot`, whose pours are KiCad's refill, made in
the kicad integration's environment, and a table of its 3D models, each a STEP the engine serves as a
document of its own; a schematic's reads its `plot` a sheet at a time. Their bundle is those answers by the
same rules (each model a bundle of its own), which `cad share` asks for as it asks for any.
