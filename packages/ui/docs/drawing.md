# Drawing editor

`@hardcore/ui/drawing` exports `DrawingEditor` and its `DrawingController`.
It wraps Excalidraw 0.18.1 (MIT), supports React 19, and is imported lazily by
the desktop Drawing tab. Web and docs do not import it. Excalidraw was chosen
for its permissive license, freehand/shapes/text/image tools, editable JSON,
and canvas export; it does not need a production license key or hosted service.

## Ownership

The shared editor owns drawing interaction, selection, undo/redo, zoom and
rendering. It receives the initial scene, resolved light/dark appearance,
document name and callbacks. It does not discover a platform or session.
The host owns tab lifetime, storage, file dialogs, font asset delivery and
prompt routing. Do not add Electron imports, app stores, autosave or provider
calls to this component. The browser editing gestures inside Excalidraw are
local; collaboration, external libraries, AI features, built-in file saving
and theme switching are not offered by this wrapper.

Inject `onSaveCopy`, `onOpenFile` and `onImportFile` to handle explicit saving,
file picking and dropped scene files. SDK save/open actions, including its
save shortcut and command palette, route through these callbacks. Returning
from a save never gives the SDK a file handle. Imported scenes and pasted
elements pass the same document validation; image insertion accepts the
portable raster formats so switching tabs cannot strand an unsupported image.

```tsx
import { DrawingEditor } from '@hardcore/ui/drawing';

<DrawingEditor initialScene={sceneJson} theme={colorScheme}
  onReady={controller => { drawing.current = controller; }}
  onContentChange={setHasContent} />;
```

`onReady(null)` releases the mounted controller. A host can snapshot with
`serialize()` on unmount and reuse that JSON on the next mount. Do not
serialize on every pointer event: the desktop retains a lazy reader while
mounted and serializes only for a requested save or final unmount. Scene and
viewport survive remounts; Excalidraw's undo history belongs to the mounted
editor. Closing a tab releases its reader before unmount, so late cleanup
cannot recreate the closed drawing.

`exportPng()` snapshots elements/files before its first asynchronous step,
then encodes a PNG capped at 2048 pixels on the longest side, with 24 pixels
of content padding. Background export defaults on for a standalone canvas;
exports use authored colors rather than the dark UI's display inversion.
An empty scene fails instead of delivering an empty attachment. The host
passes the pending PNG directly to `PromptContextPort.deliver` during the
gesture; this binds the destination before encoding finishes. Never await
encoding and then look up whichever chat happens to be active.

## Documents and explicit persistence

`@hardcore/core/drawing` is the pure document boundary. `parseDrawingScene`
accepts Excalidraw v2 JSON, bounds it to 20 MiB and 10,000 elements, validates
coordinates, and retains only portable app state. Supported content is
freehand ink, lines, arrows, rectangles, ellipses, diamonds, text, frames and
embedded PNG/JPEG/GIF/WebP images. External images, live web embeds, navigation
links and host-specific custom data do not travel in saved drawings. The SDK
performs its own element restoration after this validation. This is a visual
sketch format, not CAD topology or an inspect/selector reference format.

Desktop keeps scenes and tab metadata only in renderer memory, separate from
SQLite's `explorer_tabs`. Tab/project switches retain them; tab close, project
removal, window reload and app exit discard them. Saving a copy is explicit
and does not bind a drawing to that file or enable autosave. Loading a copy
creates another temporary drawing. Prompt attachments are copies and follow
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
draws real ink, checks PNG decoding, saves/loads through the agent bridge, and
reloads the app profile while blocking external requests.
