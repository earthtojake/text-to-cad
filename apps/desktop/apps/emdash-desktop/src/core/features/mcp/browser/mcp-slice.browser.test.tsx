import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import type { McpServer } from '@emdash/core/primitives/mcp/api';
import { ok } from '@emdash/shared';
import { defineContract } from '@emdash/wire/rpc';
import { cell, expose } from '@emdash/wire/state';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { getMcpClient } from '@core/features/mcp/api/browser/client';
import { seedSliceWire } from '@core/primitives/wire/browser/testing';
import { mcpContract, mcpDomain } from '../api';
import {
  resetInstalledMcpServersLiveModelForTests,
  useInstalledMcpServersLiveModel,
} from './live-model-hooks';

// Done-proof for the core wire seam: the mcp slice's client and live-model
// hook run unmodified against a fake controller impl seeded through
// `seedSliceWire` — no renderer host, no Electron, no other slices. This is
// the pattern for testing any slice in isolation through the seam.

function fakeServer(name: string): McpServer {
  return { name, transport: 'stdio', command: 'npx', args: ['-y', name], env: {}, providers: [] };
}

// Live-model providers bind by endpoint id, and ids are derived from the
// mount path — so the fake provider must be built against the domain-nested
// def, exactly as production mounts slice contracts in the desktop wire.
const nestedMcpContract = defineContract({ [mcpDomain]: mcpContract })[mcpDomain];

describe('mcp slice through the wire seam', () => {
  const servers = cell<McpServer[]>([fakeServer('context7')]);
  const savedInputs: unknown[] = [];
  let handle: { dispose: () => Promise<void> };
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    savedInputs.length = 0;
    servers.set([fakeServer('context7')]);
    handle = seedSliceWire(mcpDomain, mcpContract, {
      servers: expose(nestedMcpContract.servers, { list: servers }),
      saveServer: async (input: unknown) => {
        savedInputs.push(input);
        return ok(undefined);
      },
      removeServer: async () => ok(undefined),
      removeForAgent: async () => ok(undefined),
      listForAgent: async () => ok({ servers: [fakeServer('for-agent')] }),
    });
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(async () => {
    act(() => root.unmount());
    container.remove();
    await resetInstalledMcpServersLiveModelForTests();
    await handle.dispose();
  });

  it('routes slice client procedures to the fake impl', async () => {
    const client = await getMcpClient();

    const saved = await client.saveServer({ host: LOCAL_HOST_REF, server: fakeServer('linear') });
    expect(saved.success).toBe(true);
    expect(savedInputs).toEqual([{ host: LOCAL_HOST_REF, server: fakeServer('linear') }]);

    const listed = await client.listForAgent({ host: LOCAL_HOST_REF, providerId: 'claude' });
    expect(listed).toEqual(ok({ servers: [fakeServer('for-agent')] }));
  });

  it('streams live-model updates into the slice hook', async () => {
    function InstalledServers() {
      const { data, isLoading } = useInstalledMcpServersLiveModel(LOCAL_HOST_REF);
      return (
        <div data-names={data.map((server) => server.name).join(',')} data-loading={isLoading} />
      );
    }

    await act(async () => {
      root.render(<InstalledServers />);
    });
    await vi.waitFor(() =>
      expect(container.firstElementChild?.getAttribute('data-names')).toBe('context7')
    );

    act(() => {
      servers.set([fakeServer('context7'), fakeServer('playwright')]);
    });
    await vi.waitFor(() =>
      expect(container.firstElementChild?.getAttribute('data-names')).toBe('context7,playwright')
    );
  });
});
