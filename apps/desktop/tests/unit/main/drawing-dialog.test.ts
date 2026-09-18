import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, expect, it, vi } from 'vitest';
import { emptyDrawingDocument } from '@hardcore/core/drawing';

const mocks = vi.hoisted(() => ({ choose: vi.fn(), root: vi.fn() }));
vi.mock('electron', () => ({ BrowserWindow: { fromWebContents: () => null }, dialog: { showSaveDialog: mocks.choose } }));
vi.mock('@main/ipc/explorer', () => ({ rootOf: mocks.root }));
import { dialogsHandlers } from '@main/ipc/dialogs';
import type { IpcContext } from '@main/ipc/register';

const directories: string[] = [];
afterEach(async () => { vi.resetAllMocks(); await Promise.all(directories.splice(0).map(dir => fs.rm(dir, { recursive: true, force: true }))); });
const ctx = { sender: {} } as IpcContext;
it('exports an editable copy only to the native chooser destination', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'drawing-dialog-'));
  directories.push(dir);
  mocks.root.mockReturnValue(dir);
  const destination = path.join(dir, 'copy.excalidraw');
  mocks.choose.mockResolvedValue({ canceled: false, filePath: destination });
  const result = await dialogsHandlers.dialogs.saveDrawing({ projectId: 'project', title: '../../Sketch', scene: JSON.stringify(emptyDrawingDocument()) }, ctx);
  expect(mocks.root).toHaveBeenCalledWith('project', undefined);
  expect(mocks.choose.mock.calls[0]?.[0].defaultPath).toBe(path.join(dir, '.._.._Sketch.excalidraw'));
  expect(result).toEqual({ path: destination });
  expect(JSON.parse(await fs.readFile(destination, 'utf8')).type).toBe('excalidraw');
  expect(await fs.readdir(dir)).toEqual(['copy.excalidraw']);
});
it('cancelled export writes nothing', async () => {
  const dir = await fs.mkdtemp(path.join(os.tmpdir(), 'drawing-dialog-'));
  directories.push(dir);
  mocks.root.mockReturnValue(dir);
  mocks.choose.mockResolvedValue({ canceled: true });
  expect(await dialogsHandlers.dialogs.saveDrawing({ projectId: 'project', title: 'Sketch', scene: JSON.stringify(emptyDrawingDocument()) }, ctx)).toBeNull();
  expect(await fs.readdir(dir)).toEqual([]);
});
it('invalid scene or missing project is rejected before a native dialog opens', async () => {
  mocks.root.mockReturnValue('/project');
  await expect(dialogsHandlers.dialogs.saveDrawing({ projectId: 'project', title: 'Sketch', scene: '{}' }, ctx)).rejects.toThrow();
  expect(mocks.choose).not.toHaveBeenCalled();
  mocks.root.mockImplementation(() => { throw new Error('project removed'); });
  await expect(dialogsHandlers.dialogs.saveDrawing({ projectId: 'project', title: 'Sketch', scene: JSON.stringify(emptyDrawingDocument()) }, ctx)).rejects.toThrow('project removed');
  expect(mocks.choose).not.toHaveBeenCalled();
});
