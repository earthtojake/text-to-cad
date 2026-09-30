import { describe, expect, it, vi } from 'vitest';
import { inlineHeight } from '../App';
import { createBridge } from './bridge';
import { isNewer, readPresentation, watchSupersession } from './presentation';

/** Channels that deliver to every other channel of the same name, as a BroadcastChannel does. */
function channels() {
  const open = new Set<any>();
  return (name: string) => {
    const channel: any = {
      name, onmessage: null,
      postMessage(message: unknown) { for (const other of open) if (other !== channel && other.name === name) queueMicrotask(() => other.onmessage?.({ data: message })); },
      close() { open.delete(channel); },
    };
    open.add(channel);
    return channel;
  };
}
const settle = () => new Promise(resolve => setTimeout(resolve, 0));
const placed = (view: string, createdAt: number, seq: number) => ({ view, order: { createdAt, seq } });

describe('how the host presents a view', () => {
  it('is inline only when the server says so in the head', () => {
    const head = (content?: string) => ({ querySelector: () => (content ? { getAttribute: () => content } : null) }) as unknown as Document;
    expect(readPresentation(head('inline'))).toBe('inline');
    expect(readPresentation(head())).toBe('tabs');
    expect(readPresentation(head('other'))).toBe('tabs');
  });

  it('offers a tab host fullscreen only, and an inline host both', async () => {
    const offered: unknown[] = [];
    for (const displayModes of [undefined, ['inline', 'fullscreen']]) {
      const listeners = new Set<(event: MessageEvent) => void>();
      const bridge = createBridge({
        postMessage(message: any) {
          if (message.method !== 'ui/initialize') return;
          offered.push(message.params.appCapabilities.availableDisplayModes);
          queueMicrotask(() => { for (const listener of listeners) listener({ data: { jsonrpc: '2.0', id: message.id, result: {} } } as MessageEvent); });
        },
      }, { addEventListener: (_type: string, listener: any) => listeners.add(listener), removeEventListener() {} } as any);
      await bridge.initialize({ name: 'CAD', version: 'test' }, displayModes ? { displayModes } : undefined);
    }
    expect(offered).toEqual([['fullscreen'], ['inline', 'fullscreen']]);
  });

  it('sizes an inline card by its width, within the host\'s cap', () => {
    expect([inlineHeight(300), inlineHeight(700), inlineHeight(2000), inlineHeight(700, 400)]).toEqual([320, 434, 560, 400]);
  });
});

describe('views a newer one replaced', () => {
  it('step aside for the newest, by the server\'s order, including one mounted late', async () => {
    const open = channels();
    const replaced: string[] = [];
    const join = (me: ReturnType<typeof placed>) => watchSupersession('cad-views', me, () => replaced.push(me.view), open);
    join(placed('a', 1000, 1));
    await settle();
    join(placed('b', 2000, 2));
    await settle();
    expect(replaced).toEqual(['a']);
    // An older view mounting after (a stored chat scrolled back into sight) hears that it is not the newest.
    join(placed('c', 500, 7));
    await settle();
    expect(replaced).toEqual(['a', 'c']);
    // Another name is another chat's channel.
    const other = vi.fn();
    watchSupersession('cad-views-elsewhere', placed('d', 1, 1), other, open);
    await settle();
    expect(other).not.toHaveBeenCalled();
  });

  it('orders by time, then the server\'s count, then the view', () => {
    expect(isNewer(placed('a', 2, 1), placed('b', 1, 9))).toBe(true);
    expect(isNewer(placed('a', 1, 2), placed('b', 1, 1))).toBe(true);
    expect(isNewer(placed('b', 1, 1), placed('a', 1, 1))).toBe(true);
    expect(isNewer(placed('a', 1, 1), placed('a', 1, 1))).toBe(false);
  });
});
