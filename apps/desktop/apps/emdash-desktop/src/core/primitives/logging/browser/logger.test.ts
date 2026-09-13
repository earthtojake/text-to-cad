import { afterEach, describe, expect, it, vi } from 'vitest';
import { loggingDomain, loggingWireContract } from '@core/primitives/logging/api/wire-contract';
import { seedSliceWire } from '@core/primitives/wire/browser/testing';
import { log } from './logger';

type RendererLogEntry = { level: string; source: string; input: unknown[] };

afterEach(() => {
  vi.restoreAllMocks();
});

describe('logging primitive', () => {
  it('forwards renderer log lines over the seeded slice wire, no renderer host', async () => {
    const received: RendererLogEntry[] = [];
    const handle = seedSliceWire(loggingDomain, loggingWireContract, {
      writeRendererLog: (entry: RendererLogEntry) => {
        received.push(entry);
      },
    });
    vi.spyOn(console, 'error').mockImplementation(() => {});

    log.error('boom', { code: 1 });

    await vi.waitFor(() => expect(received).toHaveLength(1));
    expect(received[0]).toEqual({
      level: 'error',
      source: 'renderer',
      input: ['boom', { code: 1 }],
    });

    await handle.dispose();
  });
});
