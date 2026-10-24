# Annotation

The drawing tools — Pencil and Shapes — are the CAD viewer's own ink, with no drawing SDK behind it. A view has one
annotation: its marks are projected into the model in 3D, so they stay where they
were drawn from every angle, lying on the surface they were drawn on. The engine document, GLB, mesh, robot and DXF renderers offer them
([Pencil and Shapes](cad-renderer.md#pencil-and-shapes)).

## Pieces

- `annotation/session.js` — `useAnnotationSession`: the annotation's ink, what the tools
  put down next (the tool of the strip tool in hand, `pencil` — the pen, the highlighter or the eraser — and `shape` — the line first, the arrow, rectangle, ellipse or text — each kept while the other is up; `style`, the colour, stroke width and
  placement — `surface`, the default, or `plane` — of the tool in hand, kept per drawing kind in `styles`: `pen`, `highlighter` (yellow
  `#ffe600`; the others neon red) and `shapes`, which all five shapes share; the eraser has none) and the selection. Each add, erase, restyle of the selection
  (`restyle`) or fill of a closed shape (`fill`, joining its group) is one step
  in the file view's history (`renderers/kit/shell/useViewerHistory.js`, 200
  steps, shared with the renderer's own tools; without one the session keeps its
  own). Choosing what is drawn next never touches ink already down.
  `clear()` is a step; `discard()` drops the ink and takes its steps out of the
  history, for a model that changed under it. The session also keeps the views ink was drawn
  in (`views`, "view 1", "view 2"…), as labels for the agent: `noteView(view)` names the one a mark goes
  down in — a view drawn in before that is the same (`annotation/views.js`'s
  `sameView`: less than 2° of turn, 5% of zoom or pan, nothing else changed),
  or a new one.
- `annotation/views.js` — a view as a prompt carries it, in a snapshot job's own
  words: the camera (always orthographic), Clip when on, the one motion on
  screen (Explode, or the pose off its default as `kinematics` or
  `jointValues`), the parts hidden and isolated, and the picture's size. Never
  how it looks.
- `annotation/tools.js` — the two strip tools that draw and their tools: Pencil (`freedraw`, `highlighter`,
  `eraser`) and Shapes (`line`, `arrow`, `rectangle`, `ellipse`, `text`); `toolFamily(tool)`, `styleSlot(tool)` (the style slot a tool draws with; none for the eraser).
- `annotation/toolbar.jsx` — `AnnotationToolbar`, the sub-toolbar both strip tools share: one row (at every width; a phone's
  wraps where it has no room) — the tools of the strip tool that is up, a button each, the one in hand pressed (Pencil's Pen,
  Highlighter, Eraser; Shapes' Rectangle, Line, Arrow, Ellipse, Text); a rule; Color, Stroke width and Placement (On
  surface, On plane), dropdowns of the tool in hand's own style (disabled under the Eraser), Stroke width's glyph a straight line drawn at the weight (four, 1–6px, unnamed in its menu; Color's and its menus have no heading), then Clear;
  Undo and Redo are ⌘Z and ⇧⌘Z, with no buttons. A flat view (a DXF) passes `placements={false}`: its ink has nowhere to lie but the drawing.
  `annotationColors` offers
  neon swatches and a neutral that reads against the theme: white in dark mode,
  near-black in light mode. A native color picker adds a custom color.
  `AnnotationStylePickers` also restyles the selection's ink.
- `renderers/kit/tools/annotate/AnnotationSelectionBar.jsx` — the bar over the ink Select
  picked: its colour and weight, Fill for a closed shape (seeded
  inside its outline as it falls on the screen, `annotation/geometry.js`'s
  `interiorPoint` and `fillMarkAt`, and projected where the shape lies: On plane on the
  shape's own plane if its points are coplanar (a fitted plane), else On surface) and
  Delete.
- `annotation/geometry.js` — each tool's mark in screen space:
  - The highlighter (`highlighterMark`) is the pen's smoothed line at one broad width — five times the stroke width
    (`HIGHLIGHTER_WIDTH_FACTOR`) — 35% opaque (`HIGHLIGHTER_OPACITY`), round-ended, with no `widths`: an ordinary
    stroke mark (`width`, `opacity`) that no new field or kind describes. `strokeWidthAt` and `strokeSettingOf` convert
    between a stroke's width and the setting (1, 2, 4) for restyling. Translucent strokes are drawn once-only
    in the model (`core/common/annotation.js`: a stencil reference per stroke), so its overlapping segments do not darken.
  - The pen is smoothed as it is drawn, and each point's width comes from its
    pressure (a stylus's own, or simulated from speed with a mouse), using
    `perfect-freehand`.
  - Rectangles get rounded corners.
  - A fill finds the area inside a shape with
    `@text-to-cad/core/lib/annotation/fillRegion.js`.
- `renderers/kit/tools/annotate/AnnotationOverlay.jsx` — the surface over the viewport
  while Pencil or Shapes is up. It turns every gesture into marks, previews a mark on its
  own canvas as it is made, and puts it into the model when the gesture ends.
  Text is written where the surface is pressed: Enter, or a press elsewhere,
  puts it down as a text mark; Shift+Enter makes a new line; Escape drops it. The
  surface stops the press's mousedown, which would otherwise take the keyboard
  back from the text it just opened.
  Each mark names the view it was put down in, and is projected onto the surface it starts on.
  The drawing tools have no Select of their own:
  the viewer's Select picks ink (`RendererShell.jsx`, through the viewport's
  `annotationAt`), Shift adding to the pick, and Delete and Escape act on it (here too).
  The camera stays the person's between strokes: the wheel zooms, a right or
  middle drag orbits, and while Space is held the pointer is the view's.
- `mountAnnotations(runtime).update(items, selected, hovered)` haloes the ink Select
  picked, a wider line in the selection's blue behind it, and, fainter, the ink
  its pointer rests on (the shell's `hoveredAnnotation`, the marks drawn with it too). Ink draws after the model and its
  highlights (`ANNOTATION_RENDER_ORDER`), so a lit part never paints over it. Nothing else is drawn: no
  pane, no label. The ink's box (`runtime.annotationBounds`) widens the camera's depth range.
- `renderers/kit/tools/annotate/annotation3d.js` — projects a mark into the model.
  - Every point stays on the ray through where it was drawn, so from that view the ink is
    exactly what was drawn. **Ink lies on the surface it is drawn on.** Every mark has a
    **level**: the plane of the surface it starts on (a stroke's first point, a text mark's anchor
    corner, a fill's first outline point), found by `levelOf(runtime, start, size)`. A flat face's
    level is its own plane; a curved face's, its tangent plane at the start point (the geometry's
    smooth normal there). The normal is the surface's, **not the view direction**: from any
    angle, a mark started on a plate's top has the plate's top plane as its level. No sheet, no
    pane: nothing is made per view, and nothing is held between marks.
  - **Placement** says what a point does, per mark at draw time. *On surface* (the default): each
    point drops onto the visible surface under it (a stroke follows a curved face and steps across
    faces); a point with nothing under it (past the model's edge, over a through-hole) takes the
    level: its ray met with the level plane, so a stroke that trails off a face carries on at that
    face's level. *On plane*: every point is its ray met with the level plane — flat across a
    curved face, staying on the tangent plane where it started, and carried off the surface at
    the same level. Both modes agree off the surface. A stroke's line is first split into pieces
    of a few pixels (`subdivideStroke`) in both, so a two-point line reads the surface all along
    it; the pen's widths are split with it. In On surface a point takes the nearest depth within
    its own reach — half the stroke's width and a pixel, never a neighbour's, so a slanted face
    does not lift the ink off it; a fill point by point. Every point is then two screen pixels toward
    the eye, text eight. Text is a card facing the view, at the level's depth under its anchor
    corner, in both modes. Ink already down never moves with the setting.
  - **The level, when the start is over nothing** (in order):
    1. the surface under the start point (a ray through it);
    2. the **visible surface nearest to the start on the screen**: in a depth render of the parts
       over the window (read back at no more than 256 pixels on the long side), the covered pixel
       with the least screen distance to the start, found by searching outward in rings of pixels
       from where the start falls (the nearer of two as far wins), then ray-cast through its middle
       for the surface point and normal there;
    3. nothing drawn in the window, but a model: the drawn surface **nearest to the window on the
       screen** — the same render over a region round the window, large enough to hold the model's box
       on screen (the window's size on each side where part of the box is behind the eye), at low
       resolution; the covered pixel with the least screen distance to the window rect;
    4. no model drawn: the plane through the origin facing the view.

    "Drawn" is what the depth render sees: hidden parts and what Clip cuts away do not count.
    Clip's cap faces are not part meshes (stencil fills, `sectionCaps.js`), so they are not in
    the render: through a cut the level is the surface seen inside. Without a GPU float render the
    same reads come from rays, at a far lower resolution. The depth renders are made only when a
    level needs them, once for all the marks put down together (`projectAnnotations`).
  - **Grazing guard:** a level whose plane is nearly edge-on to the view (|normal · view
    direction| below 0.08) is replaced by the plane facing the view through the same point, else rays
    would stretch the mark along the plane.
  - `projectAnnotations(runtime, marks, size, { placement, topologyAt, level })` projects marks,
    finding each one's level inside; `level` ({ point, normal }) gives all of them one instead (a fill
    of a flat shape lies on the shape's plane).
  - What the model hides of the ink is drawn faint through it (core's `ANNOTATION_HIDDEN_OPACITY`,
    on the viewer and in snapshots), so a profile drawn through a part's middle is seen.
  - Every mark is in model coordinates: it stays where it was drawn whatever
    Explode, Position or hiding a part does to the model. Clip cuts it.
    `touches` says what it was drawn over, most first, the same for either placement: the faces and edges the
    renderer names under it (`ref`, a prompt reference, from the shell's
    `inkTouches`), each with its part; without it, the parts.
  - The projected ink is plain data (`AnnotationItem`): an annotation mark
    (`@text-to-cad/core/common/annotation.js`), kept across scene rebuilds.
    `mountAnnotations` draws it in a viewer runtime and `update` draws only the
    marks a change adds; the objects are core's, the ones a snapshot draws an
    annotation with. The preview
    holds a finished mark until the scene has drawn it. `annotationDocumentOf` writes the
    annotation as an annotation file. The file format is unchanged: marks are 3D points; the level is the viewer's own.
  - A double-click under Select (Look at, `kit/camera/lookAt.js`) is navigation only; it sets
    no plane for ink.

## Lifetime and capture

The live annotation is session-only: it is never written to tab or file state. It
outlives the drawing tools being put down, because the ink stays in the model and the next
one adds to it. It goes when the person clears it, or when the model it was
drawn on changes.

⌘C / Ctrl+C while Pencil or Shapes is up copies the view as it is on screen, ink
included, to the clipboard as a PNG.

Quick Edit captures the current view and distinct views with remaining ink when
Copy Prompt, Queue or Send is pressed (`host.promptFiles`). The snapshot packet
includes shared annotation and measurements: up to 1 KiB of compact UTF-8 JSON
travels inline, and larger packets are saved to a temporary `.snapshot.json`.
No images are rendered at handoff. Save inline JSON to a file, then
`cadgen snapshot <document> <out.png> --annotation <file> --camera authored` draws the
view the ink was drawn in over the model, or over an edit of it.
The Annotation chip does not copy references or save individual files.
Queue and Send clear the annotation with the note; Copy Prompt keeps it.
