import { defineFileRenderer } from "../../file-viewer/registry.js";

export const imageRenderer = defineFileRenderer<{ url: string; mime?: string }>({
  id: "image",
  priority: 100,
  // A DXF's registered MIME is image/vnd.dxf, but it is a CAD document: a file the
  // host has already typed as "cad" is never a picture, whatever its MIME says.
  matches: (file) => file.mediaType === "image" || (file.mediaType !== "cad" && file.mime?.startsWith("image/") === true),
  async prepare({ file, source, signal }) {
    if (!source.readAsset) throw new Error(`This file source cannot read binary assets: ${file.path}`);
    const asset = await source.readAsset(file.path, { signal });
    return {
      data: { url: asset.url, mime: asset.mime },
      dispose: asset.release,
    };
  },
  load: () => import("./ImageRenderer.js"),
});

export { formatBytes } from "./ImageRenderer.js";
export type { ImageRendererData } from "./ImageRenderer.js";
