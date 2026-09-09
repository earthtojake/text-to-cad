import { defineFileRenderer } from "../../file-viewer/registry.js";

export const unsupportedRenderer = defineFileRenderer<null>({
  id: "unsupported",
  priority: -100,
  fallback: true,
  matches: () => false,
  prepare: async () => ({ data: null }),
  load: () => import("./UnsupportedRenderer.js"),
});

export type { UnsupportedRendererData } from "./UnsupportedRenderer.js";
