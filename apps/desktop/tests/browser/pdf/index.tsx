import { createRoot } from 'react-dom/client';
import { useState } from 'react';
import { FileViewer, type FileViewerState } from '@hardcore/ui/file-viewer';
import type { LivePdfDocument } from '@hardcore/ui/host';
import '@hardcore/ui/styles.css';

import { pdfRenderer } from '../../../src/plugins/pdf/viewer';
import { testViewerHost } from '../../viewer-host';

const objects = [
  '<< /Type /Catalog /Pages 2 0 R >>',
  '<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R /F2 8 0 R >> >> /Contents 6 0 R >>',
  '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Resources << /Font << /F1 5 0 R >> >> /Contents 7 0 R >>',
  '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
  ...['First PDF page', 'Second PDF page'].map(text => { const stream = `BT /F1 16 Tf 20 100 Td (${text}) Tj ET` + (text.startsWith("First") ? " BT /F2 16 Tf 20 70 Td <65E5672C> Tj ET" : ""); return `<< /Length ${stream.length} >>\nstream\n${stream}\nendstream`; }),
  '<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiMin-W3 /Encoding /UniJIS-UTF16-H /DescendantFonts [9 0 R] >>',
  '<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiMin-W3 /CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 5 >> /FontDescriptor 10 0 R >>',
  '<< /Type /FontDescriptor /FontName /HeiseiMin-W3 /Flags 6 /FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 800 /Descent -200 /CapHeight 700 /StemV 80 >>',
];
let pdf = '%PDF-1.4\n'; const offsets = [0];
objects.forEach((object, index) => { offsets.push(pdf.length); pdf += `${index + 1} 0 obj\n${object}\nendobj\n`; });
const xref = pdf.length;
pdf += `xref\n0 ${objects.length + 1}\n0000000000 65535 f \n${offsets.slice(1).map(offset => `${String(offset).padStart(10, '0')} 00000 n \n`).join('')}trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF`;
const bytes = new TextEncoder().encode(pdf);
let live: LivePdfDocument | null = null;
const deliveries: string[] = [];
const destination = { kind: 'clipboard' as const, available: true };
const host = testViewerHost({
  promptContext: { getSnapshot: () => destination, subscribe: () => () => {},
    // A host takes the attachments' content before it reports: the page capture is the delivery.
    deliver: async context => {
      await Promise.all(context.parts.map(part => part.kind === 'attachment' ? part.content : null));
      deliveries.push(context.parts.map(part => part.id).join()); return { status: 'copied', partIds: context.parts.map(part => part.id) };
    } },
  files: { id: 'pdf-root', rootName: 'PDF', stat: async path => ({ path, name: path, kind: 'file', size: bytes.length, extension: 'pdf', mediaType: 'pdf', revision: 'fixture-r1' }),
    readAsset: async () => ({ url: '', bytes, release() {} }) },
  pdf: { assetBaseUrl: new URL('/pdfjs/', window.location.href).href, bind(target) { live = target; return () => { live = null; }; } },
});
const renderers = [pdfRenderer];
function App() {
  const [state, setState] = useState<FileViewerState>({ panel: null, panelWidth: 300 });
  return <div style={{ height: 600 }}><FileViewer file="two.pdf" host={host} renderers={renderers} state={state} onStateChange={setState} /></div>;
}
const root = createRoot(document.getElementById('root')!);
Object.assign(window, { pdfHarness: { deliveries, get live() { return live; }, unmount() { root.unmount(); } } });
root.render(<App />);
