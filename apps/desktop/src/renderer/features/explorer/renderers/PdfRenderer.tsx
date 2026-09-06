/**
 * A PDF, in Chromium's own viewer.
 *
 * An `<iframe>` at a `data:` URL, not a `<webview>` and not pdf.js: Electron
 * ships Chromium's PDF plugin, it renders, scrolls, searches and prints the
 * document correctly, and the alternative is half a megabyte of pdf.js doing
 * the same job worse. The frame is sandboxed with nothing granted — a PDF is a
 * document to look at, and one that can run script is a document that can
 * reach the app.
 */
export function PdfRenderer({ dataUrl, name }: { dataUrl: string; name: string }) {
  return (
    <iframe
      className="size-full border-0 bg-muted/30"
      sandbox=""
      src={dataUrl}
      title={name}
    />
  );
}
