import { tool, z, tabId } from "../definition.mjs";
export default { rendererCommands: {"read_document": "document-read", "edit_document": "document-edit", "save_document": "document-save"}, id: "documents", description: "Live text documents, including unsaved editor buffers.", skills: ["skills/documents"], tools: [
  tool("read_document", "Read the open text document and live revision, including unsaved edits.", { tabId }),
  tool("edit_document", "Replace a live editor buffer only if its revision still matches. Does not save to disk.", { tabId, expectedRevision: z.string().min(1), content: z.string().max(2 * 1024 * 1024) }),
  tool("save_document", "Save an open document against its live revision; refuse external disk conflicts.", { tabId, expectedRevision: z.string().min(1) }),
] };
