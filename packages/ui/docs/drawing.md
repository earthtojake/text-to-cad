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

The editor offers no saving, loading, export, library or Help menus. Save/open
shortcuts and SDK actions are disabled, including the command palette that
otherwise includes hardcoded export and library actions. The main menu retains
only **Clear canvas**, alongside the normal drawing tools, undo/redo and zoom.
Dropped scene/library files and pasted scene files are rejected. Dropped raster
images are inserted directly as images so even PNG metadata cannot replace the
current sketch. Ordinary copied elements and raster image insertion remain
available; pasted elements pass bounded scene validation.

Controls use the host's system font and 13px UI token, neutral colors, compact
28px buttons and 12px canvas-edge padding. Drawn text keeps its selected font.
Persistent controls stay at the top in desktop and narrow layouts. Pan joins the
drawing tools; lock is hidden. Narrow layouts place menu/style/undo controls in a
compact second row, with selected-shape properties opening beneath it. These
styles depend on Excalidraw's pinned DOM; verify both layouts when upgrading.
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

## Reusing the editor for viewport annotations

The editor is independent of explorer tabs and prompt destinations. Its
`mode="overlay"` uses a transparent drawing surface and defaults PNG export
to transparent ink; `exportPng({ background: false })` also works explicitly.
Use this same component and document contract when replacing screen-space
viewer annotations. A host/renderer's integration must own the background
capture, viewport coordinate mapping, camera lock/invalidation, and composition
of ink with the captured image and any selected references in one prompt bundle.
The current PNG export is content-cropped, not viewport-aligned: do not place
it over a CAD screenshot without mapping its bounds. The existing CAD overlay
has not been replaced by this tab feature, and geometry-snapped surface lines
must retain their CAD-specific implementation when that migration happens.

## Offline assets and upgrades

Desktop's `scripts/drawing-assets.mjs` serves the editor fonts in development
and emits them into the packaged renderer. A script sets the asset directory
before the editor imports. The SDK's CDN fallback is also redirected locally
by a version-guarded build adaptation, applied during Vite dependency
optimization as well as production transforms. No font binaries are committed.
The distribution contains 233 WOFF2 files and unmodified OFL Liberation Sans
2.1.5 TTF from pinned `@betteroffice/fonts`, plus font and editor notices.
The SDK's older GPL Liberation font is excluded. Review the guarded font URI
and fallback adaptations, notices, and offline Electron test when upgrading.

Validation lives in core's `drawing.test.js`, desktop's drawing document/tab,
prompt, tools and asset unit tests, and `tests/e2e/drawing.spec.ts`. The latter
draws real ink, checks PNG decoding and disabled persistence routes, and
reloads the app profile while blocking external requests.
