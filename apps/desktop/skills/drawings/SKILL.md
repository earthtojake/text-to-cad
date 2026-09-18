---
name: drawings
description: Use temporary light-mode sketches in Hardcore as visual prompt context.
---

# Drawings

Use drawings `open_drawing` with an optional descriptive `title` to open a blank canvas. Use `rename_drawing` with its `tabId` and a new `title` to rename an existing sketch. The user can also edit its name in the drawing header. Renaming preserves the scene and does not switch projects. The canvas is always light and remains in memory while the tab is open, including across project or tab switches. Closing it or restarting Hardcore discards it.

Use `drawing_state` for its identity and element count and `capture_drawing` to see its PNG. Use workspace `list_open_tabs` / `show_tab` to find or present it. There are no drawing file save/load tools. Do not manufacture persistence, start another editor or claim a sketch was saved.

The user draws in the canvas and chooses Add to prompt to attach the image to their current compatible draft. This preserves their text and does not submit the prompt. Interpret sketches with their accompanying instructions; do not infer exact dimensions from image scale.
