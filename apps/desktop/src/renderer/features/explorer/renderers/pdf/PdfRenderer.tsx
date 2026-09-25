import { useEffect, useRef, useState } from 'react';
import { getDocument, PDFWorker, TextLayer } from 'pdfjs-dist/legacy/build/pdf.mjs';
import type { PDFDocumentProxy } from 'pdfjs-dist/legacy/build/pdf.mjs';
import PdfWorker from 'pdfjs-dist/legacy/build/pdf.worker.min.mjs?worker';
import 'pdfjs-dist/web/pdf_viewer.css';
import { PromptContextAction, useViewerHost, type LivePdfDocument } from '@hardcore/ui/host';
import type { FileRendererProps } from '@hardcore/ui/file-viewer';

export interface PdfRendererData { bytes: Uint8Array<ArrayBuffer> }
function validPage(page: number, count: number) {
  if (!Number.isInteger(page) || page < 1 || page > count) throw new Error(`Page must be an integer between 1 and ${count}.`);
  return page;
}
async function capture(document: PDFDocumentProxy, page: number) {
  const selected = await document.getPage(validPage(page, document.numPages));
  const base = selected.getViewport({ scale: 1 });
  const viewport = selected.getViewport({ scale: Math.min(2, 4096 / Math.max(base.width, base.height)) });
  const canvas = globalThis.document.createElement('canvas');
  canvas.width = Math.ceil(viewport.width); canvas.height = Math.ceil(viewport.height);
  await selected.render({ canvas, viewport }).promise;
  return new Promise<Blob>((resolve, reject) => canvas.toBlob(blob => blob ? resolve(blob) : reject(new Error('PDF capture failed.')), 'image/png'));
}

/** The visible page, text extraction and agent captures share one PDF.js document. */
export default function PdfRenderer({ data, file, source, state, onStateChange, onReady }: FileRendererProps<PdfRendererData>) {
  const host = useViewerHost();
  const saved = state && typeof state === 'object' && !Array.isArray(state) ? state.page : 1;
  const [page, updatePage] = useState(typeof saved === 'number' && Number.isInteger(saved) && saved > 0 ? saved : 1);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selection, setSelection] = useState('');
  const [feedback, setFeedback] = useState('');
  // The live binding reads these outside render; every writer of `page` and `selection`
  // writes its ref first (`setPage`, the text layer's mouseup), so render never has to.
  const pageRef = useRef(page);
  const selectionRef = useRef(selection);
  const canvas = useRef<HTMLCanvasElement>(null);
  const layer = useRef<HTMLDivElement>(null);
  const liveRef = useRef<LivePdfDocument | null>(null);
  const changeRef = useRef(onStateChange);
  useEffect(() => { changeRef.current = onStateChange; }, [onStateChange]);
  const setPage = (value: number) => { pageRef.current = value; selectionRef.current = ''; setSelection(''); updatePage(value); changeRef.current({ page: value }); };
  const assetBaseUrl = host.pdf?.assetBaseUrl;
  useEffect(() => {
    let active = true;
    const worker = new PdfWorker();
    const pdfWorker = PDFWorker.create({ port: worker });
    const assets = assetBaseUrl ? {
      cMapUrl: new URL("cmaps/", assetBaseUrl).href,
      standardFontDataUrl: new URL("standard_fonts/", assetBaseUrl).href,
      wasmUrl: new URL("wasm/", assetBaseUrl).href,
      iccUrl: new URL("iccs/", assetBaseUrl).href,
    } : {};
    const loading = getDocument({ data: data.bytes.slice(), worker: pdfWorker, useSystemFonts: true, ...assets });
    void loading.promise.then(document => {
      if (!active) return;
      setPdf(document);
      if (pageRef.current > document.numPages) setPage(document.numPages);
    }).catch(reason => { if (active) setError(String(reason)); });
    return () => { active = false; void loading.destroy().finally(() => { pdfWorker.destroy(); worker.terminate(); }); };
  }, [data, assetBaseUrl]);
  useEffect(() => {
    if (!pdf) return;
    let active = true;
    const check = () => { if (!active) throw new Error('PDF resource is stale; open the file again.'); };
    const target: LivePdfDocument = {
      sourceId: source.id, path: file.path,
      state() { check(); return { sourceId: source.id, path: file.path, revision: file.revision ?? pdf.fingerprints[0] ?? undefined, page: pageRef.current, pageCount: pdf.numPages, selection: selectionRef.current }; },
      async read(startPage = pageRef.current, endPage = startPage) {
        check(); validPage(startPage, pdf.numPages); validPage(endPage, pdf.numPages);
        if (endPage < startPage || endPage - startPage >= 50) throw new Error('Read between 1 and 50 pages in ascending order.');
        const result = []; let total = 0;
        for (let current = startPage; current <= endPage; current++) {
          const page = await pdf.getPage(current); check();
          const text = await page.getTextContent(); check();
          const content = text.items.map(item => 'str' in item ? item.str + (item.hasEOL ? '\n' : ' ') : '').join('');
          total += content.length;
          if (total > 1_000_000) throw new Error('PDF text exceeds one million characters; read a smaller page range.');
          result.push({ page: current, text: content });
        }
        return result;
      },
      setPage(value) { check(); setPage(validPage(value, pdf.numPages)); return target.state(); },
      async capture(value = pageRef.current) { check(); const blob = await capture(pdf, value); check(); return blob; },
    };
    liveRef.current = target;
    const unbind = host.pdf?.bind(target);
    return () => { unbind?.(); active = false; liveRef.current = null; };
  }, [pdf, host.pdf, file.path, file.revision, source.id]);
  useEffect(() => {
    if (!pdf || !canvas.current || !layer.current) return;
    let cancelled = false;
    let render: ReturnType<Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']> | undefined;
    let textLayer: TextLayer | undefined;
    onReady(false); setError(null);
    void (async () => {
      const selected = await pdf.getPage(validPage(page, pdf.numPages));
      if (cancelled || !canvas.current || !layer.current) return;
      const base = selected.getViewport({ scale: 1 });
      const viewport = selected.getViewport({ scale: Math.min(1.5, 4096 / Math.max(base.width, base.height)) });
      canvas.current.width = Math.ceil(viewport.width); canvas.current.height = Math.ceil(viewport.height);
      layer.current.replaceChildren();
      layer.current.style.setProperty('--scale-factor', String(viewport.scale));
      render = selected.render({ canvas: canvas.current, viewport });
      textLayer = new TextLayer({ textContentSource: selected.streamTextContent(), container: layer.current, viewport });
      await Promise.all([render.promise, textLayer.render()]);
      if (!cancelled) onReady(true);
    })().catch(reason => { if (!cancelled) setError(String(reason)); });
    return () => { cancelled = true; render?.cancel(); textLayer?.cancel(); };
  }, [pdf, page, onReady]);
  return <div className="flex h-full flex-col bg-muted/30" aria-label={`PDF ${file.name}`}>
    <div className="flex shrink-0 items-center gap-2 border-b px-3 py-2">
      <button disabled={!pdf || page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page">‹</button>
      <label>Page <input aria-label="PDF page" type="number" min={1} max={pdf?.numPages ?? 1} value={page} className="w-14 rounded border bg-background px-1"
        onChange={event => { const value = Number(event.target.value); if (pdf && Number.isInteger(value) && value >= 1 && value <= pdf.numPages) setPage(value); }} /></label>
      <span>of {pdf?.numPages ?? '…'}</span>
      <button disabled={!pdf || page >= pdf.numPages} onClick={() => setPage(page + 1)} aria-label="Next page">›</button>
      <PromptContextAction size="sm" variant="ghost" disabled={!pdf} createContext={() => {
        const target = liveRef.current; if (!target) throw new Error('PDF is still loading.');
        const current = target.state();
        return { schemaVersion: 1, operationId: crypto.randomUUID(), parts: [
          { id: 'pdf', kind: 'reference', reference: { resource: { kind: 'workspace-file', workspaceId: source.id, path: file.path, revision: current.revision }, target: { kind: 'whole-resource' }, label: `${file.name}, page ${current.page}` } },
          ...(current.selection ? [{ id: 'selection', kind: 'text' as const, text: `Page ${current.page} selection:\n${current.selection}` }] : []),
          { id: 'page', kind: 'attachment', name: `${file.name}-page-${current.page}.png`, mimeType: 'image/png', content: target.capture(current.page), about: ['pdf'] },
        ] };
      }} onResult={result => setFeedback(
        // A delivery that worked says nothing (no success messages); one that did not says why.
        result.status === 'added' || result.status === 'copied' || result.status === 'cancelled' ? '' : ('message' in result ? result.message : undefined) ?? result.status)} />
      <span role="status" className="text-muted-foreground">{feedback}</span>
    </div>
    {error ? <div role="alert" className="p-3 text-destructive">{error}</div> : null}
    <div className="min-h-0 flex-1 overflow-auto p-3" onMouseUp={() => {
      const selected = globalThis.getSelection();
      const value = selected && layer.current?.contains(selected.anchorNode) && layer.current.contains(selected.focusNode) ? selected.toString() : '';
      selectionRef.current = value; setSelection(value);
    }}>
      <div className="relative mx-auto w-fit bg-white shadow-sm"><canvas ref={canvas} /><div ref={layer} className="textLayer" /></div>
    </div>
  </div>;
}
