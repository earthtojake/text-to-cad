import { createPromptDeliveryLedger, formatPromptReference, validatePromptContext } from '@text-to-cad/core/prompt';
import type { PromptContext, PromptContextPort, PromptDeliveryResult, PromptDestinationState, ResourceRef } from '@text-to-cad/core/prompt';
import type { Bridge } from './bridge';
import type { Presentation } from './presentation';
import { encodeBase64 } from './tunnel';

const MAX_ITEMS = 24;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/** One block of the composer's model context: text or an image, titled for the context popover. */
type ContextBlock =
  | { type: 'text'; text: string; _meta: { 'openai/title': string } }
  | { type: 'image'; data: string; mimeType: string; _meta: { 'openai/title': string } };

const baseName = (path: string) => path.split(/[\\/]/).pop() || path;

/**
 * Whether Add to prompt has a composer to reach. A host that mounts views inline says so by
 * declaring `updateModelContext` when it greets the page; one that does not gets a viewer with no
 * Add to prompt at all. A tab host (Codex) is not asked: its frames forward the method whether or
 * not they declare it.
 */
export function reachesComposer(hostCapabilities: Bridge['hostCapabilities'], presentation: Presentation): boolean {
  return presentation === 'tabs' || Boolean(hostCapabilities.updateModelContext);
}

/**
 * Add to prompt, into the composer of the chat this view belongs to. The host's model context
 * is replaced on every update, so the port keeps what this view has added and sends all of it;
 * when the host clears the context (the message was sent, or the chip removed) it starts again.
 */
export function createComposerPromptContext(bridge: Pick<Bridge, 'request' | 'onHostContext' | 'hostContext'>, { resolvePath }: { resolvePath(resource: ResourceRef): string }): PromptContextPort & { dispose(): void } {
  const state: PromptDestinationState = Object.freeze({
    kind: 'composer', available: true,
    capabilities: { attachments: 'images-and-text', maxParts: 128, maxAttachmentBytes: MAX_IMAGE_BYTES, mixedTextAndImage: 'atomic' },
  } satisfies PromptDestinationState);
  const ledger = createPromptDeliveryLedger({ busyMessage: 'Wait for the last additions to reach the prompt.' });
  let blocks: ContextBlock[] = [];
  let sending: Promise<unknown> = Promise.resolve();
  const stop = bridge.onHostContext(context => { if (context['openai/modelContext'] === null) blocks = []; });

  async function toBlocks(context: PromptContext): Promise<ContextBlock[]> {
    const added: ContextBlock[] = [];
    const labels = new Map<string, string>();
    for (const part of context.parts) {
      if (part.kind === 'reference') {
        const text = formatPromptReference(part.reference, { resolvePath });
        const resource = part.reference.resource;
        const file = baseName(resource.kind === 'url' ? resource.url : resource.path);
        const target = part.reference.target;
        const what = part.reference.label || (target.kind === 'cad-selector' ? target.selectors.join(', ') : '');
        const title = what ? `${what} · ${file}` : file;
        labels.set(part.id, file);
        added.push({ type: 'text', text, _meta: { 'openai/title': title } });
      } else if (part.kind === 'text') {
        added.push({ type: 'text', text: part.text, _meta: { 'openai/title': 'CAD note' } });
      }
    }
    for (const part of context.parts) {
      if (part.kind !== 'attachment') continue;
      const blob = await part.content;
      if (blob.type !== 'image/png' || blob.size > MAX_IMAGE_BYTES) throw new Error('A prompt image is a PNG of at most 20 MiB.');
      const about = (part.about || []).map(id => labels.get(id)).find(Boolean);
      added.push({ type: 'image', data: encodeBase64(new Uint8Array(await blob.arrayBuffer())), mimeType: 'image/png', _meta: { 'openai/title': `CAD view · ${about || part.name.replace(/-view\.png$/, '')}` } });
    }
    return added;
  }

  return {
    getSnapshot: () => state,
    subscribe: () => () => {},
    deliver(context) {
      if (context && Array.isArray(context.parts)) for (const part of context.parts) if (part?.kind === 'attachment' && part.content) void Promise.resolve(part.content).catch(() => {});
      try { validatePromptContext(context); }
      catch (error) { return Promise.resolve({ status: 'failed', message: error instanceof Error ? error.message : String(error) }); }
      return ledger.deliver(context.operationId, async (): Promise<PromptDeliveryResult> => {
        const added = await toBlocks(context);
        // Updates replace each other, so they go out one at a time, in order.
        const send = sending.then(async () => {
          const next = [...blocks, ...added].slice(-MAX_ITEMS);
          await bridge.request('ui/update-model-context', { content: next }, { timeoutMs: 15_000 });
          blocks = next;
        });
        sending = send.catch(() => {});
        await send;
        return { status: 'added', partIds: context.parts.map(part => part.id) };
      });
    },
    dispose: stop,
  };
}
