import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { emptyDrawingDocument } from '@hardcore/core/drawing';
import { performIntegrationCommand } from '@renderer/state/integration-commands';
import { useExplorer } from '@renderer/state/explorer';
import { getDrawingScene, retainDrawingScene } from '@renderer/state/drawings';
import { useProjects } from '@renderer/state/projects';
import { useUi } from '@renderer/state/ui';

const capture = vi.hoisted(() => vi.fn());
vi.mock('@hardcore/ui/drawing', () => ({ exportDrawingScenePng: capture }));
let projectId: string;
let sequence = 0;
beforeEach(() => {
  vi.useFakeTimers();
  capture.mockReset().mockResolvedValue({ type: 'image/png', arrayBuffer: async () => new Uint8Array([137, 80, 78, 71]).buffer });
  projectId = `drawing-project-${++sequence}`;
  useProjects.setState({ projects: [projectId, 'other'].map(id => ({ id, name: id, path: `/projects/${id}`, createdAt: 0 })), activeId: projectId });
  useExplorer.setState({ projectId, root: null, tabs: [], activeId: null, ready: true });
  useUi.setState({ route: 'app' });
});
afterEach(() => { useExplorer.getState().discardProjectResources(projectId); vi.runOnlyPendingTimers(); vi.useRealTimers(); });

it('opens an empty temporary canvas and reports identity without an editable scene', async () => {
  const root = '/worktrees/sketch';
  const result = await performIntegrationCommand({ requestId: 'r', kind: 'open-drawing', projectId, root, title: 'Plan' }) as { tabId: string };
  expect(getDrawingScene(result.tabId)).toBeNull();
  expect(await performIntegrationCommand({ requestId: 'r', kind: 'drawing-state', projectId, root, tabId: result.tabId })).toEqual({
    tabId: result.tabId, title: 'Plan', root, ephemeral: true, elementCount: 0,
  });
  expect(await performIntegrationCommand({ requestId: 'r', kind: 'list-tabs', projectId, root })).toMatchObject({
    active: result.tabId, tabs: [{ id: result.tabId, kind: 'drawing', title: 'Plan', root, ephemeral: true }],
  });
});
it('reads and captures a background drawing without changing project, tab, root or Settings', async () => {
  const tab = useExplorer.getState().open('drawing', { root: '/worktrees/sketch', title: 'Plan' })!;
  const scene = JSON.stringify({ ...emptyDrawingDocument(), elements: [{ id: 'ink', type: 'rectangle', x: 0, y: 0, width: 20, height: 20 }] });
  retainDrawingScene(tab.id, () => scene);
  await useExplorer.getState().bindProject('other');
  useProjects.getState().setActive('other');
  useUi.getState().openSettings();
  const active = useExplorer.getState().activeId;
  const root = useExplorer.getState().root;
  const command = { requestId: 'r', projectId, root: '/worktrees/sketch', tabId: tab.id };
  const state = await performIntegrationCommand({ ...command, kind: 'drawing-state' });
  expect(state).toEqual({ tabId: tab.id, title: 'Plan', root: '/worktrees/sketch', ephemeral: true, elementCount: 1 });
  expect(state).not.toHaveProperty('scene');
  expect(await performIntegrationCommand({ ...command, kind: 'drawing-capture' })).toMatchObject({ tabId: tab.id, mimeType: 'image/png', base64: 'iVBORw==' });
  expect(capture).toHaveBeenCalledWith(scene);
  expect(useProjects.getState().activeId).toBe('other');
  expect(useExplorer.getState()).toMatchObject({ projectId: 'other', activeId: active, root });
  expect(useUi.getState().route).toBe('settings');
});
it('refuses other projects, other roots and closed drawing tabs before capture', async () => {
  const tab = useExplorer.getState().open('drawing', { root: '/worktrees/sketch' })!;
  const base = { requestId: 'r', kind: 'drawing-capture' as const, projectId, tabId: tab.id };
  await expect(performIntegrationCommand({ ...base, root: null })).rejects.toThrow(/closed|workspace/);
  await expect(performIntegrationCommand({ ...base, projectId: 'other', root: '/worktrees/sketch' })).rejects.toThrow(/closed|workspace/);
  useExplorer.getState().close(tab.id);
  await expect(performIntegrationCommand({ ...base, root: '/worktrees/sketch' })).rejects.toThrow('closed');
  expect(capture).not.toHaveBeenCalled();
});
it('renames an inactive drawing without switching projects or accepting a different root', async () => {
  const tab = useExplorer.getState().open('drawing', { root: '/worktrees/sketch', title: 'Plan' })!;
  await useExplorer.getState().bindProject('other');
  const command = { requestId: 'r', projectId, tabId: tab.id, root: '/worktrees/sketch', kind: 'drawing-rename' as const, title: '  Revised plan  ' };
  await expect(performIntegrationCommand({ ...command, root: null })).rejects.toThrow(/closed|workspace/);
  expect(await performIntegrationCommand(command)).toMatchObject({ title: 'Revised plan' });
  expect(await performIntegrationCommand({ ...command, kind: 'drawing-state' })).toMatchObject({ title: 'Revised plan', elementCount: 0 });
  expect(useExplorer.getState().projectId).toBe('other');
});
it('propagates encoder failures without changing the current sketch', async () => {
  const tab = useExplorer.getState().open('drawing')!;
  const scene = JSON.stringify({ ...emptyDrawingDocument(), elements: [{ id: 'ink', type: 'rectangle', x: 0, y: 0, width: 20, height: 20 }] });
  retainDrawingScene(tab.id, () => scene);
  capture.mockRejectedValueOnce(new Error('Encoder failed'));
  await expect(performIntegrationCommand({ requestId: 'r', kind: 'drawing-capture', projectId, tabId: tab.id })).rejects.toThrow('Encoder failed');
  expect(getDrawingScene(tab.id)).toBe(scene);
});
