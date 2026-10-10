import type { CrossProbeMessage, CrossProbePort } from '@text-to-cad/ui/host';

/** The channel every viewer page on this origin shares: a board in one window, its schematic in another. */
export const CROSS_PROBE_CHANNEL = 'text-to-cad-cross-probe';

/**
 * Cross-probing between this machine's viewer pages, over a `BroadcastChannel`: one page's
 * selection reaches the others' (never its own). Absent where the browser has no BroadcastChannel.
 * The channel is open only while a view listens (a board or a schematic on screen): a page showing
 * anything else holds none, and the last listener's unsubscribe closes it.
 */
export function createBroadcastCrossProbe(name = CROSS_PROBE_CHANNEL): CrossProbePort | undefined {
  if (typeof BroadcastChannel !== 'function') return undefined;
  const listeners = new Set<(message: CrossProbeMessage) => void>();
  let channel: BroadcastChannel | null = null;
  const open = () => {
    if (channel) return channel;
    channel = new BroadcastChannel(name);
    channel.onmessage = (event: MessageEvent) => {
      const message = event.data as CrossProbeMessage | null;
      if (!message || typeof message.project !== 'string' || !Array.isArray(message.selectors)) return;
      for (const listener of listeners) listener(message);
    };
    return channel;
  };
  const closeIfUnheard = () => {
    if (listeners.size || !channel) return;
    channel.close();
    channel = null;
  };
  return {
    publish(message) {
      open().postMessage({ project: message.project, from: message.from, selectors: [...message.selectors] });
      closeIfUnheard();
    },
    subscribe(listener) {
      listeners.add(listener);
      open();
      return () => { listeners.delete(listener); closeIfUnheard(); };
    },
  };
}
