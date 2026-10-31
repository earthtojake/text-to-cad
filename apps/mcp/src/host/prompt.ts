import { createPromptDeliveryLedger, resolvePromptMessage, validatePromptContext } from '@text-to-cad/core/prompt';
import type { PromptContext, PromptContextPort, PromptDeliveryResult, PromptDestinationState } from '@text-to-cad/core/prompt';
import { HostError, type Bridge } from './bridge';
import type { Presentation } from './presentation';
import { english } from '@text-to-cad/ui/i18n';

const MAX_ITEMS = 24;
const METHOD_NOT_FOUND = -32601;

/** One text block naming the handoff's JSON files by path. */
type Block = { type: 'text'; text: string; _meta?: { 'openai/title': string } };

/** What this host's chat takes from a view: context for the next message (Queue), and a message now (Send). */
export interface ChatReach { queue: boolean; send: boolean }

/**
 * What the chat this view belongs to takes from it, as the host declared when it greeted the
 * page. Queue needs `updateModelContext`, except from a tab host (Codex), which is not asked: its
 * frames forward the method whether or not they declare it. Send needs `message`.
 */
export function chatReach(hostCapabilities: Bridge['hostCapabilities'], presentation: Presentation): ChatReach {
  const message = hostCapabilities.message;
  return {
    queue: presentation === 'tabs' || Boolean(hostCapabilities.updateModelContext),
    send: Boolean(message),
  };
}

const baseName = (path: string) => path.split(/[\\/]/).pop() || path;

/**
 * The chat this view belongs to, as the viewer's prompt port. `deliver` is Queue: the context goes
 * into the composer's model context for the person's next message. The host replaces that context
 * on every update, so the port keeps what this view has queued and sends all of it; when the host
 * clears the context (the message went, or the chip was removed) it starts again. `send`, where the
 * host takes messages, posts the context as the person's message now. The text names each
 * JSON file by its saved path (`part.path`); its bytes never travel in the message.
 */
export function createChatPromptContext(bridge: Pick<Bridge, 'request' | 'onHostContext' | 'hostContext'>, { reach, t = english }: {
  reach: ChatReach;
  /** What the person reads when the chat takes nothing, or is still busy: in the view's language. */
  t?: (key: string, params?: Record<string, unknown>) => string;
}): PromptContextPort & { dispose(): void } {
  const state: PromptDestinationState = Object.freeze(reach.queue ? {
    kind: 'composer', available: true,
    capabilities: { attachments: 'none', maxParts: 128, maxAttachmentBytes: 0, mixedTextAndImage: 'unsupported' },
  } satisfies PromptDestinationState : { kind: 'unavailable', available: false, reason: t('cad.prompt.noContext') } satisfies PromptDestinationState);
  // The ledger's refusal while busy is said in the person's language as it is said, not when the port was made.
  const BUSY = 'Wait for the last message to reach the chat.';
  const ledger = createPromptDeliveryLedger({ busyMessage: BUSY });
  const said = (result: PromptDeliveryResult): PromptDeliveryResult =>
    (result.status === 'failed' && result.message === BUSY ? { ...result, message: t('cad.prompt.busy') } : result);
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
  const textOf = resolvePromptMessage;
  const deliveryFailure = (context: unknown) => {
    if (context && typeof context === 'object' && Array.isArray((context as PromptContext).parts)) {
      for (const part of (context as PromptContext).parts) if (part?.kind === 'attachment') {
        if (part.path) void Promise.resolve(part.path).catch(() => {});
        if (part.inlineText) void Promise.resolve(part.inlineText).catch(() => {});
      }
    }
    try { validatePromptContext(context); return null; }
    catch (error) { return Promise.resolve<PromptDeliveryResult>({ status: 'failed', message: error instanceof Error ? error.message : String(error) }); }
  };

  const port: PromptContextPort & { dispose(): void } = {
    getSnapshot: () => state,
    subscribe: () => () => {},
    deliver(context) {
      if (!reach.queue) return Promise.resolve({ status: 'failed', message: t('cad.prompt.noContext') });
      const invalid = deliveryFailure(context);
      if (invalid) return invalid;
      return ledger.deliver(context.operationId, async (): Promise<PromptDeliveryResult> => {
        const blocks: Block[] = [{ type: 'text', text: await textOf(context), _meta: { 'openai/title': textTitle(context) } }];
        // Updates replace each other, so they go out one at a time, in order.
        const update = queueing.then(async () => {
          const next = [...queued, ...blocks].slice(-MAX_ITEMS);
          await bridge.request('ui/update-model-context', { content: next }, { timeoutMs: 15_000 });
          queued = next;
        });
        queueing = update.catch(() => {});
        try { await update; }
        catch (error) {
          // A tab host is not asked whether it takes context (Codex forwards it undeclared), so one
          // that does not answers "Method not found": say what to do instead of the bare JSON-RPC error.
          if (error instanceof HostError && error.code === METHOD_NOT_FOUND) {
            return { status: 'failed', message: t('cad.prompt.notTaken') };
          }
          throw error;
        }
        return { status: 'added', partIds: context.parts.map(part => part.id) };
      }).then(said);
    },
    dispose: stop,
  };
  if (!reach.send) return port;

  port.send = context => {
    const invalid = deliveryFailure(context);
    if (invalid) return invalid;
    return ledger.deliver(`send:${context.operationId}`, async (): Promise<PromptDeliveryResult> => {
      const text = await textOf(context);
      await bridge.request('ui/message', { role: 'user', content: [{ type: 'text', text }] }, { timeoutMs: 30_000 });
      return { status: 'sent', partIds: context.parts.map(part => part.id) };
    }).then(said);
  };
  return port;
}
