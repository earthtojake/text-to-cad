---
title: The CAD Viewer
description: How to open the CAD Viewer, what it shows for each kind of file, how it follows rebuilds, and how to export from it and update it.
---

The CAD Viewer is where you look at what your agent builds. It runs on your computer, in your browser, and shows models, meshes, drawings, robots and boards. Your agent normally opens it.

## Opening it

When your agent shows a model, it gives you the model's page or opens it in your app. A model's page is `/<id>` on the viewer's address, and it is the `view:` line that `cad run` prints.

To open the viewer yourself, run:

```bash
cad viewer
```

With no file it opens the home in your browser. With a file it opens that file's page, as in `cad viewer part.step`. It prints each page's URL, and `--no-open` prints the URL without opening a browser. One viewer serves your whole computer, started the first time something needs it, and `cad stop` stops it. A page's link carries a token for your session, so keep it private. If a link has expired or is refused, ask your agent to open the model again.

## What it shows

Each kind of file gets its own tools. Every 3D view ends its tool strip with Projection, Display and Preview, and has a view cube at the bottom right.

- **Models, STEP and xbf**: select faces, edges and parts, measure, explode an assembly, clip it, and read its structure in the view's panel. Selection and measurement are exact because the server holds the B-rep (the solid's exact surfaces).
- **Meshes (GLB, STL, 3MF)**: orbit and clip. A GLB or 3MF can also be measured, but only approximately, on triangles.
- **Drawings (DXF)**: a flat 2D canvas with pan and zoom, and a Layers tab where the file has layers.
- **Robots (URDF, SRDF, SDF)**: the links, and a Position tab to pose the joints.
- **Boards (KiCad)**: a board in 2D or 3D, and a schematic you can enter sheet by sheet. You do not need KiCad installed to view one.

Preview is a full-page mode that draws the model rendered and plays its animations from a bar under it. See [document types](/docs/document-types) for each format.

On a STEP or a robot, pick something, draw or measure, and Quick Edit appears at the top right. Write a note, use Copy Prompt and paste it into your agent: the prompt names the file and what you picked.

## Live updates

A model's page follows its document. When your agent edits the script and runs `cad run` again, the page you have open updates, and only the parts that changed are fetched. The camera stays where you put it. If a build fails, the page says so, and you can dismiss the message to inspect the previous version.

If the server restarts, the page shows the model as last built. If its saved build is gone, the page names the `cad run` command that rebuilds it.

## The home and Recents

The bare address is the home: the models and files you have opened, pinned ones first and then by latest activity, as tiles or a list. You can filter, search and pin them. **Open** picks a file from your computer where the system has a file chooser. A tile's menu can delete a model: that removes the server's record and its saved build, and leaves your script and exported files alone.

The name menu under the file's name has a **Models** tab and a **Files** explorer.

## Exporting from the viewer

Export is in the file menu, the three dots beside the file's name. It lists the formats that page can write. A model, STEP or xbf offers STEP, STL, 3MF, GLB and xbf, and DXF where the view is flat. A GLB, STL or 3MF page converts to the other two mesh formats.

The file arrives as an ordinary browser download, so where it goes is your browser's setting. The viewer writes the model as its code built it; a posed or partial file is a different model. [Exports](repo:skills/cad/references/exports.md) covers the command-line route.

## Updating

When a newer text-to-cad release is out and has not installed itself, an update button appears at the right of the navbar. Click it and text-to-cad updates in every agent app, then the page reloads itself into the new release. Releases that break nothing install themselves. [Updates](/docs/install#updates) has the details.

## The CAD app

Agent apps that can draw an interface show the same viewer inside the app: cards in Claude Desktop and Cursor, tabs in the Codex app. It has the same navbar, tools and view cube as the browser page, but no Export, because it has no downloads. Use the browser page or `cad` for files. See [supported agents](/docs/agents) for what each app shows, and [the viewer and the CAD app](/docs/architecture/viewer-and-cad-app) for how it works.
