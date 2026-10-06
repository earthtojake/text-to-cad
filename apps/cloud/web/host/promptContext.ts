import { createPromptDeliveryLedger, formatPromptContextText, validatePromptContext } from '@text-to-cad/core/prompt';
import type { PromptContextPort, PromptDeliveryResult, PromptDestinationState } from '@text-to-cad/core/prompt';
import type { WebClipboard } from './clipboard.ts';

const MAX_PARTS = 128;
const MAX_IMAGE_BYTES = 20 * 1024 * 1024;

/**
 * The page's prompt destination: the clipboard (Copy for prompt). A context's text and references
 * are copied as text, its one PNG as an image, and both together as two representations of one
 * item where the browser can; nothing here claims a chat received them.
 */
export function createClipboardPromptContext(clipboard: WebClipboard, supportsImages = typeof clipboard.writeImage === 'function'): PromptContextPort {
  const capabilities: NonNullable<PromptDestinationState['capabilities']> = {
    attachments: supportsImages ? 'png' : 'none', maxParts: MAX_PARTS, maxAttachmentBytes: MAX_IMAGE_BYTES,
    mixedTextAndImage: supportsImages && clipboard.writeContent ? 'representations' : 'unsupported',
  };
  const state: PromptDestinationState = Object.freeze({ kind: 'clipboard', available: true, capabilities });
  const ledger = createPromptDeliveryLedger({ busyMessage: 'Wait for pending clipboard operations before copying more.' });
  return {
    getSnapshot: () => state,
    subscribe: () => () => {},
    deliver(context) {
      // Own every encoder before validation can reject the bundle.
      if (context && Array.isArray(context.parts)) for (const part of context.parts) if (part?.kind === 'attachment' && part.content) void Promise.resolve(part.content).catch(() => {});
      try { validatePromptContext(context); }
      catch (error) { return Promise.resolve({ status: 'failed', message: error instanceof Error ? error.message : String(error) }); }
      return ledger.deliver(context.operationId, (): Promise<PromptDeliveryResult> => {
        const attachments = context.parts.filter(part => part.kind === 'attachment');
        if (attachments.length && !supportsImages) throw new Error('Clipboard image copy is not supported in this browser.');
        if (attachments.length > 1 || attachments.some(part => part.mimeType !== 'image/png')) throw new Error('The browser can copy one PNG image per action. Copy other attachments separately.');
        const text = context.parts.some(part => part.kind !== 'attachment') ? formatPromptContextText(context) : undefined;
        const image = attachments[0] ? Promise.resolve(attachments[0].content).then(blob => {
          if (blob.type !== 'image/png' || blob.size > MAX_IMAGE_BYTES) throw new Error('Prompt image must be a PNG of at most 20 MiB.');
          return blob;
        }) : undefined;
        void image?.catch(() => {});
        const partIds = context.parts.map(part => part.id);
        if (image !== undefined && text !== undefined) {
          if (!clipboard.writeContent) throw new Error('This browser cannot copy text and an image together. Copy them separately.');
          return clipboard.writeContent({ text, image }).then(() => ({ status: 'partial', partIds, message: 'Text and PNG copied as separate clipboard representations. Some apps paste only one; paste and check both before sending.' }));
        }
        const write = image !== undefined ? clipboard.writeImage(image) : clipboard.writeText(text ?? '');
        return write.then(() => ({ status: 'copied', partIds }));
      });
    },
  };
}
