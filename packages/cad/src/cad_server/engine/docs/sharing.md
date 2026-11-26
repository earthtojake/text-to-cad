# Sharing

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`cad share` puts a file on the web for anyone with its link to open in the hosted viewer, and to download the files
that made it, with no sign-in. A share is of one file, named by its canonical path, and is two things under one id:
the view, the file's view bundle (**View bundle**: what its page reads), and its files: the file itself and, of a
model, the files that made it, at the paths they have in the project. A model is shared by its `.xbf`, its document
(**Document lifetime**). `cad import` writes a share's files into a folder, a model's `.xbf` among them, so the model is
there at once with nothing run; the share's link then names that copy wherever cad takes a document.

```bash
cad share arm.xbf --yes        # the first time on a computer: the person's yes, kept
cad share status               # on or off, agreed or not, and this computer's live shares with their links
cad share off                  # every share refused, --yes or not, until `cad share on`
cad share delete arm.xbf --yes # the share of a file this computer shared
cad share delete 'https://cad.fun/<id>#delete=<secret>' --yes
cad import https://cad.fun/<id> arm # its files written into ./arm, its file the library's; it runs nothing
```

FILE is turned into the file's canonical path (`ids.canonical`) before anything else: a path read from the folder
the command runs in, a document id (which the command takes too) the file the engine names by it (`inspect`'s `build` query: a model's `.xbf`, a
file's own path), a share's link this computer's copy of it (**A share's link names this computer's copy**). A
model's script is refused in one line that says to share the model's `.xbf`, which running the script writes
(`wrong_type`, exit 2). The same file is the same share wherever it is named from; a file that moves is another
file, and shares to a link of its own.

## What goes, where, for how long

- **What.** Its files (**The files that made it**, below) and its view: a model's or a STEP's parts as meshes,
  with their names, measurements and joints; an STL's, a GLB's or a 3MF's mesh; a DXF's drawing as the viewer draws
  it; a URDF's or an SRDF's links, joints and mesh files; a KiCad board's layers as KiCad draws them, its pours
  KiCad's refill, and its parts' 3D models; a KiCad schematic's sheets. The picture a page kept (`thumbnail.png`) is
  left out of the view: it may be of an earlier version. A folder and a script are refused in one line each.
- **Where.** The share service, `https://cad.fun`, which keeps everything of a share encrypted (AES-256-GCM)
  under a key it derives from the share's id, and keeps neither the id nor the key. The id is the link's: whoever
  has the view link can open the model, and download its files from the files' link, `<view link>.zip`.
- **Who.** Anyone with the view link. No account, no sign-in.
- **For how long.** 7 days after the last share. The same file shared again from the same computer is the same
  share: the link stays, the 7 days start again, and only the files that changed travel.
- **Delete.** The delete link removes it, from any computer and any browser; `cad share delete FILE` removes
  a share this computer made; asked first, as every command that destroys is (`--yes` where nobody can be asked).
  An expired share is deleted by the service. Either way what the share kept in the file's folder of cad's cache
  goes too (**What is kept**).
- **Off.** `cad share off` keeps the person's no: every share is refused until `cad share on`. Shares made
  before stay until they expire or are deleted.

The first share on a computer is refused without `--yes`, in lines an agent passes on to the person (what goes --
for a model its `.xbf`, its code and the files it reads, with how many, for a file document the file itself and
the files it draws from (a KiCad project's, with how many), which anyone with the link can download, and its view
--, where, who can open it, for how long, how to delete it), naming the same command with `--yes`
(`confirmation_required`, exit 2, with `next`). `--yes` keeps the agreement, and later shares need none. Sharing
turned off is refused even with `--yes` (`declined`, exit 1).

## The files that made it

**A model**: its `.xbf`, and the files of the build closure it holds (**Build closure**), every path relative to
the `.xbf`'s folder:

- its script, every module in `modules`, and every input of kind `file` or `read` the build found (its digest not
  null) that is on the disk still;
- the `.xbf` itself: the model as its last run made it, which an import reads as any `.xbf` with nothing run, and
  which a later in-browser kernel may read too. Its pack is any size: a file larger than a pack goes on into the
  next (**The packs**);
- each at its path under **the files' root**: the deepest folder that holds all of them, but never above the nearest
  folder over the script's that holds a `.git` (a checkout's root) and never above the person's home folder. A file
  outside the root is left out, and said in one line (`Left out, outside the project: ...`). An `.xbf` outside it
  is refused in one line: a share holds one folder's files. A `font` input goes only where it lies in the root: a
  system font is recorded nowhere else needed;
- **none changed since the model was made**: the `.xbf`'s time, or, where a live worker of the running engine holds
  the model and its last run is later, that run's (a run that takes the `.xbf` whole, its key the model's, writes
  nothing: an edit no key sees, a comment, is made by that run). A file modified after it is not what the `.xbf` was
  made from, and the share is refused in one line naming it and the run of its script (`failed`, exit 1, with
  `next`: `cad run SCRIPT`): run it, then share. A script or a module the closure names that is gone from the disk is
  refused the same way (`not_found`, exit 2); an input gone is left out, and said;
- a build that read a file the engine could not see leaves the closure's key null (**Body retention**): the share
  goes, and a line says an import may not rebuild it without that file. An `.xbf` that holds no closure (a shape a
  program handed over, a file exported from another document) goes alone, at its own name, said.

**A file document**: the file itself, at its own name; a URDF's mesh files too (each `<mesh filename>` of its visuals
and collisions, resolved as the viewer resolves one), and an SRDF's URDF with that one's, each at its path under the
file's folder: one outside it is left out, and said.

**A KiCad board or schematic**: the file itself and what an import needs to open it and work on it, each at its path under
the files' root, which is found as a model's is (the deepest folder that holds them, from the file's, capped at a
checkout's root and the home folder):

- of a board, its project file (`<board>.kicad_pro`) and its custom rules (`.kicad_dru`) beside it, its project's
  footprint and symbol libraries -- `fp-lib-table` and `sym-lib-table` and each library they list there (a
  `.pretty`'s footprints, a `.kicad_sym`) -- and the 3D model files its footprints name in the project (`${KIPRJMOD}`'s,
  a variable the project defines, a path), a VRML name with the STEP beside it, which the view draws;
- of a schematic, every sheet of the hierarchy it is drawn in (from its project's root sheet, which a sheet shared
  on its own is drawn from too), the root's project file and its project's symbol libraries;
- never a library of KiCad's (`${KICAD9_FOOTPRINT_DIR}`, `${KICAD9_3DMODEL_DIR}`, a variable the project does not
  define, a model KiCad's 3D library holds): an installed library, which an importer's KiCad has;
- a file outside the root, and one the project names that is gone, left out and said, as a model's are.

Never: a file the build did not read (a README beside the script, another script, tests, `.env`), or an installed
library (named by its version in `made`).

## Where each step runs

1. The command turns FILE into the file's path, and, of a model, reads the closure its `.xbf` holds and its files,
   checking each against the time the model was made (the engine's `model_info`, for a live worker's last run).
2. The command holds the file's lock in cad's cache: one `cad share` of a file at a time. Another says so in a
   line, waits for it 60 seconds at most, then is refused in one.
3. The running server writes the bundle into the file's folder in cad's cache (`{"op": "bundle"}`, `api.bundle`),
   over the one it wrote there last: only what that bundle lacks is asked of the engine, so sharing a file again costs
   what changed. A model made again meanwhile has its files read again.
4. The command takes the bundle's files as its `manifest.json` lists them, packs the files the share lacks, the view's
   and its own, and uploads the packs and then the share's manifest in its own process, never through the server or a
   worker, so an agent app's sandbox sees the connection and its network rules apply. Proxies are taken from the
   environment, as `urllib` takes them. A connection that cannot be made, or an answer that is not the service's (a
   proxy's refusal, with no JSON `error`), is said in one line: the network here does not reach the share service, and
   a sandbox that limits hosts must allow its host.
5. The agreement, the setting, each share in its file's entry of the library and the file's folder are written by
   the running server for the command (`{"op": "share"}`), as every change of the library is, and as `cad update auto`
   has its switch written, since a sandboxed shell may write neither the state folder nor the cache; with none
   answering, the command writes them itself.

Its requests, and `cad import`'s, are ones a person asks for by name (law 17): nothing else in cad reaches the service,
and nothing shares again on its own: a build changes no share until `cad share` runs again.

## Importing

`cad import LINK [FOLDER] [--json]`, `cad share`'s match: LINK a view link, a files' link (`<origin>/<id>.zip`), or a
share's id at the service `CAD_SHARE_URL` names. The command downloads `<origin>/<id>.zip` in its own process, as `cad
share` uploads, and writes its files into FOLDER, by default `./<name>`, the folder the zip holds. A FOLDER that is there and holds
anything is refused (`invalid_argument`), before anything is downloaded. Every entry is refused that would land
outside it -- an absolute path, a `..`, a drive, a link, anything but a file or a folder, a path twice, an entry
outside the zip's one folder -- and every file is written into a folder made beside FOLDER, checked against its
CRC-32, and moved in once all are whole, so a refused or broken zip leaves nothing. A share the service holds no
more: "This shared model has expired or was deleted." (`not_found`).

It finds the file the share is of among them (`sharing.shared_file`): of a model, whose share names its script
(`Cad-Share-Entry`), the `.xbf` whose build closure names that script from its own folder (of several, the one no
other of them read); of a file document, the one SRDF at the folder's top, else the one URDF, else the one KiCad
board, else the root of a schematic's hierarchy (the sheet beside a project file of its name, else the one no other
of its sheets draws: whichever of them was shared, it draws the same pages), else its one file. It
says what it wrote, that file, the script, and where what built it (`Cad-Share-Made`) differs from this computer:
this release, the CAD kernel environment's libraries and Python (not compared where that environment is not made
yet), the system and the architecture. It runs nothing, and makes no project: the next steps it prints are `cad
viewer FOLDER/<file>`, which shows it as it was shared, and, of a model, `cad run FOLDER/<script>`, which builds it
here, since someone else's code is the person's to read and run. The file the share is of goes into the library with
the link it came from (**What is kept**), written by the running server as a share is, so that it is among the
viewer's Recents and the share's link names it on this computer (**A share's link names this computer's copy**);
where it cannot, or the command could not tell which file that is, a line says so. `--json` is
one object: `local` (false), `folder`, `name`, `files` (`count`, `bytes`, `paths`), `file` (the shared file's path in
the folder, or null), `entry`, `made`, `here`, `differs` (each `name`, `made`, `here`) and `next`.

**A share this computer made.** A link of a live share this computer's library holds (**What is kept**: that
service's origin and that id), whose file is still where it was shared from, is downloaded by no one: the command writes
nothing, FOLDER included (said where one is given), and says where its files are, which is where to work on them:
`arm was shared from this computer: it is <root>/XBF/arm.xbf, its files in <root>, its script <root>/arm.py. Nothing
was downloaded; work there.`, or a file document's own file. `--json`: `local` (true), `name`, `file`, `root`,
`entry` (a model's), `ignored` (the FOLDER given, or null) and `next` (`cad run <root>/<script>`, or `cad viewer
<file>`: these files are this computer's own). A share of another service, one expired, or one whose file moved or
went is no such share: its link is downloaded as any other.

## A share's link names this computer's copy

Wherever cad takes a document -- the source of every `cad <type> <operation>` (`snapshot`, `inspect`, `export`, a
check), a Quick Edit packet's `input` (and a job's), a ref's FILE, `cad viewer`'s FILEs and `cad share`'s -- a share's
view link, `<origin>/<id>` of the service `CAD_SHARE_URL` names or of `https://cad.fun`, names this computer's copy of
the share, so that a shared page's prompt reads here as a local page's does:

- **a share this computer made**: the file it shared under that link, by its entry in the library;
- **else an import of it**: the file of the import's the share is of, by its entry in the library, whose file is there; a
  model's `.xbf` is there with nothing run;
- **else** -- neither, or an import whose file is gone -- it is refused in one line, ``<link> is a shared model this
  computer has no copy of: run `cad import <link>`.`` (`not_found`, exit 2, with `next`).

A selector after the link, `<link>#<selector>`, is the same in the copy as in the share: `cad inspect
'https://cad.fun/<id>#head_shell/f:...'`. A link of another origin, or a files' link (`.zip`), is no document's name.
Nothing of it goes through the engine's knowledge of a model: the library's entries are this computer's own.

## What is kept

The settings' `share` section: `{"agreed": "<ISO time>"}`, and `"on": false` once turned off.

The library (`library.json` in the state folder, `cad_server.engine.library`), which this user alone may read or write
(0600 on POSIX), as it holds the shares' keys, and which the engine alone writes, as it writes every change of the
library (a command asks it to, and writes it itself only where none answers). A shared file is in it, its entry found
by the file's canonical path, and its entry's `shares` holds, by each share service's origin, its share there:

```json
{"path": "/home/me/arm/XBF/arm.xbf", "created": 1764000000.0, "opened": 1764000100.0,
 "shares": {"https://cad.fun": {"link": "https://cad.fun/<share id>", "write": "<write secret>",
                                "delete": "<delete secret>", "expires": "2026-12-01T10:00:00Z",
                                "root": "/home/me/arm", "entry": "arm.py"}}}
```

`link` is the view link, `write` and `delete` the share's keys, `expires` its expiry as the service said it, and
`root` and `entry` where on this computer the files that made it are: their root, and the script among them (a
model's), which `cad import` of its link points at (**Importing**). What a command says of a share is worked out from
there: its delete link (`<link>#delete=<delete secret>`), and its file's id, kind and name from its path. A share past
its expiry goes from its entry as the library is written, and that file's next share is a new one; an entry whose
file is gone stays while a share of it is live, listed and deleted as any, and is never shared to again. A file
forgotten (the home's Remove) forgets its share's keys: its delete link still deletes it. A share whose entry holds no
keys is none. The id and the secrets are said only inside the links and in the library (and a view link a command was
given, said back where this computer has no copy of it): in no other line of any command, no log, no telemetry and no
file of the cache. The command is counted as any command is, nothing of the share.

An imported file is in it too: the file of the import's that the share is of (`sharing.shared_file`), its entry's
`imported` the share's view link it came from, which names it from then on (**A share's link names this computer's
copy**), so it is among the viewer's Recents. One entry holds a link: the latest import of it. Where the import could not
tell which of its files the share is of, none is in the library, and the command says so.

What a development build of 0.12 kept beside the library (`shares.json`, `forks.json`) is not read: those shares are
deleted by their delete links, and expire.

In the shared file's own folder of cad's cache, `documents/<id>/` (**The store**), beside what the cache keeps of the
file:

- `view/`: its view bundle as last shared, made only when the file is shared and written over at each share, the base
  the next share reuses.
- `stored.json`: where each file of the share's last commit lives, the view's and its own, by the SHA-256 of its
  bytes, `{"share": "<hex SHA-256 of the share id>", "files": {"<sha256>": [["<pack id>", <offset>, <length>],
  ...]}}`: the share named by a hash of its id, never the id. One of another share, or one that cannot be read, is
  none: every file is sent.
- `share.lock`: held by the `cad share` or `cad share delete` of the file that runs.

As a share is kept or dropped, these are removed from each folder that no live share's file names (a share deleted,
expired or never committed), but one whose lock a command holds; the rest of the folder stays. Nothing there is
needed: deleted, the next share makes the bundle again and sends every file, and keeps its link, whose keys are the
library's.

## What it prints

The view link, the files' link (`Files:`), the delete link, the expiry and one line of what travelled: the
file's name and kind, its files and its view (`its .xbf and the 12 files that made it and its view (245 parts as
meshes, ...)`, `the file itself and its view`), the files and bytes uploaded this time, the view's and its own, and,
sharing it again, the share's whole size (`2 files changed, 67.4 KiB uploaded (4.0 MiB in all)`, or `nothing changed,
nothing uploaded (4.0 MiB in all)`); then a line for each kind of file left out (`Left out, outside the project:
...`, `Left out, no longer on the disk: ...`) and the line of a build that read a file the engine could not see.
`--json` is one object: `view`, `zip`, `delete`, `expires`, `id`, `again` (the same link as before), `document` (`id`,
`kind`, `name`, `path`), `files` (its files: `count`, `bytes`, `entry`, `file` -- the shared file's path among them --,
`left_out`, each `path` and `reason` -- `outside`, `gone` or `name`, a name no share takes -- and `unseen`, the
closure's null key), `sent` (`what`, `parts`, this time's `files`, `bytes` and `packs`, `format`), `stored` (the
share's `files` and `bytes` as the service stores them) and `kept` (whether the library kept the share). `status --json` is
`sharing` (`on` or `off`), `agreed`, `service` and `shares` (each its `document`, `view`, `zip`, `delete`,
`expires`); `delete --json` is `deleted` (false where the service held it no more), `share` (its view link) and
`document`.

## The protocol, as the command speaks it

`cad-share/2`. Every random value is from `secrets`, base64url without padding.

| Value | Form |
| --- | --- |
| share id | 16 random bytes, 22 characters (`[A-Za-z0-9_-]{22}`), drawn again while they begin with `-`, which a command line reads as an option: the capability, which the view link is |
| write secret | 32 random bytes, 43 characters: upload again |
| delete secret | 32 random bytes, 43 characters: delete |

The view link is `<origin>/<id>`, the files' link `<origin>/<id>.zip`, the delete link
`<origin>/<id>#delete=<delete secret>`. The origin is `https://cad.fun`; `CAD_SHARE_URL`, an http or https origin,
names another (a test's stand-in, a local run of the service), as `CAD_API_URL` names another receiver of telemetry.

**The view.** The bundle's `manifest.json`, and every file it lists but `thumbnail.png`, by its path in the
bundle: relative, `/` separated, with no empty, `.` or `..` segment, at most 1024 bytes; each a regular file inside
the bundle with the bytes its manifest says, or nothing is sent. **The files.** The file itself and the files that
made it, by their paths under the files' root, the same rules. 200,000 files at most over both.

**The packs.** Each file the share lacks (whose bytes `stored.json` does not hold for this share) as one gzip
member (RFC 1952: level 6, mtime 0, no file name), back to back in packs: the view's in the order a page reads them
-- `manifest.json`, `structure.json`, `names/...`, the other files at the bundle's root, the meshes (`parts/...`,
`meshes/...`), each part's `elements.json`, then the rest -- then its files, by their paths. Files of the same bytes
are one member, named twice (a mesh file's and the view's copy of it, two empty modules). A pack is closed at 4 MiB,
and a member that does not fit the room left goes on into the next, so a file of any size (a large `.xbf`) is the
ranges of as many packs as it needs. A pack's id is the lowercase hex SHA-256 of its bytes.

**`PUT /v1/shares/<id>/packs/<pack id>`**, 4 at a time as they close: `Authorization: Bearer <write secret>`,
`Cad-Delete-Hash: <lowercase hex SHA-256 of the delete secret's 43-character text>`, `Content-Length`, the pack as
the body. `201`. The share's first write makes its owner, which keeps the two hashes.

**`PUT /v1/shares/<id>`**, the commit: the same headers, `Content-Type: application/json`, and the share's
manifest: its `name` (a model's `.xbf`'s stem, else the file's name, 1 to 200 characters, no control character),
`entry` (the path among its files of the script that builds a model; `null` for a file document, and for an `.xbf`
that holds no closure), `made` (what built a model: `cad`, the release, then the closure's `libs` and `platform`,
each as text; `null` where no closure says), and its two maps, `view` and `files`, each file by its path with its
bytes' SHA-256 and size and `at`, the ranges of packs whose bytes, joined in order, are its member:

```json
{"format": "cad-share/2", "name": "arm", "entry": "arm.py", "made": {"cad": "0.11.17", "build123d": "0.13.0"},
 "view": {"manifest.json": {"sha256": "<64 hex>", "bytes": 1234, "at": [["<pack id>", 0, 456]]}},
 "files": {"arm.py": {"sha256": "<64 hex>", "bytes": 980, "at": [["<pack id>", 456, 410]]},
           "XBF/arm.xbf": {"sha256": "<64 hex>", "bytes": 5242880, "at": [["<pack id>", 866, 4193438],
                                                                       ["<next pack id>", 0, 1052094]]}}}
```

`201` (made) or `200` (replaced), `{"id", "expires", "bytes", "files"}`; the service then deletes the packs that
neither this manifest nor the one it replaced names. A `409` naming `missing` packs: the files in them are packed
and uploaded again, then the commit made again, twice at most. A `409` naming none (another commit replaced the
manifest meanwhile): committed again, once. A `403`, to a pack or the commit, is a share of that id that another
write secret made: the command makes a new share, new names and all, and sends every file, once.

**`GET /<id>.zip`**, an import's: its files, a model's `.xbf` among them, as a zip of one folder named for the share,
made by the service from their stored members; `Cad-Share-Entry` and `Cad-Share-Made` (`<name>=<value>, ...`) say its entry and
its `made`, each name and value percent-encoded UTF-8. `404` for a share expired or deleted.

**`DELETE /v1/shares/<id>`**: `Authorization: Bearer <delete secret>`. `204` deleted, `404` none (it expired,
or was deleted), `403` a secret that matches neither of its hashes.

A `429` is waited out for its `Retry-After`, said once in a line: ten times at most for one request, two minutes
at most each. Every other answer is the service's refusal, `{"error", "hint"}` with its status (400, 401, 411,
413), said with both. The service keeps neither secret, only the SHA-256 of each one's text (its ASCII bytes,
never the bytes it decodes to; a bearer's is hashed the same way), and never the id: from the id alone it derives
the name it stores the share under and the key it seals each object with.
