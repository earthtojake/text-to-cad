import { defineFileRenderer } from "@hardcore/ui/file-viewer";

export const unsupportedRenderer = defineFileRenderer<null>({
  id: "unsupported",
  priority: -100,
  fallback: true,
  matches: () => false,
  prepare: async () => ({ data: null }),
  load: () => import("./UnsupportedRenderer"),
});

export type { UnsupportedRendererData } from "./UnsupportedRenderer";
