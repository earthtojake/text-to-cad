import { defineFileRenderer } from "@hardcore/ui/file-viewer";

export const imageRenderer = defineFileRenderer<{ url: string; mime?: string }>({
  id: "image",
  priority: 100,
  matches: (file) => file.mediaType === "image" || file.mime?.startsWith("image/") === true,
  async prepare({ file, source, signal }) {
    if (!source.readAsset) throw new Error(`This file source cannot read binary assets: ${file.path}`);
    const asset = await source.readAsset(file.path, { signal });
    return {
      data: { url: asset.url, mime: asset.mime },
      dispose: asset.release,
    };
  },
  load: () => import("./ImageRenderer"),
});

export { formatBytes } from "./ImageRenderer";
export type { ImageRendererData } from "./ImageRenderer";
