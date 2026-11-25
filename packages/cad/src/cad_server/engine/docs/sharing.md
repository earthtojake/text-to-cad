# Sharing

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`cad share` puts a document on the web for anyone with its link to open in the hosted viewer, and to download the
files that made it, with no sign-in. A share is two things under one id: the view, the document's view bundle (**View
bundle**: what its page reads), and the files that made it, at the paths they have in the project. `cad fork` writes
a share's files into a folder, as `cad run` builds them; the share's link then names that copy where cad draws or
inspects a document.

```bash
cad share arm.xbf --yes        # the first time on a computer: the person's yes, kept
cad share <id>                 # a model the engine holds; a file the viewer opens
cad share status               # on or off, agreed or not, and this computer's live shares with their links
cad share off                  # every share refused, --yes or not, until `cad share on`
cad share delete arm.xbf --yes # the share of a TARGET this computer shared
cad share delete 'https://cad.fun/<id>#delete=<secret>' --yes
cad fork https://cad.fun/<id> arm   # its files written into ./arm; it runs nothing
```

## What goes, where, for how long

- **What.** The files that made it (**The files that made it**, below) and its view: a model's, an `.xbf`'s or a
  STEP's parts as meshes, with their names, measurements and joints; an STL's, a GLB's or a 3MF's mesh; a DXF's
  drawing as the viewer draws it; a URDF's or an SRDF's links, joints and mesh files. The picture a page kept
  (`thumbnail.png`) is left out of the view: it may be of an earlier version. A KiCad board or schematic, which has
  no bundle yet, and a folder are refused in one line each.
- **Where.** The share service, `https://cad.fun`, which keeps everything of a share encrypted (AES-256-GCM)
  under a key it derives from the share's id, and keeps neither the id nor the key. The id is the link's: whoever
  has the view link can open the model, and download its files from the files' link, `<view link>.zip`.
- **Who.** Anyone with the view link. No account, no sign-in.
- **For how long.** 7 days after the last share. The same document shared again from the same computer is
  the same share: the link stays, the 7 days start again, and only the files that changed travel.
- **Delete.** The delete link removes it, from any computer and any browser; `cad share delete TARGET`
  removes a share this computer made; asked first, as every command that destroys is (`--yes` where nobody
  can be asked). An expired share is deleted by the service. Either way the document's folder in cad's cache
  goes too (**What is kept**).
- **Off.** `cad share off` keeps the person's no: every share is refused until `cad share on`. Shares made
  before stay until they expire or are deleted.

The first share on a computer is refused without `--yes`, in lines an agent passes on to the person (what goes --
for a model its code and the files it reads, with how many, for a file document the file itself, which anyone with
the link can download, and its view --, where, who can open it, for how long, how to delete it), naming the same
command with `--yes` (`confirmation_required`, exit 2, with `next`). `--yes` keeps the agreement, and later shares
need none. Sharing turned off is refused even with `--yes` (`declined`, exit 1).

## The files that made it

**A model**: from its build closure (**Build closure**), every path relative to its xbf's folder where it declares one,
else its script's, the folder its last run says (`model_info`): the one from which the closure spells its script's
path. Where none of those does (a model taken from the cache after a restart, its xbf declared in a folder beside its
script's), the share is refused in a line: run it, then share.

- its script, every module in `modules`, and every input of kind `file` or `read` the build found (its digest not
  null) that is on the disk still;
- each at its path under **the files' root**: the deepest folder that holds all of them, but never above the nearest
  folder over the script's that holds a `.git` (a checkout's root) and never above the person's home folder. A file
  outside the root is left out, and said in one line (`Left out, outside the project: ...`). A `font` input goes only
  where it lies in the root: a system font is recorded nowhere else needed;
- **the files that built its view**: the engine's `builtAt`, which every run moves, one that changes nothing too. A
  file modified after it changed after the build, and the share is refused in one line naming it and the command that
  runs the model again (`failed`, exit 1, with `next`): run it, then share. A script or a module the closure names
  that is gone from the disk is refused the same way (`not_found`, exit 2); an input gone is left out, and said;
- a build that read a file the engine could not see leaves the closure's key null (**Body retention**): the share
  goes, and a line says a fork may not rebuild it without that file. A shape a program handed over has no closure,
  and its share holds no files, said.

**A file document**: the file itself, at its own name; a URDF's mesh files too (each `<mesh filename>` of its visuals
and collisions, resolved as the viewer resolves one), and an SRDF's URDF with that one's, each at its path under the
file's folder: one outside it is left out, and said.

Never: a file the build did not read (a README beside the script, another script, tests, `.env`), the xbf (the
engine's own, made again from the files), an installed library (named by its version in `made`).

## Where each step runs

1. The command asks the engine what made the document: a model's build closure and its last run (`cad model
   inspect`'s queries), and reads its files, checking each against `builtAt`.
2. The command holds the document's lock in cad's cache: one `cad share` of a document at a time. Another
   says so in a line, waits for it 60 seconds at most, then is refused in one.
3. The running server writes the bundle into the document's folder in cad's cache, over the one it wrote there
   last, as `cad <type> export TARGET DST.view` writes one: only what that bundle lacks is asked of the engine,
   so sharing a document again costs what changed. A model built again meanwhile has its files read again.
4. The command takes the bundle's files as its `manifest.json` lists them, packs the files the share lacks, the view's
   and the ones that made it, and uploads the packs and then the share's manifest in its own process, never through
   the server or a worker, so an agent app's sandbox sees the connection and its network rules apply. Proxies are
   taken from the environment, as `urllib` takes them. A connection that cannot be made, or an answer that is not
   the service's (a proxy's refusal, with no JSON `error`), is said in one line: the network here does not reach
   the share service, and a sandbox that limits hosts must allow its host.
5. The agreement, the setting, each share's record and the document's folder are written by the running server
   for the command (`{"op": "share"}`), as `cad update auto` has its switch written, since a sandboxed shell may
   write neither the state folder nor the cache; with none answering, the command writes them itself.

Its requests, and `cad fork`'s, are ones a person asks for by name (law 17): nothing else in cad reaches the service.

## Forking

`cad fork LINK [FOLDER] [--json]`: LINK a view link, a files' link (`<origin>/<id>.zip`), or a share's id at the
service `CAD_SHARE_URL` names. The command downloads `<origin>/<id>.zip` in its own process, as `cad share` uploads,
and writes its files into FOLDER, by default `./<name>`, the folder the zip holds. A FOLDER that is there and holds
anything is refused (`invalid_argument`), before anything is downloaded. Every entry is refused that would land
outside it -- an absolute path, a `..`, a drive, a link, anything but a file or a folder, a path twice, an entry
outside the zip's one folder -- and every file is written into a folder made beside FOLDER, checked against its
CRC-32, and moved in once all are whole, so a refused or broken zip leaves nothing. A share the service holds no
more: "This shared model has expired or was deleted." (`not_found`).

It says what it wrote, the script that builds it (`Cad-Share-Entry`), and where what built it (`Cad-Share-Made`)
differs from this computer: this release, the CAD kernel environment's libraries and Python (not compared where
that environment is not made yet), the system and the architecture. It runs nothing: the next step it prints is
`cad run FOLDER/<script>` (a file document's, `cad viewer FOLDER/<file>`), since someone else's code is the person's
to read and run. It keeps a record of the fork (**What is kept**), written by the running server as a share's is, so
that the share's link names these files on this computer (**A share's link names this computer's copy**); where it
cannot, a line says so. `--json` is one
object: `local` (false), `folder`, `name`, `files` (`count`, `bytes`, `paths`), `entry`, `made`, `here`, `differs`
(each `name`, `made`, `here`) and `next`.

**A share this computer made.** A link of a live share this computer's records hold (**What is kept**: that service's
origin and that id), whose files are still where it was shared from, is downloaded by no one: the command writes
nothing, FOLDER included (said where one is given), and says where the files are, which is where to work on them:
`arm was shared from this computer: its files are in <root>, its script <root>/arm.py. Nothing was downloaded; work
there.`, or a file document's own file. `--json`: `local` (true), `name`, `root`, `entry`, `file` (a file document's),
`ignored` (the FOLDER given, or null) and `next` (`cad run <root>/<script>`, or `cad viewer <file>`: these files are
this computer's own). A record of another service, one expired, or one whose files moved or went is no such share:
its link is downloaded as any other.

## A share's link names this computer's copy

Where cad takes a document to draw or inspect -- `cad <type> snapshot`'s SRC and a Quick Edit packet's `input` (and a
job's), `cad <type> inspect`'s DOC and a ref's FILE -- a share's view link, `<origin>/<id>` of the service
`CAD_SHARE_URL` names or of `https://cad.fun`, names this computer's copy of the share, so that a shared page's
prompt reads here as a local page's does:

- **a share this computer made**: the document it shared under that link, as its record holds it (a model's id, a
  file document's path);
- **else a fork of it** whose folder is there: the model built from the folder's entry -- the one the engine's records
  say that script is the home of (of the share's name, where it is the home of several) -- or, of a file document,
  its file there. A fork not built yet is refused in one line naming the `cad run` that builds it (`not_found`).
- **else** it is refused in one line, ``<link> is a shared model this computer has no copy of: run `cad fork <link>`,
  then build it.`` (`not_found`, exit 2, with `next`).

A selector after the link, `<link>#<selector>`, is the same in the copy as in the share: `cad model inspect
'https://cad.fun/<id>#head_shell/f:...'`. A link of another origin, or a files' link (`.zip`), is no document's name.

## What is kept

The settings' `share` section: `{"agreed": "<ISO time>"}`, and `"on": false` once turned off.

`shares.json` in the state folder, written whole into a file only this user may read or write (0600 on
POSIX), one record a share, dropped once past its expiry:

```json
{"format": "cad-shares/1", "shares": [{
  "id": "<share id>", "write": "<write secret>", "delete": "<delete secret>",
  "service": "https://cad.fun", "view": "<view link>", "remove": "<delete link>",
  "expires": "2026-12-01T10:00:00Z", "shared": "2026-11-24T10:00:00Z", "bytes": 3880124,
  "document": {"id": "<document id>", "kind": "model", "name": "arm", "path": null},
  "files": {"root": "/home/me/arm", "entry": "arm.py", "file": null}}]}
```

A document is one record per service, by its document id (a file's `path` too); `bytes` is the share's size as
the service stores it; `files`, where on this computer the files that made it are: their root, the script among them
(`entry`, a model's) and a file document's own `file`, which `cad fork` of its link points at (**Forking**). A record with a `key` (`cad-share/1`'s) is none, as is one past its expiry: that
document's next share is a new one. The id and the secrets are said only inside the links and in the records (and
a view link a command was given, said back where this computer has no copy of it): in no other line of any command,
no log, no telemetry and no file of the cache. The command is counted as any command is: its export as an export (a
bundle is no counted kind), nothing of the share.

`forks.json` beside `shares.json`, written the same way, one record a share's link, the latest fork of it, dropped once its
folder is gone:

```json
{"format": "cad-forks/1", "forks": [{
  "link": "https://cad.fun/<id>", "folder": "/home/me/arm", "entry": "arm.py", "file": null, "name": "arm",
  "forked": "2026-11-24T11:00:00Z"}]}
```

`entry` is the script among the fork's files that builds it (a model's), `file` the file a file document's fork shows,
each by its path in the folder; `name` the share's name as its zip's folder gives it.

`shares/<document id>/` in cad's cache, for each document with a live share:

- `bundle.view/`: the bundle as last shared, written over at each share.
- `stored.json`: where each file of the share's last commit lives, the view's and the ones that made it, by the
  SHA-256 of its bytes, `{"share": "<hex SHA-256 of the share id>", "files": {"<sha256>": [["<pack id>", <offset>,
  <length>], ...]}}`: the share named by a hash of its id, never the id. One of another share, or one that cannot be
  read, is none: every file is sent.
- `lock`: held by the `cad share` or `cad share delete` of the document that runs.

As the records are written, each folder that no live record names is removed (a share deleted, expired or never
committed), but one whose lock a command holds. Every file there is made again by the next share, which then
sends every file.

## What it prints

The view link, the files' link (`Files:`), the delete link, the expiry and one line of what travelled: the
document's name and kind, its files and its view (`its 12 files and its view (245 parts as meshes, ...)`, `the file
itself and its view`), the files and bytes uploaded this time, the view's and the ones that made it, and, sharing it
again, the share's whole size (`2 files changed, 67.4 KiB uploaded (4.0 MiB in all)`, or `nothing changed, nothing
uploaded (4.0 MiB in all)`); then a line for each kind of file left out (`Left out, outside the project: ...`, `Left
out, no longer on the disk: ...`) and the line of a build that read a file the engine could not see. `--json` is one
object: `view`, `zip`, `delete`, `expires`, `id`, `again` (the same link as before), `document` (`id`, `kind`,
`name`), `files` (the files that made it: `count`, `bytes`, `entry`, `left_out`, each `path` and `reason` --
`outside`, `gone` or `name`, a name no share takes -- and `unseen`, the closure's null key), `sent` (`what`,
`parts`, this time's `files`, `bytes` and `packs`, `format`), `stored` (the share's `files` and `bytes` as the
service stores them) and `kept` (whether the record was kept). `status --json` is `sharing` (`on` or `off`),
`agreed`, `service` and `shares` (each its `document`, `view`, `zip`, `delete`, `expires`); `delete --json` is
`deleted` (false where the service held it no more), `share` (its view link) and `document`.

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
the bundle with the bytes its manifest says, or nothing is sent. **The files.** The files that made it, by their
paths under the files' root, the same rules. 200,000 files at most over both.

**The packs.** Each file the share lacks (whose bytes `stored.json` does not hold for this share) as one gzip
member (RFC 1952: level 6, mtime 0, no file name), back to back in packs: the view's in the order a page reads them
-- `manifest.json`, `structure.json`, `names/...`, the other files at the bundle's root, the meshes (`parts/...`,
`meshes/...`), each part's `elements.json`, then the rest -- then the files that made it, by their paths. Files of
the same bytes are one member, named twice (a mesh file's and the view's copy of it, two empty modules). A pack is
closed at 4 MiB, and a member that does not fit the room left goes on into the next. A pack's id is the lowercase
hex SHA-256 of its bytes.

**`PUT /v1/shares/<id>/packs/<pack id>`**, 4 at a time as they close: `Authorization: Bearer <write secret>`,
`Cad-Delete-Hash: <lowercase hex SHA-256 of the delete secret's 43-character text>`, `Content-Length`, the pack as
the body. `201`. The share's first write makes its owner, which keeps the two hashes.

**`PUT /v1/shares/<id>`**, the commit: the same headers, `Content-Type: application/json`, and the share's
manifest: its `name` (the document's, 1 to 200 characters, no control character), `entry` (the path among its files
of the script that builds a model; `null` for a file document), `made` (what built a model: `cad`, the release, then
the closure's `libs` and `platform`, each as text; `null` for a file document), and its two maps, `view` and
`files`, each file by its path with its bytes' SHA-256 and size and `at`, the ranges of packs whose bytes, joined in
order, are its member:

```json
{"format": "cad-share/2", "name": "arm", "entry": "arm.py", "made": {"cad": "0.11.17", "build123d": "0.13.0"},
 "view": {"manifest.json": {"sha256": "<64 hex>", "bytes": 1234, "at": [["<pack id>", 0, 456]]}},
 "files": {"arm.py": {"sha256": "<64 hex>", "bytes": 980, "at": [["<pack id>", 456, 410]]}}}
```

`201` (made) or `200` (replaced), `{"id", "expires", "bytes", "files"}`; the service then deletes the packs that
neither this manifest nor the one it replaced names. A `409` naming `missing` packs: the files in them are packed
and uploaded again, then the commit made again, twice at most. A `409` naming none (another commit replaced the
manifest meanwhile): committed again, once. A `403`, to a pack or the commit, is a share of that id that another
write secret made: the command makes a new share, new names and all, and sends every file, once.

**`GET /<id>.zip`**, a fork's: the files that made it as a zip of one folder named for the share, made by the
service from their stored members; `Cad-Share-Entry` and `Cad-Share-Made` (`<name>=<value>, ...`) say its entry and
its `made`, each name and value percent-encoded UTF-8. `404` for a share expired or deleted.

**`DELETE /v1/shares/<id>`**: `Authorization: Bearer <delete secret>`. `204` deleted, `404` none (it expired,
or was deleted), `403` a secret that matches neither of its hashes.

A `429` is waited out for its `Retry-After`, said once in a line: ten times at most for one request, two minutes
at most each. Every other answer is the service's refusal, `{"error", "hint"}` with its status (400, 401, 411,
413), said with both. The service keeps neither secret, only the SHA-256 of each one's text (its ASCII bytes,
never the bytes it decodes to; a bearer's is hashed the same way), and never the id: from the id alone it derives
the name it stores the share under and the key it seals each object with.
