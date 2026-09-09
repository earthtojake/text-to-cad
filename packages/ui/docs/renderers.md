# File renderers

The non-CAD renderers are a pure ownership refactor of Hardcore's desktop file tab. They preserve the existing Markdown document and source views, Monaco configuration and save behavior, image fit and actual-size controls, Chromium PDF presentation, and unsupported-file fallback.

Hosts register `markdownRenderer`, `codeRenderer`, `imageRenderer`, `pdfRenderer`, and `unsupportedRenderer` from their corresponding `@hardcore/ui/renderers/*` entry points. Text preparation uses `FileSource.readText`; image and PDF preparation use `FileSource.readAsset`. Every acquired asset URL carries a release lease, and FileViewer releases it when the request is cancelled, the file changes, or the view unmounts.

Monaco setup and editor constants live at `@hardcore/ui/renderers/code/editor`. Model URIs include source, document, and mounted-view identity so two FileViewer instances cannot share draft or cursor state, while a mounted editor keeps a stable model through ordinary renders. Markdown loads that editor only when its source view is opened.
