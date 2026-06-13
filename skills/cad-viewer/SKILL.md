---
name: cad-viewer
description: Start or reuse CAD Viewer and return review links for explicit CAD, implicit CAD, robot-description, and G-code files. Use when visually reviewing `.step`, `.stp`, `.implicit.js`, `.implicit.mjs`, `.glb`, `.stl`, `.3mf`, `.gcode`, `.dxf`, `.urdf`, `.srdf`, or `.sdf` files, especially when handed off from CAD, implicit-cad, G-code, URDF, SRDF, or SDF generation skills.
---

# CAD Viewer

Provenance: maintained in [earthtojake/text-to-cad](https://github.com/earthtojake/text-to-cad).
Use the installed local skill files as the runtime source of truth; the
repository link is only for provenance and release review.

Use this skill to open existing or newly generated CAD, implicit CAD,
robot-description, DXF, or plain FDM G-code files in CAD Viewer and hand back
live review links. The expected input is one or more explicit file paths.

## Start Viewer

Start or reuse one local CAD Viewer with `npm run agent:start`, passing the
absolute artifact directory as `--dir`. The `agent:start` launcher owns port
selection, compatible-server reuse, directory activation, and the `?dir=` query
parameter. It activates reused servers through the Viewer's lightweight
directory activation API, without requiring agents to probe ports or trigger
catalog scans manually. Use the Viewer URL printed by `agent:start` as-is, then
add only a `file=` query value for the artifact you want to review.

Choose `--dir` as the absolute directory that contains the model
artifacts and sidecars, commonly `<repo>/models` or the consuming project's
equivalent model directory. The `file=` value must be relative to that `--dir`.
Do not manually choose ports, probe servers, rewrite `?dir=`, or start a
separate Viewer just to change directories.

Always start new local Viewer servers with `--shutdown-after 12h` so forgotten
review servers clean themselves up. Do not rely on a default shutdown; the
server stays alive until stopped unless this flag or `VIEWER_SERVER_LIFETIME_MS`
is set.

Run from this skill directory:

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --dir <absolute-model-root> --shutdown-after 12h
```

Use the printed Viewer URL and append `file=`:

```bash
http://127.0.0.1:<printed-port>/?dir=/absolute/project/models&file=path/to/model.step
```

If a non-Viewer process or another worktree's Viewer occupies the candidate
port, the launcher will continue automatically. In sandboxed agent environments,
local binding or probe failures such as `EPERM` or `EACCES` can be expected;
rerun the same command with the needed permission/escalation.

## Links

- Before returning any `file=` link, resolve `<dir>/<file>` and confirm the
  artifact exists. Pass the generated artifact (e.g. `.step`), not its
  generator source (e.g. `.py`). If the resolved path is missing, do not
  return the link, and instead report the problem and point to the correct
  generated artifact path.
- Return one Viewer URL per requested file.
- Start/reuse the Viewer once per absolute directory `--dir`, then append
  `file=<path>` for each requested file. The file path must be relative to
  `--dir`.
- For directory-only review links, return the URL printed by `agent:start`
  without adding `file=`.
- Do not stop an existing Viewer server unless the user asks.
- If Viewer startup fails, report the failure and continue with the owning skill's non-GUI validation or artifacts.

## Claude Preview

The viewer port is dynamic — it is chosen at startup and may differ across
worktrees. To integrate with the Claude Preview tool, add `--json` to the
`agent:start` command:

```bash
npm --prefix scripts/viewer run agent:start -- --host 127.0.0.1 --dir <absolute-model-root> --shutdown-after 12h --json
```

The launcher writes a JSON result line to stdout after the human-readable lines.
Parse it by taking the last line of stdout that begins with `{`:

```json
{"url":"http://127.0.0.1:<port>/?dir=<absolute-model-root>","port":<port>,"action":"reuse"}
```

`action` is `"reuse"` when an existing server was reused and is immediately
ready, or `"start"` when a new server process was spawned and may still be
initializing. For a `"start"` result, probe `GET /__cad/server` on the base
URL (e.g. `http://127.0.0.1:<port>/__cad/server`) until it returns HTTP 200
before passing the `url` value to the Claude Preview tool.

## Review Feedback

Users can attach feedback to a model from inside CAD Viewer: select a face,
edge, or part, open the feedback panel (message icon in the floating toolbar),
type what is wrong, and submit. Each submission is persisted as a sidecar next to
the reviewed model, in the same `--dir` model root:

- `<model>.feedback.json` — JSON array, one object appended per submission.
- `<model>.feedback/<id>.png` — screenshot for that submission (the `screenshot`
  field is a path relative to the `--dir` model root, not inlined).

Read `<model>.feedback.json` on demand (when the user says they left feedback, or
when re-reviewing a model) and act on each item. Item shape:

```json
{
  "id": "fb-0001",
  "createdAt": "<ISO8601>",
  "comment": "this fillet is too sharp",
  "references": [
    { "id": "f42", "label": "Face 42", "copyText": "f42",
      "partId": "...", "entityType": "ADVANCED_FACE", "selectorType": "face" }
  ],
  "camera": { "position": {...}, "target": {...}, "up": {...}, "zoom": 1 },
  "drawingStrokes": [ { "id": "...", "tool": "arrow", "points": [{"x":..,"y":..}] } ],
  "screenshot": "<model>.feedback/fb-0001.png"
}
```

Use `comment` for the user's intent and `references[].copyText` as the exact CAD
selector token to locate the entity to change. Open the `screenshot` PNG for
visual context, and use `camera` to reconstruct the exact view if needed. Empty
`references` means the comment applies to the whole model.

After you have acted on a feedback item, remove it from `<model>.feedback.json`
(and delete its `screenshot` PNG) so it is not processed again on the next read.
When every item is handled, delete the empty `<model>.feedback.json` and the
`<model>.feedback/` directory. Submitting new feedback recreates them. There is
no automatic notification or cleanup — feedback is only read when asked, and only
cleared by you once resolved.

## References

- Read `references/development.md` when the user asks to modify, debug, or
  iterate on CAD Viewer source.
- Read `references/viewer-features.md` when you need supported file types, Viewer controls, or file-specific feature details.
- Read `references/moveit2-server.md` only when the user specifically needs optional SRDF MoveIt2 IK or path-planning controls.
