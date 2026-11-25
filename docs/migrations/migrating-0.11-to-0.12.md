# Migrating from 0.11 to 0.12

This guide covers what changes for a person and for a program that talks to the cad server when cad
stops keeping a record of each document. A document is its file: cad keeps one small library file
(the project folders, the files you opened or pinned) and nothing else about a document. Nothing
needs doing by hand: the first start of the new release carries what it can and removes the rest.

Each change names its tier of the compatibility law ([law 14](../../packages/cad/README.md#the-design-laws),
"Compatibility, by who pays for a break"), which says what a change of its kind keeps working.

## Your data (tier 3)

The first start reads the records 0.11 kept in the state folder (`documents/`, `recents/`) once,
writes `library.json` there, and removes them. `cad server status` says what it did in one line
while that server runs.

| 0.11 | Now |
| --- | --- |
| A CAD file you opened, with its pin | Carried: it is in Recents as before, pinned as before |
| A model a script built | Listed again, as its `.xbf`, the next time its script runs. Its pin and its opened time are not carried: 0.11's record of a model named no file |
| A model's id (from its script and function) | The id of its `.xbf`. An old id, in a link or a command, names nothing: `no document <id> is held`. Running the script prints the new id and link |
| A card's picture | Taken again the next time its page is open |
| A file that was already gone | Not carried |

## Documents and the server (tier 1)

- **A document lives while its file does.** With a model's `.xbf` gone, its id names nothing, and
  running its script writes the file again. The states `unsaved` and `detached` are gone, and no
  message names a command that builds a document again.
- **`cad delete` is removed.** It is answered as any unknown command is. cad has no copy of a
  document to delete: to be rid of one, delete its file. To take a file off the viewer's lists and
  leave it on disk, use Remove on its card. The rule that keeps a command the skills used working for
  30 days was waived for this one by the repository's owner.
- **A run takes a model from its `.xbf` whenever the file holds the model's key**, whoever wrote
  the file last. 0.11 built again when the file was not the one the server had written.
- **A script moved to another folder is a new document**, with the id of its `.xbf` there. Moved
  together with its `.xbf`, it is taken from that file; moved alone, it is built.
- **The first run after the server restarts says no "was ..." line** under its report: what it
  compares against is kept in memory.
- **`cad server status`** lists `live`, `building`, `failed` and `held` documents, and no command
  beside any. With `--json`, the key `identity` is gone and `library` says what the first start
  carried.

## The viewer

- **Recents lists a model as its file** (`arm.xbf`), with the file's size and time, and a file that
  is gone is on no list.

## The HTTP API (tier 4)

| Route | Change |
| --- | --- |
| `GET /api/v1/documents` rows | `record` is always `file`; a model's row has `path` its `.xbf`, `name` the file's name, `size` the file's. `script`, `rebuild`, `shown` and `file` are gone. A file that is gone is not listed |
| `GET /api/v1/documents/<id>` and every read by id | A 404 is `{"error", "hint"}`: no `state`, no `rebuild`. `entry.project` gains `folder` |
| `DELETE /api/v1/documents/<id>` | 405. `PATCH /api/v1/documents` with `remove` forgets a file's entry; `delete` is refused as an unknown action |
