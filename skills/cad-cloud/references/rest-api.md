# REST API

The REST API does what the MCP tools do, for scripts and for hosts without MCP:
JSON in, JSON out, one service layer under both, so the validation, caps and
results match the tools. Every path below is under the server's address,
`https://<host>`, the same host that appears in build links.

## Authentication

Reading a build is public: its id is the secret, as it is for its link. Every
request that runs compute or names you needs `Authorization: Bearer <key>`. An
API key starts with `t2c_` and is created on the server's account page, which
also lists builds and the MCP address; a key cannot create keys. Keys are
secrets: keep them out of files, links, logs and chat, and delete a key that
leaks. Without a valid key the server answers 401.

## Requests

| Request | Same as | Needs a key | Body or query |
| --- | --- | --- | --- |
| `POST /v1/builds` | `cad_build` | yes | JSON `files`, `entry`, `base`, `delete`, `title`, `pythonpath`, `wait` |
| `GET /v1/builds/<id>` | `cad_status` | no | `wait` |
| `GET /v1/builds` | `cad_builds` | yes | `limit` (default 20) |
| `GET /v1/builds/<id>/files` | `cad_files` | no | none |
| `GET /v1/builds/<id>/files/<path>` | `cad_files` with `path` | no | none |
| `POST /v1/builds/<id>/snapshot` | `cad_snapshot` | yes | JSON `file`, `args`, `format`, `wait` |
| `POST /v1/builds/<id>/inspect` | `cad_inspect` | yes | JSON `code`, `wait` |
| `GET /v1/jobs/<id>` | `cad_status` for a job | yes | `wait` |
| `GET /v1/me` | none | yes | none |
| `GET /v1/api-keys`, `DELETE /v1/api-keys/<id>` | none | yes | none |

`files`, `entry`, `base`, `delete`, `title` and `pythonpath` mean what they do
in the tools, as do `file`, `args`, `format` and `code`: see [SKILL.md](../SKILL.md)
and [snapshots](snapshots.md). `wait` is a number of seconds, at most the tools'
40; without it a request returns at once with the build or job still `queued`.

A build request:

```json
{
  "files": {"src/bracket.py": "<script text>"},
  "entry": "src/bracket.py",
  "title": "Bracket, 40 x 20 x 6 mm",
  "wait": 40
}
```

An edit of that build sends the previous id and only what changed; `entry` is
the base build's unless given:

```json
{
  "base": "<previous id>",
  "files": {"src/bracket.py": "<new script text>"},
  "delete": []
}
```

## Results

A build carries `id`, `status` (`queued`, `running`, `succeeded` or `failed`),
`title`, `link` (the main file's link), `primary`, `outputs` (paths), `entry`,
`pythonpath`, `base`, `error`, `progress`, `log` (the tail), `thumbnail` (an image
URL), `view` (`available`, `error`), `flags` (`network`, `dropped`), `cadgen` and
timestamps. `error` holds `message`, `file`, `line` and `kind`: `model`,
`timeout`, `limit`, `runner` or `infra`. A request that matched an identical
earlier build also carries `deduped`.

A job (a snapshot or an inspection) carries `id`, `kind`, `build`, `status`,
`error`, `progress`, `exitCode`, `stdout`, `stderr`, `log`, `images` (each with a
`url`, `type` and `path`) and `flags`.

`GET /v1/builds/<id>/files` lists each file with its `path`, `kind` (`input` or
`output`), `bytes`, `sha256`, `url` and `download`. Reading one file returns text
inline up to 1 MiB and redirects to the stored object otherwise. `GET /v1/me`
returns the user, today's compute usage and the limits.

An error is `{"error": {"code": ..., "message": ...}}` with the HTTP status that
fits: 400 for a request the validator refuses, 401 without a key, 404 for an
unknown build or job, 409 while a build or job of yours is still running (the
message names it), and 429 over a cap, with the cap and its reset time in the
message.

## Waiting

A build, a snapshot and an inspection run in a sandbox, so a request can return
before the work is done. Poll the build or job with `wait` until its status is
`succeeded` or `failed`; do not resubmit. Submit one build at a time, and one
snapshot or inspection at a time, and only against a finished build. An
identical submission returns the existing build.
