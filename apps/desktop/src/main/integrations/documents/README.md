# Live document integration

`read_document`, `edit_document` and `save_document` operate on a mounted text
capability, not a second disk buffer. Main checks session/project/root and the
renderer repeats this check before resolving the tab. `ViewerHost.documents`
binds shared editor capabilities and supplies app-owned draft retention.

The live revision is opaque and changes on every content update and remount.
Edits compare it synchronously, so two commands using one revision cannot both
succeed before React renders. Saves separately validate the disk revision via
FileSource's existing serialized atomic write protocol. Conflicts preserve the
draft; no force-write operation exists. Read-only/truncated content stays so.
Markdown visual editing and source editing share the same document buffer.

Draft bytes remain in the app window's map keyed by source identity and path
when a tab or project unmounts. Inactive tabs retain a read snapshot tagged
`active: false`; edits and saves require reactivation. Closing a dirty tab is
refused through `hasDirtyDocument`, and `releaseDocumentTab` clears closed clean
resources. They are never serialized into camera/view
settings and are rechecked against the fresh disk revision when reopened.
Reload is explicit discard. Quitting the app does not persist these drafts.
A disk write completing after unmount keeps the prior existing stale/committed
receipt semantics; it cannot replace another mounted document.

Monaco's selection context action sends selected text and zero-based UTF-16
coordinates through PromptContext. The delivery never sends the prompt.
