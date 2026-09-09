import { defineFileRenderer } from "../../file-viewer/registry.js";

export const pdfRenderer = defineFileRenderer<{ url: string; mime?: string }>({
  id: "pdf",
  priority: 100,
  matches: (file) =>
    file.mediaType === "pdf" || file.mime?.toLowerCase().split(";", 1)[0] === "application/pdf",
  async prepare({ file, source, signal }) {
    if (!source.readAsset) throw new Error(`This file source cannot read binary assets: ${file.path}`);
    const asset = await source.readAsset(file.path, { signal });
    return {
      data: { url: asset.url, mime: asset.mime },
      dispose: asset.release,
    };
  },
  load: () => import("./PdfRenderer.js"),
});

export type { PdfRendererData } from "./PdfRenderer.js";
