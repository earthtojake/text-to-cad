---
name: hardcore-app
description: How to work inside the Hardcore desktop app, where the CAD Viewer is beside the chat and files are shown with the `open_file` tool. Installed only by Hardcore; replaces the `cad` skill's `$cad-viewer` hand-off. Use whenever a CAD, drawing, mesh, or robot-description file is created, changed, or reviewed in a Hardcore session.
---

# Working inside Hardcore

You are running inside Hardcore. The person sees three panes: their projects,
this conversation, and an explorer that renders any file you name — code,
markdown, images, and every CAD format (`.step .stp .glb .stl .3mf .dxf .urdf
.srdf .sdf`) through the CAD Viewer's own surface. The viewer is already
there. This skill says how to use it; the `cad`, `dxf`, `urdf`, `srdf`, `sdf`
and `gcode` skills still say how to build the files.

## Never start a viewer, never post a link

- Do not run `cadgen viewer`, `python -m cadgen.viewer`, or anything that
  serves a URL for review, and do not write `http://127.0.0.1:…` links. Hardcore
  runs one viewer per project on its own; a second one is noise the person
  cannot see.
- Where the `cad` skill says to hand paths to `$cad-viewer`, do this instead:
  call `open_file` with the path. That call is the hand-off.
- Reference files by their path relative to the project root
  (`STEP/bracket.step`, not `/Users/…/STEP/bracket.step`); Hardcore turns them
  into links the person can click.

## The tools Hardcore gives you

| Tool | Call it when |
| --- | --- |
| `open_file(path)` | You want the person to look at a file. Opens the right renderer for its type and focuses that tab. Works for CAD files, drawings, code and markdown alike. |
| `reveal(path)` | You want to point at a file or folder in the tree without switching what is open. |
| `attach_snapshot(path)` | You rendered a PNG (`cadgen step snapshot`) and want it in the transcript. The image appears inline; otherwise a snapshot is a file the person has to go and find. |
| `list_open_tabs()` | You need to know what the person is already looking at before opening more. |
| `viewer_state()` | You want the file currently in the viewer before acting on "this part" or "that face". |
| `open_url(url)` | A datasheet, a docs page or a step.parts listing belongs beside the work. |

Call `open_file` on the artifact (`STEP/bracket.step`), not on the script that
made it. Open the file the person asked about, not every file you touched.

## Publish geometry at milestones

- Finish each build before naming its output: run the model script, wait for
  its `built <path>` line, then `open_file` that path. A path announced
  mid-build opens a stale or missing file.
- On long tasks, open intermediate geometry as soon as a part is recognisable —
  a first solid, a mated pair, a posed assembly — so the person can steer before
  you invest in details. Say what to look at and what is still missing.
- When a file changes on disk the open tab reloads by itself; call `open_file`
  again only to bring a different file forward.

## What the person can do that you cannot

In the viewer they can orbit, zoom, section, measure between faces, isolate a
component, toggle layers of a DXF, pose joints, play a `.step.js` animation,
and edit the model script beside it and rebuild. So:

- Do not narrate what a snapshot already shows; describe what to check.
- Ask them to measure or section when a question needs a view you cannot
  render in one snapshot.
- Expect edits: when they say a dimension is wrong, reread the script before
  changing it — they may have already changed it.

## Finishing a CAD turn

1. Validate as the `cad` skill requires: `cadgen step inspect refs … --facts
   --planes --positioning`, the spec-driven `measure`/`align` checks, and
   `cadgen step inspect validate …`. Report only checks that ran.
2. Snapshot the primary artifact with `cadgen step snapshot` (or the mesh
   door), then `attach_snapshot` the PNG. Read it yourself first.
3. `open_file` the primary artifact so it is on screen when you stop.
4. List the files you created or changed, one per line, relative paths.
5. Guide the eye: two or three sentences on what to look at, what to measure,
   and what you are unsure of. Assumptions and caveats go here, not in a preamble.

If a tool call fails, say so in one line and continue with the CLI validation
and the snapshot; do not fall back to starting a viewer.
