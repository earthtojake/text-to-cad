import { beforeEach, expect, test, vi } from 'vitest';
import { desktopLiveDocuments, performPdfCommand, releaseDocumentTab } from '@renderer/state/live-documents';
import { MAX_IMAGE_BYTES } from '@shared/image-cap';

const shrink = vi.hoisted(() => vi.fn());
vi.mock('@renderer/lib/shrink-image', () => ({ shrinkImage: shrink }));

const scope = { projectId: 'project', root: null };
const png = (size: number) => new Blob([new Uint8Array(size)], { type: 'image/png' });
function bindPage(blob: Blob) {
  const host = desktopLiveDocuments('pdf-cap', scope);
  return host.pdf!.bind({ sourceId: 'root', path: 'a.pdf', state: () => ({ sourceId: 'root', path: 'a.pdf', page: 2, pageCount: 5, selection: '' }),
    read: async () => [], setPage: () => { throw new Error('unused'); }, capture: async () => blob });
}
beforeEach(() => { shrink.mockReset(); });

test('a pdf-capture over the model image limit is scaled down like every other capture', async () => {
  const release = bindPage(png(MAX_IMAGE_BYTES + 512 * 1024));
  shrink.mockResolvedValueOnce(png(1024));
  const result = await performPdfCommand('pdf-capture', { tabId: 'pdf-cap', page: 4 }, scope);
  expect(result).toMatchObject({ scaled: true, mimeType: 'image/png', page: 4, visiblePage: 2, pageCount: 5 });
  expect(shrink).toHaveBeenCalledOnce();
  release(); releaseDocumentTab('pdf-cap');
});

test('a pdf-capture that cannot be scaled under the limit is refused, not attached', async () => {
  const release = bindPage(png(MAX_IMAGE_BYTES + 512 * 1024));
  shrink.mockResolvedValue(null);
  await expect(performPdfCommand('pdf-capture', { tabId: 'pdf-cap' }, scope)).rejects.toThrow(/could not be scaled/);
  release(); releaseDocumentTab('pdf-cap');
});
