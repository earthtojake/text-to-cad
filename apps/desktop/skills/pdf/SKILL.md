---
name: "pdf"
description: "Use when tasks involve reading, creating, or reviewing PDF files where rendering and layout matter; prefer visual checks by rendering pages (Poppler) and use Python tools such as `reportlab`, `pdfplumber`, and `pypdf` for generation and extraction."
---


# PDF Skill

App tabs belong to this session only. Even another session in the same directory
has separate tabs. Opening or showing a tab updates this session's explorer;
background tool calls never switch the user's selected session. Use IDs returned
by this session's tools.


## When to use
- Read or review PDF content where layout and visuals matter.
- Create PDFs programmatically with reliable formatting.
- Validate final rendering before delivery.

## Workflow
1. Prefer visual review: render PDF pages to PNGs and inspect them.
   - Use `pdftoppm` if available.
   - If unavailable, install Poppler or ask the user to review the output locally.
2. Use `reportlab` to generate PDFs when creating new documents.
3. Use `pdfplumber` (or `pypdf`) for text extraction and quick checks; do not rely on it for layout fidelity.
4. After each meaningful update, re-render pages and verify alignment, spacing, and legibility.

## Temp and output conventions
- Use `tmp/pdfs/` for intermediate files; delete when done.
- Write final artifacts under `output/pdf/` when working in this repo.
- Keep filenames stable and descriptive.

## Dependencies (install if missing)
Prefer `uv` for dependency management.

Python packages:
```
uv pip install reportlab pdfplumber pypdf
```
If `uv` is unavailable:
```
python3 -m pip install reportlab pdfplumber pypdf
```
System tools (for rendering):
```
# macOS (Homebrew)
brew install poppler

# Ubuntu/Debian
sudo apt-get install -y poppler-utils
```

If installation isn't possible in this environment, tell the user which dependency is missing and how to install it locally.

## Environment
No required environment variables.

## Rendering command
```
pdftoppm -png $INPUT_PDF $OUTPUT_PREFIX
```

## Quality expectations
- Maintain polished visual design: consistent typography, spacing, margins, and section hierarchy.
- Avoid rendering issues: clipped text, overlapping elements, broken tables, black squares, or unreadable glyphs.
- Charts, tables, and images must be sharp, aligned, and clearly labeled.
- Use ASCII hyphens only. Avoid U+2011 (non-breaking hyphen) and other Unicode dashes.
- Citations and references must be human-readable; never leave tool tokens or placeholder strings.

## Final checks
- Do not deliver until the latest PNG inspection shows zero visual or formatting defects.
- Confirm headers/footers, page numbering, and section transitions look polished.
- Keep intermediate files organized or remove them after final approval.

## Hardcore live PDF viewer (local adaptation)

Modified by Hardcore: when reviewing a PDF already open in the app, use the
`pdf` MCP server. Resolve its `tabId` from `list_open_tabs`; the tab's renderer
is `pdf` and its workspace must match the session. `pdf_state` returns page,
page count, selection and resource identity. `read_pdf` reads 1–50 pages from
the same loaded document (defaults to the visible page). An empty text result
can indicate a scanned page; inspect `capture_pdf` rather than inventing text.
`set_pdf_page` changes the visible page; `capture_pdf` produces a PNG of the
specified page without changing the view. These operations are read-only.

The PDF toolbar's Add to prompt action includes the page capture and selected
text through the app's existing prompt destination. It never sends the prompt.
Tools cannot edit PDF bytes, fill forms or perform OCR. Use the upstream disk
workflow above only when that is the requested task and dependencies exist.
