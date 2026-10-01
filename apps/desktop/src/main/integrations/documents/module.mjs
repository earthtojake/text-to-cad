import { tool, z, tabId } from "../definition.mjs";

/** The longest buffer `edit_document` takes and `read_document` returns, in UTF-16 code units. The bridge sizes its body cap from it. */
export const MAX_DOCUMENT_CHARS = 2 * 1024 * 1024;

export default { rendererCommands: {"read_document": "document-read", "edit_document": "document-edit", "save_document": "document-save"}, id: "documents", description: "Live text documents, including unsaved editor buffers.", skills: ["skills/documents"], tools: [
  tool("read_document", "Read the open text document and live revision, including unsaved edits.", { tabId }),
  tool("edit_document", "Replace a live editor buffer only if its revision still matches. Does not save to disk.", { tabId, expectedRevision: z.string().min(1), content: z.string().max(MAX_DOCUMENT_CHARS, "the document is too large to edit through the bridge") }),
  tool("save_document", "Save an open document against its live revision; refuse external disk conflicts.", { tabId, expectedRevision: z.string().min(1) }),
] };
