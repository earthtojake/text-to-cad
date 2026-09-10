import React from 'react';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ReconstructionExport from '../../../../../dist/renderers/cad/components/workbench/ReconstructionExport.js';
const mocks = vi.hoisted(() => ({ encode: vi.fn(), download: vi.fn() }));
vi.mock('../../../../../dist/renderers/cad/workbench/reconstructionExport.js', () => ({ exportReconstruction: mocks.encode, downloadExport: mocks.download, videoMimeType: () => 'video/webm;codecs=vp8' }));
Object.assign(globalThis, { React });
afterEach(() => { cleanup(); vi.resetAllMocks(); });
const props = { data: { steps: [{}, {}] }, label: 'Part', viewRef: { current: null }, onStart: vi.fn() };
async function choose(label: string) {
  fireEvent.keyDown(screen.getByRole('button', { name: 'Export', exact: true }), { key: 'Enter' });
  fireEvent.click(await screen.findByRole('menuitem', { name: label, exact: true }));
}
it('downloads the selected format and restores the export control', async () => {
  const result = { blob: new Blob(['gif']), filename: 'part.gif' }; mocks.encode.mockResolvedValue(result);
  render(<ReconstructionExport {...props} />); await choose('Animated GIF');
  await waitFor(() => expect(mocks.download).toHaveBeenCalledWith(result));
  expect(mocks.encode.mock.calls[0][0].format).toBe('gif');
  expect(screen.getByRole('button', { name: 'Export', exact: true })).toBeTruthy();
});
it('cancel aborts encoding and never downloads a late result', async () => {
  let finish: any; mocks.encode.mockImplementation(() => new Promise(resolve => { finish = resolve; }));
  render(<ReconstructionExport {...props} />); await choose('Video');
  const signal = mocks.encode.mock.calls[0][0].signal;
  fireEvent.click(screen.getByRole('button', { name: 'Cancel export' }));
  expect(signal.aborted).toBe(true); finish({ blob: new Blob(['late']), filename: 'late.webm' });
  await waitFor(() => expect(screen.getByRole('button', { name: 'Export', exact: true })).toBeTruthy());
  expect(mocks.download).not.toHaveBeenCalled();
});
it('closing the preview aborts the active export', async () => {
  mocks.encode.mockImplementation(() => new Promise(() => {}));
  const { unmount } = render(<ReconstructionExport {...props} />); await choose('Animated GIF');
  const signal = mocks.encode.mock.calls[0][0].signal; unmount(); expect(signal.aborted).toBe(true);
});
it('an encoder error stays visible and allows retry', async () => {
  mocks.encode.mockRejectedValue(new Error('Encoder unavailable'));
  render(<ReconstructionExport {...props} />); await choose('Video');
  expect((await screen.findByRole('alert')).textContent).toContain('Encoder unavailable');
  expect(screen.getByRole('button', { name: 'Export', exact: true })).toBeTruthy();
});
