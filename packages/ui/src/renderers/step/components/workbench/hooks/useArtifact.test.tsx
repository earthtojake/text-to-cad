import { act, cleanup, renderHook } from '@testing-library/react';
import { useSyncExternalStore } from 'react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { createCadClient } from '@text-to-cad/core/client';
import { entryHasMesh } from '@text-to-cad/core/lib/entryAssets.js';
import { artifactFreshnessKey } from '../../../workbench/artifactResolution.js';
import { useArtifact } from './useArtifact.js';

beforeEach(() => { vi.useFakeTimers(); });
afterEach(() => { cleanup(); vi.useRealTimers(); });

// A viewer server for one STEP: its catalog (the file and whatever is beside it) and its
// artifact status, which a build somebody else started holds at `compiling`.
function workspace({ tree = 'tree-1' } = {}) {
  const server = { tree, siblings: [] as string[], state: 'compiling', artifactReads: 0, catalogReads: 0 };
  const fetch = async (url: string) => {
    const { pathname } = new URL(url, 'http://viewer.test');
    let body: unknown;
    if (pathname === '/__cad/catalog') {
      server.catalogReads += 1;
      body = { revision: `${server.tree}:${server.siblings.join(',')}`, entries: [
        { file: 'car.step', kind: 'assembly', url: server.tree ? `/__cad/store?file=${server.tree}/assembly.json` : '',
          hash: server.tree, documentHash: 'document-1' },
        ...server.siblings.map(file => ({ file, kind: 'part', url: `/__cad/store?file=${file}`, hash: file, documentHash: file })),
      ] };
    } else if (pathname === '/__cad/artifact') {
      server.artifactReads += 1;
      body = { ok: true, state: server.state, runId: 'peer-run' };
    } else throw new Error(`unexpected ${pathname}`);
    return { ok: true, status: 200, headers: new Headers(), json: async () => body };
  };
  const client = createCadClient({ origin: 'http://viewer.test', pollIntervalMs: 0, fetch });
  return { server, client };
}

// The file's artifact status as StepSurface asks it: from the file's catalog entry, and whether
// its model is already on screen (its entry names a built tree).
function useStepArtifact(client: ReturnType<typeof createCadClient>) {
  const catalog = useSyncExternalStore(client.subscribe, client.getSnapshot, client.getSnapshot);
  const entry = catalog.entries.find(item => item.file === 'car.step') || null;
  return useArtifact(entry ? 'car.step' : '', { client,
    freshnessKey: artifactFreshnessKey(entry, catalog), shown: entryHasMesh(entry) });
}

const elapse = (ms: number) => act(() => vi.advanceTimersByTimeAsync(ms));

it('leaves a peer\'s build of a model on screen to its build feed, whatever else the catalog gains', async () => {
  const { server, client } = workspace();
  const { result } = renderHook(() => useStepArtifact(client));
  await elapse(10);
  expect(server.artifactReads).toBe(1);
  expect(result.current.status).toBe('compiling');
  // A sibling written while the build runs is news for the catalog, and none for this file.
  server.siblings.push('zz_sibling.step');
  await act(() => client.refresh({ markRefreshing: false }));
  await elapse(6000);
  expect(server.artifactReads).toBe(1);
  // The build settles: its feed reads the catalog, whose entry now names the new tree.
  server.tree = 'tree-2';
  server.state = 'compiled';
  await act(() => client.refresh({ markRefreshing: false }));
  await elapse(10);
  expect(server.artifactReads).toBe(2);
  expect(result.current.status).toBe('compiled');
  client.dispose();
});

it('follows a peer\'s build of a model not yet on screen until it ends, then reads the catalog', async () => {
  const { server, client } = workspace({ tree: '' });
  const { result } = renderHook(() => useStepArtifact(client));
  await elapse(10);
  expect(result.current.status).toBe('compiling');
  await elapse(2000);
  const polls = server.artifactReads;
  expect(polls).toBeGreaterThan(3);
  const catalogReads = server.catalogReads;
  server.state = 'compiled';
  await elapse(1000);
  expect(result.current.status).toBe('compiled');
  expect(server.catalogReads).toBeGreaterThan(catalogReads);
  const settled = server.artifactReads;
  await elapse(3000);
  expect(server.artifactReads).toBe(settled);
  client.dispose();
});
