/**
 * How the host presents this view, and how views that the host never unmounts step aside.
 *
 * The server tells a host that mounts views inline (a new one per tool call, in the chat) by a
 * `<meta name="cad-presentation" content="inline">` it puts in the page's head; a host that shows
 * tabs gets the page untouched. Inline, every launch carries its place among the views (`order`,
 * stamped by the server), and the views of a chat elect the newest over a `BroadcastChannel`: the
 * others keep a still of their last frame and let go of everything else.
 */

export type Presentation = 'inline' | 'tabs';

export function readPresentation(doc: Pick<Document, 'querySelector'> = document): Presentation {
  return doc.querySelector('meta[name="cad-presentation"]')?.getAttribute('content') === 'inline' ? 'inline' : 'tabs';
}

/** A view's place: server wall-clock time, then the server's count, then the view's own token. */
export interface Order { createdAt: number; seq: number }
export interface Placed { view: string; order: Order }

export function isNewer(other: Placed, mine: Placed): boolean {
  if (other.order.createdAt !== mine.order.createdAt) return other.order.createdAt > mine.order.createdAt;
  if (other.order.seq !== mine.order.seq) return other.order.seq > mine.order.seq;
  return other.view > mine.view;
}

interface Channel { postMessage(message: unknown): void; close(): void; onmessage: ((event: MessageEvent) => void) | null }

/**
 * Take part in the election among this chat's views: `onSuperseded` runs once, when a newer view is
 * heard from. A view says hello when it mounts, and every view answers a hello, so a view that
 * mounts late (an old one, scrolled back into sight) learns at once that it is not the newest.
 */
export function watchSupersession(name: string, me: Placed, onSuperseded: () => void,
  open: (name: string) => Channel = channel => new BroadcastChannel(channel)): () => void {
  let channel: Channel;
  try { channel = open(name); } catch { return () => {}; }
  let superseded = false;
  channel.onmessage = event => {
    const peer = event.data as (Placed & { type?: string }) | null;
    if (!peer || peer.view === me.view || !peer.order) return;
    if (peer.type === 'hello') channel.postMessage({ type: 'here', ...me });
    if (!superseded && isNewer(peer, me)) { superseded = true; onSuperseded(); }
  };
  channel.postMessage({ type: 'hello', ...me });
  return () => channel.close();
}
