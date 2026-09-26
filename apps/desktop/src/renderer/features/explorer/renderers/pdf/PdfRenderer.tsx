import { useCallback, useEffect, useRef, useState } from 'react';
import { getDocument, PDFWorker, TextLayer } from 'pdfjs-dist/legacy/build/pdf.mjs';
import type { PDFDocumentProxy, PDFPageProxy } from 'pdfjs-dist/legacy/build/pdf.mjs';
import { zoomLimits } from '@hardcore/core/lib/drawing2d/index.js';
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

// Pan and zoom, as the DXF viewer has them: wheel or pinch zooms about the pointer, a drag pans,
// a double-click fits the page. Only the part of the page in view is drawn, into a canvas the size
// of the pane, so a deep zoom into a drawing sheet stays sharp. A gesture moves the last drawing by
// a CSS transform at once, and the page is drawn again sharp when the view settles.
type View = { scale: number; x: number; y: number };
/** Wheel notches to zoom factor (~100 px of delta a notch); a pinch is a ctrl-wheel with smaller deltas. */
const WHEEL_ZOOM_SPEED = 0.0015;
const PINCH_WHEEL_ZOOM_SPEED = 0.01;
const FIT_MARGIN_PX = 12;
const SETTLE_MS = 120;
function wheelZoomFactor(event: WheelEvent) {
  const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? 100 : 1;
  return Math.exp(-event.deltaY * unit * (event.ctrlKey ? PINCH_WHEEL_ZOOM_SPEED : WHEEL_ZOOM_SPEED));
}
function fitView(page: { width: number; height: number }, pane: { width: number; height: number }): View {
  const scale = Math.max(1e-3, Math.min((pane.width - 2 * FIT_MARGIN_PX) / page.width, (pane.height - 2 * FIT_MARGIN_PX) / page.height));
  return { scale, x: (pane.width - page.width * scale) / 2, y: (pane.height - page.height * scale) / 2 };
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
  const pane = useRef<HTMLDivElement>(null);
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
  // ---- the view --------------------------------------------------------------------------
  const pdfPage = useRef<PDFPageProxy | null>(null);
  const size = useRef({ width: 0, height: 0 });
  const view = useRef<View>({ scale: 1, x: 0, y: 0 });
  /** The view the canvas and text layer were last drawn for; a moving view is shown relative to it. */
  const drawn = useRef<View | null>(null);
  const fitted = useRef(true);
  const settle = useRef<number | undefined>(undefined);
  const drawing = useRef<{ cancel(): void } | null>(null);
  const draw = useCallback(() => {
    const target = canvas.current; const text = layer.current; const host = pane.current; const current = pdfPage.current;
    if (!target || !text || !host || !current) return;
    drawing.current?.cancel();
    const at = { ...view.current };
    const ratio = globalThis.devicePixelRatio || 1;
    const width = host.clientWidth; const height = host.clientHeight;
    target.width = Math.max(1, Math.round(width * ratio)); target.height = Math.max(1, Math.round(height * ratio));
    target.style.width = `${width}px`; target.style.height = `${height}px`; target.style.transform = '';
    const context = target.getContext('2d');
    if (!context) return;
    const pageViewport = current.getViewport({ scale: at.scale });
    context.clearRect(0, 0, target.width, target.height);
    context.fillStyle = '#fff';
    context.fillRect(at.x * ratio, at.y * ratio, pageViewport.width * ratio, pageViewport.height * ratio);
    const render = current.render({ canvas: target, background: 'rgba(0,0,0,0)',
      viewport: current.getViewport({ scale: at.scale * ratio, offsetX: at.x * ratio, offsetY: at.y * ratio }) });
    // The text layer is rebuilt when the scale changes; a pan only moves it.
    const rebuild = drawn.current?.scale !== at.scale;
    let textLayer: TextLayer | undefined;
    if (rebuild) {
      text.replaceChildren();
      text.style.setProperty('--scale-factor', String(at.scale));
      textLayer = new TextLayer({ textContentSource: current.streamTextContent(), container: text, viewport: pageViewport });
    }
    text.style.transform = `translate(${at.x}px, ${at.y}px)`;
    drawn.current = at;
    drawing.current = { cancel: () => { render.cancel(); textLayer?.cancel(); } };
    void Promise.all([render.promise, textLayer?.render()]).then(() => onReady(true)).catch(reason => {
      // A drawing cut short by the next one is not an error.
      const name = (reason as { name?: string })?.name;
      if (name !== 'RenderingCancelledException' && name !== 'AbortException') setError(String(reason));
    });
  }, [onReady]);
  /** A new view: shown at once by moving the last drawing, drawn again sharp when it settles. */
  const moveTo = useCallback((next: View) => {
    view.current = next;
    const before = drawn.current;
    if (before && canvas.current && layer.current) {
      const k = next.scale / before.scale;
      const move = `translate(${next.x - before.x * k}px, ${next.y - before.y * k}px) scale(${k})`;
      canvas.current.style.transform = move;
      layer.current.style.transform = `translate(${next.x}px, ${next.y}px) scale(${k})`;
    }
    window.clearTimeout(settle.current);
    settle.current = window.setTimeout(draw, SETTLE_MS);
  }, [draw]);
  const fit = useCallback(() => {
    const host = pane.current;
    if (!host || !size.current.width) return;
    fitted.current = true;
    view.current = fitView(size.current, { width: host.clientWidth, height: host.clientHeight });
    window.clearTimeout(settle.current);
    draw();
  }, [draw]);
  useEffect(() => {
    if (!pdf) return;
    let cancelled = false;
    onReady(false);
    void pdf.getPage(validPage(page, pdf.numPages)).then(selected => {
      if (cancelled) return;
      setError(null);
      pdfPage.current = selected;
      const base = selected.getViewport({ scale: 1 });
      size.current = { width: base.width, height: base.height };
      drawn.current = null;
      fit();
    }).catch(reason => { if (!cancelled) setError(String(reason)); });
    return () => { cancelled = true; drawing.current?.cancel(); window.clearTimeout(settle.current); };
  }, [pdf, page, onReady, fit]);
  // A resized pane keeps a fitted page fitted, and draws any other view again at the new size.
  useEffect(() => {
    const host = pane.current;
    if (!host) return undefined;
    const observer = new ResizeObserver(() => { if (fitted.current) fit(); else draw(); });
    observer.observe(host);
    return () => observer.disconnect();
  }, [fit, draw]);
  useEffect(() => {
    const host = pane.current;
    if (!host) return undefined;
    const local = (event: { clientX: number; clientY: number }) => {
      const box = host.getBoundingClientRect();
      return { x: event.clientX - box.left, y: event.clientY - box.top };
    };
    const onWheel = (event: WheelEvent) => {
      // The pane must not scroll under a page being zoomed.
      event.preventDefault();
      if (!size.current.width) return;
      const fitScale = fitView(size.current, { width: host.clientWidth, height: host.clientHeight }).scale;
      const { minScale, maxScale } = zoomLimits(fitScale);
      const at = view.current; const point = local(event);
      const scale = Math.min(maxScale, Math.max(minScale, at.scale * wheelZoomFactor(event)));
      const k = scale / at.scale;
      fitted.current = false;
      moveTo({ scale, x: point.x - (point.x - at.x) * k, y: point.y - (point.y - at.y) * k });
    };
    // A drag pans, except one that starts on the page's text: that one selects it.
    let drag: { id: number; x: number; y: number } | null = null;
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0 || (event.target as Element | null)?.closest?.('.textLayer span')) return;
      drag = { id: event.pointerId, x: event.clientX, y: event.clientY };
      host.setPointerCapture(event.pointerId);
    };
    const onPointerMove = (event: PointerEvent) => {
      if (!drag || drag.id !== event.pointerId) return;
      const at = view.current;
      fitted.current = false;
      moveTo({ ...at, x: at.x + event.clientX - drag.x, y: at.y + event.clientY - drag.y });
      drag = { ...drag, x: event.clientX, y: event.clientY };
    };
    const onPointerUp = (event: PointerEvent) => { if (drag?.id === event.pointerId) drag = null; };
    const onDoubleClick = (event: MouseEvent) => {
      if ((event.target as Element | null)?.closest?.('.textLayer span')) return;
      event.preventDefault(); fit();
    };
    host.addEventListener('wheel', onWheel, { passive: false });
    host.addEventListener('pointerdown', onPointerDown);
    host.addEventListener('pointermove', onPointerMove);
    host.addEventListener('pointerup', onPointerUp);
    host.addEventListener('pointercancel', onPointerUp);
    host.addEventListener('dblclick', onDoubleClick);
    return () => {
      host.removeEventListener('wheel', onWheel);
      host.removeEventListener('pointerdown', onPointerDown);
      host.removeEventListener('pointermove', onPointerMove);
      host.removeEventListener('pointerup', onPointerUp);
      host.removeEventListener('pointercancel', onPointerUp);
      host.removeEventListener('dblclick', onDoubleClick);
    };
  }, [moveTo, fit]);
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
    <div ref={pane} data-pdf-view="" className="relative min-h-0 flex-1 cursor-grab touch-none overflow-hidden active:cursor-grabbing" onMouseUp={() => {
      const selected = globalThis.getSelection();
      const value = selected && layer.current?.contains(selected.anchorNode) && layer.current.contains(selected.focusNode) ? selected.toString() : '';
      selectionRef.current = value; setSelection(value);
    }}>
      <canvas ref={canvas} className="absolute left-0 top-0 origin-top-left" />
      <div ref={layer} className="textLayer absolute left-0 top-0 origin-top-left cursor-text" />
    </div>
  </div>;
}
