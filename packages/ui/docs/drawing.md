# Drawing editor

`@hardcore/ui/drawing` exports `DrawingEditor` and its `DrawingController`, plus
`exportDrawingScenePng(serialized)` for an unfocused retained scene capture.
It wraps Excalidraw 0.18.1 (MIT), supports React 19, and is imported lazily by
the desktop Drawing tab. Web and docs do not import it. Excalidraw was chosen
for its permissive license, freehand/shapes/text/image tools, in-memory scene snapshots,
and canvas export; it does not need a production license key or hosted service.

## Ownership

The shared editor owns drawing interaction, selection, undo/redo, zoom and
rendering. It receives the retained scene, sketch name and callbacks. Both its canvas
and controls always use the light appearance; standalone canvases are white.
It does not discover a platform or session.
The host owns tab lifetime, in-memory scene retention, font asset delivery and
prompt routing. Do not add Electron imports, app stores, autosave or provider
calls to this component. The browser editing gestures inside Excalidraw are
local; collaboration, external libraries, AI features, built-in file saving
and theme switching are not offered by this wrapper.

The editor offers no saving, loading, export, library or Help routes. Save/open
shortcuts and SDK actions are disabled, including the command palette that
otherwise includes hardcoded export and library actions. Dropped scene/library
files and pasted scene files are rejected. Dropped raster images are inserted
directly as images so even PNG metadata cannot replace the current sketch.
Ordinary copied elements and raster image insertion remain available; pasted
elements pass bounded scene validation.

Every SDK control is hidden. The canvases, the in-place text editor, the context
menu remain; SDK toast notifications are hidden, and `DrawingToolbar` (`drawing/toolbar.jsx`) is the
one control surface: Select and move drawings, Pan view, Pen, Line, Arrow,
Rectangle, Ellipse, Text, Fill area, and Eraser, followed by Color, Undo, Redo
and Clear drawing, in the floating-toolbar button primitive. It imports nothing of the SDK.
The standalone editor renders it top-centre and always light (its tokens are
re-declared inside the editor, and the color strip is in the toolbar's flow
rather than a portalled popover, so a dark application cannot restyle it). A
host that places the toolbar itself passes `toolbar={false}` and drives the same
component from `useDrawingSession` (`drawing/session.js`), as the CAD viewport
does. In CAD, Draw's corner menu is a narrow ephemeral dropdown with separate
tool and settings groups divided by a separator, without internal headings
(`layout="panel"`). Picking a tool changes the Draw button's icon and closes the
menu. Undo, Redo and Color keep it open; Clear drawing closes it. Outside click,
Escape or pressing Draw again dismisses the menu without ending Draw. Leaving
Draw closes the menu and ends the session. The viewport’s Copy Drawing action,
which copies the view with its ink to the host's clipboard as a PNG, appears only
while the sketch contains visible elements; clearing or undoing the last element
hides it again. These styles depend on Excalidraw's pinned DOM; verify both hosts when
upgrading.

Tools are locked in the SDK's sense: a shape is followed by another of the same
tool instead of a return to selection. Color sets what is drawn next
(`currentItemStrokeColor`) and never recolors existing elements, selected or
not; the swatches are neon so ink stands out from a shaded model. Fill area is
this editor's tool, not the SDK's (`drawing/fill.ts`): a press renders the ink
without earlier fills, finds the area around the point with
`@hardcore/core/lib/drawing/fillRegion.js` — as drawn, then with nearby stroke
ends joined, then guessed from what the ink does enclose, ignoring rays that
leave through a gap — and appends a closed, strokeless, 35%-opacity line element
(inserting below existing elements would cost a second, invisible undo step). A fill is an ordinary element: it moves, erases and undoes. The
SDK's lock, image, frame, embed, diamond and laser tools are not offered and
their shortcut keys are blocked.
Drawing names belong to the host, which updates the editor name and prompt
attachment title without recreating the scene or persisting it.

```tsx
import { DrawingEditor } from '@hardcore/ui/drawing';

<DrawingEditor initialScene={sceneJson}
  onReady={controller => { drawing.current = controller; }}
  onContentChange={setHasContent} />;
```

`onReady(null)` releases the mounted controller. A host can snapshot with
`serialize()` on unmount and reuse that JSON on the next mount. Do not
serialize on every pointer event: the desktop retains a lazy reader while
mounted and serializes only for final unmount. Scene and
viewport survive remounts; Excalidraw's undo history belongs to the mounted
editor. Closing a tab releases its reader before unmount, so late cleanup
cannot recreate the closed drawing.

`exportPng()` snapshots elements/files before its first asynchronous step,
then encodes a PNG capped at 2048 pixels on the longest side, with 24 pixels
of content padding. Background export defaults on for a standalone canvas;
exports use authored colors.
An empty scene fails instead of delivering an empty attachment. The host
passes the pending PNG directly to `PromptContextPort.deliver` during the
gesture; this binds the destination before encoding finishes. Never await
encoding and then look up whichever chat happens to be active.

## In-memory scenes

`@hardcore/core/drawing` is the pure document boundary. `parseDrawingScene`
accepts Excalidraw v2 JSON, bounds it to 20 MiB and 10,000 elements, validates
coordinates, and retains only portable app state. Supported content is
freehand ink, lines, arrows, rectangles, ellipses, diamonds, text, frames and
embedded PNG/JPEG/GIF/WebP images. External images, live web embeds, navigation
links and host-specific custom data are rejected or discarded. The SDK
performs its own element restoration after this validation. This is a visual
sketch format, not CAD topology or an inspect/selector reference format.

Desktop keeps scenes and tab metadata only in renderer memory, separate from
SQLite's `explorer_tabs`. Tab/project switches retain them; tab close, project
removal, window reload and app exit discard them. Prompt attachments are copies
and follow
the existing draft/transcript lifetime after being added; closing the drawing
does not delete an already attached image.

## Viewport annotations

The editor is independent of explorer tabs and prompt destinations. Its
`mode="overlay"` uses a transparent drawing surface, red default ink and
transparent PNG export; `exportPng({ background: false })` also works explicitly.
The STEP renderer's Draw tool is this component ([Draw](cad-renderer.md#draw));
no other file family offers it.

`toolbar={false}` leaves the toolbar to the host, and `initialTool` chooses the
tool a new editor opens on. The controller drives the editor: `setTool` (one of
`DRAWING_TOOLS`), `setColor`, `undo`/`redo` (the SDK exposes no history API, so
these press its own shortcut on the editor), an undoable `clear`, and
`inkCanvas()`. `onToolChange` and `onColorChange` report the SDK's state whoever
changed it. The overlay stays hidden until the SDK has the given scene, because
its default page is white.

`onViewportChange({ scrollX, scrollY, zoom })` reports pan and zoom made inside
the editor; a scene point `s` is drawn at `(s + scroll) * zoom` CSS pixels from
the editor's top-left. A host that moves its own background with the ink (the
CAD camera) follows this mapping. The host still owns the background capture,
the camera lock and the composition of ink, image and references into one prompt
bundle. `exportPng` is content-cropped, not viewport-aligned: compose
`inkCanvas()` instead, which is the committed ink exactly as displayed,
viewport-sized, without selection handles, at the editor's own pixel ratio.

## Offline assets and upgrades

The Vite plugin `@hardcore/ui/drawing-assets` (`scripts/drawing-assets.mjs`,
notices in `licenses/excalidraw/`) serves the editor fonts in development and
emits them into a host's build. Every host that loads this entry point adds it
to its Vite config: desktop's renderer and the web Viewer both do. A script
sets the asset directory before the editor imports. The SDK's CDN fallback is
also redirected locally by a version-guarded build adaptation, applied during
Vite dependency optimization (esbuild on Vite 7, Rolldown on Vite 8) as well
as production transforms, so a missing font is a local miss and a system font,
never a network request. No font binaries are committed.

The full set, which desktop ships, is 233 WOFF2 files and unmodified OFL
Liberation Sans 2.1.5 TTF from pinned `@betteroffice/fonts`, plus font and
editor notices: 246 files, 12.9 MiB. The SDK's older GPL Liberation font is
excluded. `drawingAssetsPlugin({ exclude })` takes RegExps tested against each
emitted file name; a match is neither served nor emitted. The web Viewer ships
inside a Python wheel and passes `[/\/fonts\/Xiaolai\//]`, dropping the 209-file
CJK family: 37 files, 0.8 MiB. Review the guarded font URI and fallback
adaptations, notices, and offline Electron test when upgrading.

Validation lives in core's `drawing.test.js`, desktop's drawing document/tab,
prompt, tools and asset unit tests (`tests/unit/main/drawing-assets.test.ts`
covers this plugin), and `tests/e2e/drawing.spec.ts`. The latter
draws real ink, checks PNG decoding and disabled persistence routes, and
reloads the app profile while blocking external requests.

While Draw is active the view cube stays visible but takes no drag or snap until
Draw ends: drawing must not change the camera through it. Display stays usable
because it is a tool of its own; choosing it leaves Draw.

New freehand strokes use `2 / 4.25` stroke width to compensate for Excalidraw’s
freehand brush scaling; line, arrow, rectangle, and ellipse use width `2`.
Toolbar and keyboard tool changes apply the same defaults without rewriting
existing strokes.
