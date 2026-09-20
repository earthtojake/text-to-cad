# File renderers

The viewer renderers, `cad` (STEP, DXF), `glb`, `mesh` (STL, 3MF) and `robot` (URDF, SRDF, SDF), and
the kit and shell they are built on are in [CAD renderer](cad-renderer.md).

The non-CAD renderers share Hardcore's desktop file-tab implementation. They preserve the existing Markdown document and source views, Monaco configuration and save behavior, image fit and actual-size controls, PDF presentation, and unsupported-file fallback.

Hosts register `markdownRenderer`, `codeRenderer`, `imageRenderer`, `pdfRenderer`, and `unsupportedRenderer` from their corresponding `@hardcore/ui/renderers/*` entry points. Text preparation uses `FileSource.readText`; image and PDF preparation use `FileSource.readAsset`. Every acquired asset URL carries a release lease, and FileViewer releases it when the request is cancelled, the file changes, or the view unmounts.

Monaco setup and editor constants live at `@hardcore/ui/renderers/code/editor`. Model URIs include source, document, and mounted-view identity so two FileViewer instances cannot share draft or cursor state, while a mounted editor keeps a stable model through ordinary renders. Markdown loads that editor only when its source view is opened.


PDF uses Mozilla PDF.js with a per-document worker, real text layer, page
navigation and a prompt capture action. Rendering, extraction and captures
share the same loaded document. Hosts provide asset bytes and optional live
capability binding. Reads accept at most 50 pages and one million characters;
page canvases are bounded to 4096 pixels on their longest side. Extraction
is not OCR. Page and selection identity is captured before asynchronous prompt
delivery. Page state persists through the existing renderer state slice.

Code and Markdown source selections offer “Use selection in prompt” in Monaco's
context menu. This sends a zero-based UTF-16 text range and the selected bytes
through PromptContext. External live-buffer replacements update the Markdown
visual editor without echoing another edit or discarding unaffected source
formatting. Dirty text can survive view unmounts through the host draft store.
