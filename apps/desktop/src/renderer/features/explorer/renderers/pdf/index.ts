import { defineFileRenderer } from "../../file-viewer/registry.js";

export const pdfRenderer = defineFileRenderer<{ bytes: Uint8Array<ArrayBuffer> }>({
  id: "pdf",
  priority: 100,
  matches: (file) =>
    file.mediaType === "pdf" || file.mime?.toLowerCase().split(";", 1)[0] === "application/pdf",
  async prepare({ file, source, signal }) {
    if (!source.readAsset) throw new Error(`This file source cannot read binary assets: ${file.path}`);
    const asset = await source.readAsset(file.path, { signal });
    if (!asset.bytes) { asset.release(); throw new Error("PDF rendering requires a file source supplying asset bytes."); }
    return {
      data: { bytes: asset.bytes },
      dispose: asset.release,
    };
  },
  load: () => import("./PdfRenderer.js"),
});

export type { PdfRendererData } from "./PdfRenderer.js";
