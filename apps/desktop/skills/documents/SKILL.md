---
name: documents
description: Read and edit the live text buffer in a Hardcore file tab, retaining user drafts and checking revisions before changes.
---

# Live documents

Find the file's tab with `list_open_tabs`, then activate/open it if necessary.
Use the `documents` MCP server's `read_document` to read the current editor
buffer, including unsaved typing. Its revision is a live buffer token, distinct
from `diskRevision`. Pass that token as `expectedRevision` to `edit_document`
with the replacement content. The replacement stays unsaved and visible for
review. `save_document` is a separate explicit write with the latest live token.

A revision conflict means the person or another operation changed the buffer.
Read again and reconcile; never retry with a guessed revision. Disk conflicts
preserve the draft and require reconciliation with the external changes. There
is no force-write tool. Read-only or truncated files cannot be edited.

File resources are scoped to the session's project and worktree. A path in a
different workspace is not the same document. A tab switch retains drafts and an inactive read snapshot (`active: false`).
Activate the intended file before editing or saving it.
Draft retention lasts for this app window, not across quitting the application.

The code editor's selection context menu sends a UTF-16 text-range reference
and the selected text through the existing prompt context port. It never
submits a prompt. Markdown source uses the same selection action.
