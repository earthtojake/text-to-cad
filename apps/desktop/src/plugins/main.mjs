/** Main's half of each plugin: its agent tools and the renderer commands they relay, in `plugins` order. */
import pdf from "./pdf/integration.mjs";
import gcode from "./gcode/integration.mjs";

export const pluginIntegrations = [pdf, gcode];
