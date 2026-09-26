import type { RendererPlugin } from "../renderer";
import { performGcodeCommand } from "./live";
import manifest from "./manifest.mjs";
import { createGcodeRenderer } from "./viewer";

/** The G-code plugin: a toolpath viewer per tab, and its commands answered from that viewer. */
const gcode: RendererPlugin = {
  manifest,
  renderers: (tab) => [createGcodeRenderer(tab)],
  perform: performGcodeCommand,
};
export default gcode;
