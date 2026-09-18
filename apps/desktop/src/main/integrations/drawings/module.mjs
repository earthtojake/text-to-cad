import { tool, z, tabId } from "../definition.mjs";
export default { rendererCommands: {"open_drawing": "open-drawing", "rename_drawing": "drawing-rename", "drawing_state": "drawing-state", "capture_drawing": "drawing-capture"}, id: "drawings", description: "Sketch canvases for prompt context.", skills: ["skills/drawings"], tools: [
  tool("open_drawing", "Open an empty, light-mode scratch drawing. It is held only in memory and discarded on close or app restart.", { title: z.string().trim().min(1).max(200).optional() }),
  tool("drawing_state", "Read the temporary drawing's element count and identity without switching tabs.", { tabId }),
  tool("rename_drawing", "Rename a drawing tab without changing its contents or switching the active project.", { tabId, title: z.string().trim().min(1).max(200) }),
  tool("capture_drawing", "Capture a temporary drawing as a PNG tool result. This does not save a drawing file or submit a prompt.", { tabId }, "image"),
] };
