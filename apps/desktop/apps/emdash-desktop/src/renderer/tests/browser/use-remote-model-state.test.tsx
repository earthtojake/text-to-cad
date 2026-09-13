import { defineContract, liveModel, liveState } from '@emdash/wire/rpc';
import { cell, type RemoteModel } from '@emdash/wire/state';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { useRemoteModelState } from '@core/primitives/wire/browser/use-remote-model-state';

const contract = defineContract({
  values: liveModel({
    key: z.object({ id: z.string() }),
    states: {
      value: liveState({ data: z.object({ count: z.number() }) }),
    },
  }),
}).values;

describe('useRemoteModelState', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('does not resubscribe when callers pass inline options and callbacks', async () => {
    const source = cell({ count: 1 });
    const remoteModel = (() => ({
      states: { value: source },
      mutations: {},
    })) as unknown as RemoteModel<typeof contract>;
    const getRemote = vi.fn(async () => remoteModel);
    let renderCount = 0;

    function Consumer({ parentVersion }: { readonly parentVersion: number }) {
      renderCount += 1;
      const result = useRemoteModelState(contract, () => getRemote(), { id: 'one' }, 'value', {
        initialValue: { count: 0 },
      });
      return (
        <div data-count={result.value?.count ?? 'missing'} data-parent-version={parentVersion} />
      );
    }

    await act(async () => {
      root.render(<Consumer parentVersion={1} />);
    });
    await vi.waitFor(() =>
      expect(container.firstElementChild?.getAttribute('data-count')).toBe('1')
    );

    for (const version of [2, 3, 4]) {
      await act(async () => {
        root.render(<Consumer parentVersion={version} />);
      });
    }

    expect(getRemote).toHaveBeenCalledTimes(1);
    expect(renderCount).toBeGreaterThan(1);

    await act(async () => {
      source.set({ count: 2 });
    });

    await vi.waitFor(() =>
      expect(container.firstElementChild?.getAttribute('data-count')).toBe('2')
    );
  });
});
