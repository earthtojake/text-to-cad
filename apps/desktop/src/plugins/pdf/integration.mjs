import { tool, z, tabId } from "../../main/integrations/definition.mjs";
import manifest from "./manifest.mjs";
export default { id: manifest.id, description: manifest.description, skills: [...manifest.skills], rendererCommands: manifest.commands, tools: [
  tool("pdf_state", "Read the PDF viewer's document identity, page, page count and text selection.", { tabId }),
  tool("read_pdf", "Read text from a bounded page range of the open PDF.", { tabId, startPage: z.number().int().positive().optional(), endPage: z.number().int().positive().optional() }),
  tool("set_pdf_page", "Display a page of the open PDF.", { tabId, page: z.number().int().positive() }),
  tool("capture_pdf", "Render a PDF page into an image tool result with its document identity.", { tabId, page: z.number().int().positive().optional() }, "image"),
] };
