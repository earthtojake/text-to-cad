import { createPromptDeliveryLedger, formatPromptMessage, validatePromptContext } from '@text-to-cad/core/prompt';
import type { PromptContext, PromptContextPort, PromptDeliveryResult, PromptDestinationState, PromptPart, ResourceRef } from '@text-to-cad/core/prompt';
import type { AttachmentStore } from '@text-to-cad/ui/host';
import { HostError, type Bridge } from './bridge';
import type { Presentation } from './presentation';
import { encodeBase64 } from './tunnel';

const MAX_ITEMS = 24;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;
// JSON-RPC's "invalid params": what a host answers a message whose content it does not take.
const INVALID_PARAMS = -32602;

type Attachment = Extract<PromptPart, { kind: 'attachment' }>;
/** One block of a message or of the composer's model context: text or an image, titled for the context popover. */
type Block =
  | { type: 'text'; text: string; _meta?: { 'openai/title': string } }
  | { type: 'image'; data: string; mimeType: string; _meta?: { 'openai/title': string } };

/** What this host's chat takes from a view: context for the next message (Queue), and a message now (Send). */
export interface ChatReach { queue: boolean; send: boolean; sendImages: boolean }

/**
 * What the chat this view belongs to takes from it, as the host declared when it greeted the
 * page. Queue needs `updateModelContext`, except from a tab host (Codex), which is not asked: its
 * frames forward the method whether or not they declare it. Send needs `message`, and a picture
 * rides in the message only where the host takes images there (`message.image`).
 */
export function chatReach(hostCapabilities: Bridge['hostCapabilities'], presentation: Presentation): ChatReach {
  const message = hostCapabilities.message as { image?: unknown } | undefined;
  return {
    queue: presentation === 'tabs' || Boolean(hostCapabilities.updateModelContext),
    send: Boolean(message),
    sendImages: Boolean(message?.image),
  };
}

const baseName = (path: string) => path.split(/[\\/]/).pop() || path;

async function png(part: Attachment): Promise<Blob> {
  const blob = await part.content;
  if (blob.type !== 'image/png' || blob.size > MAX_IMAGE_BYTES) throw new Error('A prompt image is a PNG of at most 20 MiB.');
  return blob;
}

/**
 * The chat this view belongs to, as the viewer's prompt port. `deliver` is Queue: the context goes
 * into the composer's model context for the person's next message. The host replaces that context
 * on every update, so the port keeps what this view has queued and sends all of it; when the host
 * clears the context (the message went, or the chip was removed) it starts again. `send`, where the
 * host takes messages, posts the context as the person's message now. A picture is an image block
 * where the host takes one; where it does not, it is saved (`attachments`) and the text names it.
 */
export function createChatPromptContext(bridge: Pick<Bridge, 'request' | 'onHostContext' | 'hostContext'>, { resolvePath, reach, attachments }: {
  resolvePath(resource: ResourceRef): string; reach: ChatReach; attachments?: AttachmentStore;
}): PromptContextPort & { dispose(): void } {
  const state: PromptDestinationState = Object.freeze(reach.queue ? {
    kind: 'composer', available: true,
    capabilities: { attachments: 'images-and-text', maxParts: 128, maxAttachmentBytes: MAX_IMAGE_BYTES, mixedTextAndImage: 'atomic' },
  } satisfies PromptDestinationState : { kind: 'unavailable', available: false, reason: 'This chat takes no added context.' } satisfies PromptDestinationState);
  const ledger = createPromptDeliveryLedger({ busyMessage: 'Wait for the last message to reach the chat.' });
  let queued: Block[] = [];
  let queueing: Promise<unknown> = Promise.resolve();
  const stop = bridge.onHostContext(context => { if (context['openai/modelContext'] === null) queued = []; });

  // The file the context is about, for the context popover's titles.
  const fileOf = (context: PromptContext) => {
    const reference = context.parts.find(part => part.kind === 'reference');
    const resource = reference?.kind === 'reference' ? reference.reference.resource : null;
    return resource ? baseName(resource.kind === 'url' ? resource.url : resource.path) : '';
  };
  const titled = (what: string, file: string) => (file ? `${what} · ${file}` : what);
  // What the person wrote heads the title; a context of references alone is named by them.
  function textTitle(context: PromptContext): string {
    if (context.parts.some(part => part.kind === 'text')) return titled('Quick edit', fileOf(context));
    const selectors = context.parts.flatMap(part => part.kind === 'reference' && part.reference.target.kind === 'cad-selector' ? part.reference.target.selectors : []);
    return titled(selectors.join(', ') || 'CAD file', fileOf(context));
  }
  const imageBlock = async (part: Attachment, title?: string): Promise<Block> => ({
    type: 'image', data: encodeBase64(new Uint8Array(await (await png(part)).arrayBuffer())), mimeType: 'image/png',
    ...(title ? { _meta: { 'openai/title': title } } : {}),
  });
  const attachmentsOf = (context: PromptContext) => context.parts.filter((part): part is Attachment => part.kind === 'attachment');
  const deliveryFailure = (context: unknown) => {
    if (context && typeof context === 'object' && Array.isArray((context as PromptContext).parts)) {
      for (const part of (context as PromptContext).parts) if (part?.kind === 'attachment' && part.content) void Promise.resolve(part.content).catch(() => {});
    }
    try { validatePromptContext(context); return null; }
    catch (error) { return Promise.resolve<PromptDeliveryResult>({ status: 'failed', message: error instanceof Error ? error.message : String(error) }); }
  };

  const port: PromptContextPort & { dispose(): void } = {
    getSnapshot: () => state,
    subscribe: () => () => {},
    deliver(context) {
      if (!reach.queue) return Promise.resolve({ status: 'failed', message: state.reason });
      const invalid = deliveryFailure(context);
      if (invalid) return invalid;
      return ledger.deliver(context.operationId, async (): Promise<PromptDeliveryResult> => {
        const file = fileOf(context);
        const blocks: Block[] = [{ type: 'text', text: formatPromptMessage(context, { resolvePath }), _meta: { 'openai/title': textTitle(context) } }];
        for (const part of attachmentsOf(context)) blocks.push(await imageBlock(part, titled(part.label || 'CAD view', file)));
        // Updates replace each other, so they go out one at a time, in order.
        const update = queueing.then(async () => {
          const next = [...queued, ...blocks].slice(-MAX_ITEMS);
          await bridge.request('ui/update-model-context', { content: next }, { timeoutMs: 15_000 });
          queued = next;
        });
        queueing = update.catch(() => {});
        await update;
        return { status: 'added', partIds: context.parts.map(part => part.id) };
      });
    },
    dispose: stop,
  };
  if (!reach.send) return port;

  async function post(context: PromptContext, images: boolean) {
    const blocks: Block[] = [];
    const saved = new Map<string, string>();
    for (const part of attachmentsOf(context)) {
      if (images) blocks.push(await imageBlock(part));
      else if (attachments) saved.set(part.id, await attachments.save(await png(part), part.name));
    }
    const text = formatPromptMessage(context, { resolvePath, attachmentPath: part => saved.get(part.id) });
    await bridge.request('ui/message', { role: 'user', content: [{ type: 'text', text }, ...blocks] }, { timeoutMs: 30_000 });
  }
  port.send = context => {
    const invalid = deliveryFailure(context);
    if (invalid) return invalid;
    return ledger.deliver(`send:${context.operationId}`, async (): Promise<PromptDeliveryResult> => {
      const pictured = attachmentsOf(context).length > 0;
      try { await post(context, reach.sendImages && pictured); }
      catch (error) {
        // A host that declares images in messages and still refuses this one gets the picture as a file.
        if (!(error instanceof HostError && error.code === INVALID_PARAMS && reach.sendImages && pictured && attachments)) throw error;
        await post(context, false);
      }
      return { status: 'sent', partIds: context.parts.map(part => part.id) };
    });
  };
  return port;
}
