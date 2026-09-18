import { z, tool, tabId } from "../definition.mjs";
const vector = z.tuple([z.number(), z.number(), z.number()]);
const camera = z.object({ position: vector, target: vector, up: vector,
  zoom: z.number().positive().optional(), projection: z.enum(["orthographic", "perspective"]).optional(),
  focalLength: z.number().positive().optional(), orthographicHalfHeight: z.number().positive().optional(),
}).strict();
export default {
  id: "cad", description: "Inspect and control CAD documents displayed in Hardcore.", skills: ["skills/cad-viewer"],
  rendererCommands: { viewer_state: "viewer-state", select_reference: "select-reference", capture_view: "capture-view",
    clear_selection: "cad-clear-selection", set_camera: "cad-camera", reset_camera: "cad-reset-camera", set_render_mode: "cad-render-mode" },
  tools: [
    tool("viewer_state", "Read the scoped CAD viewer's current model, selection, camera and revision. No tab ID selects the active CAD tab in this workspace.", { tabId: tabId.optional() }),
    tool("select_reference", "Select a cadgen topology selector in an open CAD file. The target must be displayed; use workspace.show_tab first if necessary.", { tabId, selector: z.string().min(1) }),
    tool("clear_selection", "Clear selection in the displayed CAD viewport.", { tabId }),
    tool("set_camera", "Set the displayed CAD viewport camera. Use the vectors returned by viewer_state as the starting point.", { tabId, camera }),
    tool("reset_camera", "Fit the displayed model to its viewport.", { tabId }),
    tool("set_render_mode", "Switch the displayed CAD viewport between Inspect and Render modes.", { tabId, mode: z.enum(["inspect", "render"]) }),
    tool("capture_view", "Capture the currently displayed CAD viewport as an image, preserving its model and selection identity.", { tabId }, "image"),
  ],
};
