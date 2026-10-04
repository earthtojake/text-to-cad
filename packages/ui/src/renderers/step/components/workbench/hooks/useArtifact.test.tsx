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
  const server = { tree, siblings: [] as string[], state: 'compiling', artifactReads: 0, catalogReads: 0, compiles: 0,
    gate: null as { after: number, held: Promise<void> } | null,
    // Hold every catalog read after the first `after` of them until the answer is released.
    holdCatalog(after: number) {
      let release!: () => void;
      server.gate = { after, held: new Promise<void>(resolve => { release = resolve; }) };
      return release;
    } };
  const fetch = async (url: string, init?: { method?: string }) => {
    const { pathname } = new URL(url, 'http://viewer.test');
    let body: unknown;
    if (pathname === '/__cad/catalog') {
      server.catalogReads += 1;
      if (server.gate && server.catalogReads > server.gate.after) await server.gate.held;
      body = { revision: `${server.tree}:${server.siblings.join(',')}`, entries: [
        { file: 'car.step', kind: 'assembly', url: server.tree ? `/__cad/store?file=${server.tree}/assembly.json` : '',
          hash: server.tree, documentHash: 'document-1' },
        ...server.siblings.map(file => ({ file, kind: 'part', url: `/__cad/store?file=${file}`, hash: file, documentHash: file })),
      ] };
    } else if (pathname === '/__cad/artifact' && init?.method === 'POST') {
      // The compile the client asked for: started, and followed through the status route.
      server.compiles += 1;
      server.state = 'compiling';
      body = { ok: true, state: 'compiling', runId: 'own-run' };
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
  const artifact = useArtifact(entry ? 'car.step' : '', { client,
    freshnessKey: artifactFreshnessKey(entry, catalog), shown: entryHasMesh(entry) });
  return { ...artifact, entry };
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

// The row the server keeps for a store it cannot read whole names no tree while the artifact status
// says compiled. The view read "Reading model" over it forever: compiled was reported with nothing
// said about whether it was the server's word, and the alert waits for loading to end.
it('reads the catalog again before a compiled status settles over an entry that names no tree', async () => {
  const { server, client } = workspace({ tree: '' });
  server.state = 'compiled';
  // The subscription's own read lists the file; the hook's read of the row is what is held.
  const release = server.holdCatalog(1);
  const { result } = renderHook(() => useStepArtifact(client));
  await elapse(10);
  expect(server.artifactReads).toBe(1);
  expect(server.catalogReads).toBe(2);
  // Until that read lands, compiled is the optimism a fresh selection starts with, and says so.
  expect(result.current).toMatchObject({ status: 'compiled', settled: false });
  release();
  await elapse(10);
  // The row still names no tree: the server's word, over which the renderer stops waiting. The
  // file was found compiled; no build of it ended here.
  expect(result.current).toMatchObject({ status: 'compiled', settled: true, built: false });
  expect(entryHasMesh(result.current.entry)).toBe(false);
  expect(server.catalogReads).toBe(2);
  client.dispose();
});

// A store that lost an object of the tree an entry names: the entry keeps its hash, the status
// says not compiled, and the compile the client starts restores the object at the same hash, so
// the entry never moves. The load that 404'd meanwhile is retried on the strength of `built`.
it('says when a compiled status is the end of a build it followed', async () => {
  const { server, client } = workspace();
  server.state = 'not-compiled';
  const { result } = renderHook(() => useStepArtifact(client));
  await elapse(10);
  expect(server.compiles).toBe(1);
  expect(result.current).toMatchObject({ status: 'compiling', settled: true, built: false });
  server.state = 'compiled';
  await elapse(1000);
  expect(result.current).toMatchObject({ status: 'compiled', settled: true, built: true });
  expect(result.current.entry.hash).toBe('tree-1');
  client.dispose();
});

it('reports a build\'s end as compiled only once the catalog lists the tree it wrote', async () => {
  const { server, client } = workspace({ tree: '' });
  const { result } = renderHook(() => useStepArtifact(client));
  await elapse(10);
  expect(result.current).toMatchObject({ status: 'compiling', settled: true });
  // The build ends: the status says compiled before the catalog has the row, as it does after
  // every compile. Compiled is not reported over the entry without its tree.
  const release = server.holdCatalog(server.catalogReads);
  server.state = 'compiled';
  await elapse(1000);
  expect(server.catalogReads).toBeGreaterThan(1);
  expect(result.current.status).toBe('compiling');
  server.tree = 'tree-2';
  release();
  await elapse(10);
  expect(result.current).toMatchObject({ status: 'compiled', settled: true });
  expect(entryHasMesh(result.current.entry)).toBe(true);
  client.dispose();
});
