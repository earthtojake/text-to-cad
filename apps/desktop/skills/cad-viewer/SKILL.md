---
name: cad-viewer
description: Inspect and present CAD files inside Hardcore using its CAD and workspace MCP tools. Use for STEP, mesh and robot-description viewer interaction.
---

# CAD inside Hardcore

The embedded viewer already belongs to the workspace. Use workspace `open_file` on a completed artifact instead of starting `cadgen viewer` or posting a localhost link. Use `list_open_tabs` for tab IDs and `show_tab` to display a model before controlling it.

The `cad` integration supplies `viewer_state`, `select_reference` and `capture_view`. Viewer state includes model revision, actual selection and camera. Inactive snapshots are marked `active:false`; activate the model before mutating or capturing its viewport. Captures are tool results, not a submitted prompt.

Use the bundled `cad` authoring skill for modeling and exact inspection: cadgen.read_step, cadgen.read_scene and cadgen.geometry. Viewer feature recognition is not authoring history or a replacement for kernel inspection. Resolve copied topology references against the matching scene revision.

The app supplies cadgen and Python on PATH. Never install cadgen or replace the bundled runtime to repair an app fault. Report runtime failure.

Finish generation before opening the artifact. Existing file tabs refresh after disk changes. Show useful intermediate artifacts on long work so the user can steer. Inspect a snapshot yourself before describing it. The workspace `attach_snapshot` tool reads an already-written PNG into the transcript.
