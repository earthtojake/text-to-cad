import { tool, z, tabId } from "../definition.mjs";
export default { rendererCommands: {"pdf_state": "pdf-state", "read_pdf": "pdf-read", "set_pdf_page": "pdf-page", "capture_pdf": "pdf-capture"}, id: "pdf", description: "Page-aware PDF viewing and prompt capture.", skills: ["skills/pdf"], tools: [
  tool("pdf_state", "Read the PDF viewer's document identity, page, page count and text selection.", { tabId }),
  tool("read_pdf", "Read text from a bounded page range of the open PDF.", { tabId, startPage: z.number().int().positive().optional(), endPage: z.number().int().positive().optional() }),
  tool("set_pdf_page", "Display a page of the open PDF.", { tabId, page: z.number().int().positive() }),
  tool("capture_pdf", "Render a PDF page into an image tool result with its document identity.", { tabId, page: z.number().int().positive().optional() }, "image"),
] };
