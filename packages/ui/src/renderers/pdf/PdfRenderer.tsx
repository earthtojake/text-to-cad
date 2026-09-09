import { useEffect } from "react";

import type { FileRendererProps } from "../../file-viewer/types.js";

/**
 * A shared PDF view, in Chromium's own viewer.
 *
 * An `<iframe>` at a `data:` URL, not a `<webview>` and not pdf.js: Electron
 * ships Chromium's PDF plugin, it renders, scrolls, searches and prints the
 * document correctly, and the alternative is half a megabyte of pdf.js doing
 * the same job worse. The frame is sandboxed with nothing granted — a PDF is a
 * document to look at, and one that can run script is a document that can
 * reach the app.
 */
export interface PdfRendererData { url: string; mime?: string }

export default function PdfRenderer({ data, file, onReady }: FileRendererProps<PdfRendererData>) {
  useEffect(() => onReady(true), [onReady]);
  return (
    <iframe
      className="size-full border-0 bg-muted/30"
      sandbox=""
      src={data.url}
      title={file.name}
    />
  );
}
