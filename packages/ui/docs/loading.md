# Loading and live updates

What the viewport does in the background between "a file was selected" and
"the picture has settled": how a document arrives, and how it follows a
model that is being rebuilt while you watch.

A STEP and an `.xbf` open in the engine document renderer (`renderers/xbf`), read from the
cadgen engine that serves them. A triangle mesh (STL, 3MF) and a
GLB are drawn as they are: their renderers load the file whole, parse it once per revision
(an STL in a worker) and keep the decode cached, so reopening one fetches and parses nothing
(see [Mesh renderer](cad-renderer.md#mesh-renderer)).

The observable promises are in [the web app README](../../../apps/web/README.md#the-laws-that-bind-the-app);
this file is the mechanism behind them. None of it may change **exact**
geometry, measurements or explicit mesh-export tolerances.

| § | Covers |
|---|---|
| [1](#1-opening-a-document) | Where the page reads a document, its structure and its parts |
| [2](#2-following-an-active-build) | The version wait, what a new version fetches, what stays on screen |

## 1. Opening a document

The page asks its viewer where to read the file (`client.engineDocument`, `GET /__cad/xbf`):
the viewer asks the engine's daemon to serve it and answers the document's API URL through
itself (`/__cad/api/doc/<id>`), or 202 while the engine still reads a large STEP, and the
client asks again after the server's `retryMs`. The page then reads the structure (prototypes
with their names, geometry keys, colours and element names by ordinal; instances with world
matrices; the tree; the version) and one XBM2 buffer per prototype, six at a time
(`loadXbfDocument`, core's `lib/xbf/xbfDocument.js`), beside the engine's look. The viewport
reads "Reading model", then "Loading geometry" with the parts in and the parts to come, and
the scene is built once they are all in (`createXbfScene`, the builder a snapshot calls too).
Every part is drawn at the mesh the engine made of it: the page never tessellates. What the
kernel measures of an element is asked when a person asks (`fetchXbfElementFacts`), never
extracted ahead.

## 2. Following an active build

Once a version is on screen the page waits on the engine for the next (`waitForXbfVersion`,
`…/version?after=&wait=`), about once a second: a build that rewrites the document, or a STEP
written again, answers at once. The new version is read with the old one as `previous`: a
part is fetched once per geometry key, so only the parts the edit changed are fetched, and
every other part keeps its buffer and the geometry already uploaded. The new scene replaces
the old when it is ready, so the old one stays on screen meanwhile, reported as an update
("Updating model…"), never as the loading screen, and the camera stays where it is. An engine
that stopped answering (its daemon idled out or was stopped) is asked again after a second,
which starts it, and the document is read from it as it has it now.
