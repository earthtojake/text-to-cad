import { tool, z, tabId } from "../../main/integrations/definition.mjs";
import manifest from "./manifest.mjs";
export default { id: manifest.id, description: manifest.description, skills: [...manifest.skills], rendererCommands: manifest.commands, tools: [
  tool("gcode_state", "Read the open G-code toolpath: layer count, shown layer, extents (mm), move counts and extruded length.", { tabId }),
  tool("set_gcode_layer", "Show the toolpath up to and including a layer (1-based) of the open G-code.", { tabId, layer: z.number().int().positive() }),
  tool("capture_gcode", "Render the open G-code toolpath, as shown, into an image tool result.", { tabId }, "image"),
] };
