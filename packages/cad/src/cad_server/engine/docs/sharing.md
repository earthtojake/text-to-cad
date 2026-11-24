# Sharing

A page of [the engine's documentation](../README.md). A name in bold in parentheses, such as (**Kinematics**), is another page or a named paragraph of one: the index says which.

`cad share` puts a document on the web for anyone with its link to open in the hosted viewer, with no sign-in.
What goes is the document's view bundle (**View bundle**): what its page reads, and nothing a kernel reads.

```bash
cad share arm.xbf --yes        # the first time on a computer: the person's yes, kept
cad share <id>                 # a model the engine holds; a file the viewer opens
cad share status               # on or off, agreed or not, and this computer's live shares with their links
cad share off                  # every share refused, --yes or not, until `cad share on`
cad share delete arm.xbf --yes # the share of a TARGET this computer shared
cad share delete 'https://cad.fun/<id>#delete=<secret>' --yes
```

## What goes, where, for how long

- **What.** A model's, an `.xbf`'s or a STEP's parts as meshes, with their names, measurements and joints:
  never its code, its build closure or the CAD file. An STL, a GLB or a 3MF is the file itself; a DXF its
  drawing as the viewer draws it; a URDF or an SRDF its links, joints and mesh files. The picture a page kept
  (`thumbnail.png`) is left out: it may be of an earlier version. A KiCad board or schematic, which has no
  bundle yet, and a folder are refused in one line each.
- **Where.** The share service, `https://cad.fun`, which stores the archive encrypted (AES-256-GCM) under a
  key the command makes and sends with the upload, then forgets. The key is in the view link's fragment,
  which no browser sends to a server.
- **Who.** Anyone with the view link. No account, no sign-in.
- **For how long.** 7 days after the last upload. The same document shared again from the same computer
  is uploaded again under the same names: the link stays the same and the 7 days start again.
- **Delete.** The delete link removes it, from any computer and any browser; `cad share delete TARGET`
  removes a share this computer made; asked first, as every command that destroys is (`--yes` where nobody
  can be asked). An expired share is deleted by the service.
- **Off.** `cad share off` keeps the person's no: every share is refused until `cad share on`. Shares made
  before stay until they expire or are deleted.

The first share on a computer is refused without `--yes`, in lines an agent passes on to the person (what
goes, where, who can open it, for how long, how to delete it), naming the same command with `--yes`
(`confirmation_required`, exit 2, with `next`). `--yes` keeps the agreement, and later shares need none.
Sharing turned off is refused even with `--yes` (`declined`, exit 1).

## Where each step runs

1. The running server writes the bundle into a temporary folder this command made, as `cad <type> export
   TARGET DST.view` writes one; the folder is removed once it is packed.
2. The command packs it and uploads it in its own process, never through the server or a worker, so an agent
   app's sandbox sees the connection and its network rules apply. Proxies are taken from the environment,
   as `urllib` takes them. A connection that cannot be made, or an answer that is not the service's (a proxy's
   refusal, with no JSON `error`), is said in one line: the network here does not reach the share service, and
   a sandbox that limits hosts must allow its host.
3. The agreement, the setting and each share's record are written by the running server for the command
   (`{"op": "share"}`), as `cad update auto` has its switch written, since a sandboxed shell may not write the
   state folder; with none answering, the command writes them itself.

Its own request is the one a person asks for by name (law 17): nothing else in cad reaches the service.

## What is kept

The settings' `share` section: `{"agreed": "<ISO time>"}`, and `"on": false` once turned off.

`shares.json` in the state folder, written whole into a file only this user may read or write (0600 on
POSIX), one record a share, dropped once past its expiry:

```json
{"format": "cad-shares/1", "shares": [{
  "id": "<share id>", "key": "<key>", "write": "<write secret>", "delete": "<delete secret>",
  "service": "https://cad.fun", "view": "<view link>", "remove": "<delete link>",
  "expires": "2026-12-01T10:00:00Z", "shared": "2026-11-24T10:00:00Z", "bytes": 16308,
  "document": {"id": "<document id>", "kind": "model", "name": "arm", "path": null}}]}
```

A document is one record per service, by its document id (a file's `path` too). The key and the secrets are
said only inside the two links and in the record: in no other line of any command, no log and no telemetry.
The command is counted as any command is: its export as an export (a bundle is no counted kind), nothing of
the share.

## What it prints

The view link, the delete link, the expiry and one line of what travelled: the document's name and kind, its
parts or its file, the bytes uploaded, and that no code (nor, but for a mesh file, the CAD file) went. `--json`
is one object: `view`, `delete`, `expires`, `id`, `again` (the same link as before), `document` (`id`, `kind`,
`name`), `sent` (`what`, `without`, `parts`, `files`, `bytes`, `format`, `code`, `cad_file`) and `kept`
(whether the record was kept). `status --json` is `sharing` (`on` or `off`), `agreed`, `service` and
`shares` (each its `document`, `view`, `delete`, `expires`); `delete --json` is `deleted` (false where the
service held it no more), `share` (its address, with no fragment) and `document`.

## The protocol, as the command speaks it

Every random value is from `secrets`, base64url without padding.

| Value | Form |
| --- | --- |
| share id | 16 random bytes, 22 characters (`[A-Za-z0-9_-]{22}`) |
| key | 32 random bytes, 43 characters: an AES-256-GCM key |
| write secret | 32 random bytes, 43 characters: upload again |
| delete secret | 32 random bytes, 43 characters: delete |

The view link is `<origin>/<id>#key=<key>`, the delete link `<origin>/<id>#delete=<delete secret>`. The origin
is `https://cad.fun`; `CAD_SHARE_URL`, an http or https origin, names another (a test's stand-in, a local run of
the service), as `CAD_API_URL` names another receiver of telemetry.

**The archive, `cad-share/1`.** The bundle folder as a gzip-compressed POSIX ustar archive: every regular file
by its path relative to the bundle's root, `/` separated, `manifest.json` among them, and no folder, link or
other entry; sorted by path; each with mtime 0, mode 0644, uid and gid 0 and empty user and group names; gzip
with mtime 0 and no file name, so the same bundle makes the same bytes. A path that does not fit a ustar header
(a name of 100 bytes, a prefix of 155) is refused, never written another way. The archive is held to 25 MiB
before it is sent.

**`PUT /v1/shares/<id>`**, upload or upload again: `Authorization: Bearer <write secret>`, `Cad-Share-Key:
<key>`, `Cad-Delete-Hash: <lowercase hex SHA-256 of the delete secret's 43-character text>`, `Content-Type: application/gzip`,
`Content-Length`, the archive as the body. `201` (made) or `200` (replaced), `{"id", "expires", "bytes"}`. A
`403` is a share of that id that another write secret made: the command makes a new share, new names and all,
once. A `409` is the service's create that lost a race: tried once more, then said with its `error` and `hint`.

**`DELETE /v1/shares/<id>`**: `Authorization: Bearer <delete secret>`. `204` deleted, `404` none (it expired,
or was deleted), `403` a secret that matches neither of its hashes.

Every other answer is the service's refusal, `{"error", "hint"}` with its status (400, 401, 411, 413, 429), said
with both. The service keeps neither secret, only the SHA-256 of each one's text (its ASCII bytes, never the bytes
it decodes to; a bearer's is hashed the same way), and never the key.
