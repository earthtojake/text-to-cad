# PDF integration

The registry declares the PDF tools and separately composes its Apache-2.0
OpenAI PDF skill. Main resolves the tab in the session's project/root and relays
only to the mounted viewer. `renderer/state/live-documents.ts` checks the same
scope and calls the host-bound shared `LivePdfDocument` capability.

The UI uses Mozilla's Apache-2.0 `pdfjs-dist`, including its actual worker and
text layer. Both imports use the upstream legacy build, whose compatibility
polyfills support the Chromium version shipped by Electron (the modern PDF.js
build currently assumes newer Map APIs). Page text, current page, selection and PNG captures use the exact
same loaded PDF as the visible page. Bytes come from the host's scoped file
source, never a path or URL interpreted by shared UI. Page reads are limited to
50 pages and one million characters; render surfaces are capped at 4096 pixels
on their longest side. Unmounted capabilities reject late results. PDF scripts,
forms, annotations, OCR and arbitrary remote URL loading are not exposed.

## Upstream decision

Evaluated the official [MCP Apps PDF server](https://github.com/modelcontextprotocol/ext-apps/tree/main/examples/pdf-server)
(compatible Apache-2.0/MIT code). It supplies its own MCP App viewer with its
own view identity, persistence and command queue; its server does not address
Hardcore's existing FileTab. Embedding that separately would produce two live
PDFs. We therefore reuse its underlying established Mozilla PDF.js engine and
bind it directly to the host's document capability, with a small domain MCP
adapter. No claim is made that the upstream PDF skill and server are a matched
pair. The [OpenAI PDF skill](../../../../skills/pdf/UPSTREAM.md) is reused
independently under its preserved Apache-2.0 license. Anthropic's PDF skill was
also considered but its per-skill license is not permissive for redistribution.

PDF capture returns a tool image. The viewer's Add to prompt button uses the
same page capture plus selected text and a file reference; it freezes the page
before asynchronous rendering and relies on PromptContext's destination guard.

Desktop bundles PDF.js CMaps, standard fonts, image codecs and ICC profiles through `scripts/pdf-assets.mjs`, with their licenses. Its GPL Liberation Sans files are replaced by unmodified OFL 2.1.5 fonts from the pinned font package. The shared renderer receives their base URL from `ViewerHost.pdf.assetBaseUrl`; HTTP hosts fetch locally and Electron file URLs use PDF.js’s main-thread binary loader. The CSP permits WebAssembly compilation for the bundled codecs, without enabling JavaScript eval.
