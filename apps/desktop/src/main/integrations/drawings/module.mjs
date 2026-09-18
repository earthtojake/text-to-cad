import { tool, z, tabId } from "../definition.mjs";
export default { rendererCommands: {"open_drawing": "open-drawing", "drawing_state": "drawing-state", "capture_drawing": "drawing-capture"}, id: "drawings", description: "Temporary sketch canvases for prompt context.", skills: ["skills/drawings"], tools: [
  tool("open_drawing", "Open an empty, light-mode scratch drawing. It is held only in memory and discarded on close or app restart.", { title: z.string().min(1).max(200).optional() }),
  tool("drawing_state", "Read the temporary drawing's element count and identity without switching tabs.", { tabId }),
  tool("capture_drawing", "Capture a temporary drawing as a PNG tool result. This does not save a drawing file or submit a prompt.", { tabId }, "image"),
] };
