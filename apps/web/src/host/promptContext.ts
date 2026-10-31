import { createPromptDeliveryLedger, formatPromptContextText, validatePromptContext } from '@text-to-cad/core/prompt';
import type { PromptContextPort, PromptDeliveryResult, PromptDestinationState } from '@text-to-cad/core/prompt';
import type { WebClipboard } from './clipboard';
import { english } from '@text-to-cad/ui/i18n';

/**
 * Prepare portable clipboard content without claiming an external composer pasted it. What it says
 * to the person (busy, a partial copy) is in `t`'s language, read as it speaks.
 */
export function createWebPromptContext(clipboard: WebClipboard, supportsImages = typeof clipboard.writeImage === 'function',
  t: (key: string, params?: Record<string, unknown>) => string = english): PromptContextPort {
  const capabilities: NonNullable<PromptDestinationState['capabilities']> = {
    attachments: supportsImages ? 'png' : 'none', maxParts: 128, maxAttachmentBytes: 20 * 1024 * 1024,
    mixedTextAndImage: supportsImages && clipboard.writeContent ? 'representations' : 'unsupported',
  };
  const state: PromptDestinationState = Object.freeze({ kind: 'clipboard', available: true, capabilities });
  // The ledger's refusal while busy is said in the person's language as it is said, not when the port was made.
  const BUSY = 'Wait for pending clipboard operations before copying more.';
  const ledger = createPromptDeliveryLedger({ busyMessage: BUSY });
  const said = (result: PromptDeliveryResult): PromptDeliveryResult =>
    (result.status === 'failed' && result.message === BUSY ? { ...result, message: t('web.prompt.busy') } : result);
  return {
    getSnapshot: () => state,
    subscribe: () => () => {},
    deliver(context) {
      if (context && Array.isArray(context.parts)) for (const part of context.parts) if (part?.kind === 'attachment' && part.content) void Promise.resolve(part.content).catch(() => {});
      try { validatePromptContext(context); }
      catch (error) { return Promise.resolve({ status: 'failed', message: error instanceof Error ? error.message : String(error) }); }
      return ledger.deliver(context.operationId, (): Promise<PromptDeliveryResult> => {
        if (context.parts.length > 128) throw new Error('Prompt context has too many parts.');
        const attachments = context.parts.filter(part => part.kind === 'attachment');
        if (attachments.length && !supportsImages) throw new Error('Clipboard image copy is not supported in this browser.');
        if (attachments.length > 1 || attachments.some(part => part.mimeType !== 'image/png')) throw new Error('The browser can copy one PNG image per action. Copy other attachments separately.');
        const textIds = context.parts.filter(part => part.kind !== 'attachment').map(part => part.id);
        const text = textIds.length ? formatPromptContextText(context) : undefined;
        const image = attachments[0] ? Promise.resolve(attachments[0].content).then(blob => {
          if (blob.type !== 'image/png' || blob.size > 20 * 1024 * 1024) throw new Error('Prompt image must be a PNG of at most 20 MiB.');
          return blob;
        }) : undefined;
        // A rejected encoder must also be consumed when the host rejects the combination.
        void image?.catch(() => {});
        const partIds = context.parts.map(part => part.id);
        // No await precedes this call: ClipboardItem can carry the pending Blob.
        if (image !== undefined && text !== undefined) {
          if (!clipboard.writeContent) throw new Error('This browser cannot copy text and an image together. Copy them separately.');
          return clipboard.writeContent({ text, image }).then(() => ({ status: 'partial', partIds, message: t('web.prompt.partial') }));
        }
        const write = image !== undefined ? clipboard.writeImage(image) : clipboard.writeText(text ?? '');
        return write.then(() => ({ status: 'copied', partIds }));
      }).then(said);
    },
  };
}
