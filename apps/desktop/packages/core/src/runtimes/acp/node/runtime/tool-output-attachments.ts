import type { SessionUpdate } from '@agentclientprotocol/sdk';
import type { Logger } from '@emdash/shared/logger';
import type { AttachmentMimeType, AttachmentRef } from '#runtimes/acp/api';
import type { AttachmentStore } from './attachment-store';

export { redactToolOutputImageData } from '../agent-ports/tool-output-redaction';

const MAX_IMAGE_BYTES = 25 * 1024 * 1024;
const MAX_BASE64_LENGTH = Math.ceil(MAX_IMAGE_BYTES / 3) * 4;
const SUPPORTED_IMAGE_MIME_TYPES = new Set<AttachmentMimeType>([
  'image/png',
  'image/jpeg',
  'image/gif',
  'image/webp',
]);

type ProviderImage = {
  data: string;
  mimeType: string;
  uri?: string | null;
};

export async function persistToolOutputAttachments(input: {
  conversationId: string;
  update: SessionUpdate;
  attachmentStore: AttachmentStore | undefined;
  logger: Logger;
}): Promise<AttachmentRef[] | undefined> {
  const images = toolOutputImages(input.update);
  if (images.length === 0) return undefined;

  if (!input.attachmentStore) {
    input.logger.warn('SessionManager: ignored provider image output without attachment storage', {
      conversationId: input.conversationId,
      imageCount: images.length,
    });
    return undefined;
  }

  const attachments: AttachmentRef[] = [];
  const seen = new Set<string>();
  for (const [index, image] of images.entries()) {
    const mimeType = supportedMimeType(image.mimeType);
    if (!mimeType) {
      warnIgnoredImage(input, index, 'unsupported_mime_type', { mimeType: image.mimeType });
      continue;
    }

    const decoded = decodeBase64Image(image.data);
    if (!decoded.success) {
      warnIgnoredImage(input, index, decoded.reason);
      continue;
    }

    try {
      const ref = await input.attachmentStore.put({
        conversationId: input.conversationId,
        data: decoded.data,
        name: providerImageName(image, index, mimeType),
        mimeType,
        deduplicate: true,
      });
      if (!seen.has(ref.id)) {
        seen.add(ref.id);
        attachments.push(ref);
      }
    } catch (error) {
      warnIgnoredImage(input, index, 'storage_failed', {
        error: error instanceof Error ? error.message : String(error),
      });
    }
  }

  return attachments.length > 0 ? attachments : undefined;
}

function toolOutputImages(update: SessionUpdate): ProviderImage[] {
  if (
    (update.sessionUpdate === 'agent_message_chunk' ||
      update.sessionUpdate === 'user_message_chunk') &&
    update.content.type === 'image'
  ) {
    return [
      { data: update.content.data, mimeType: update.content.mimeType, uri: update.content.uri },
    ];
  }
  if (update.sessionUpdate !== 'tool_call' && update.sessionUpdate !== 'tool_call_update')
    return [];
  const images: ProviderImage[] = [];
  for (const block of update.content ?? []) {
    if (block.type !== 'content' || block.content.type !== 'image') continue;
    images.push({
      data: block.content.data,
      mimeType: block.content.mimeType,
      uri: block.content.uri,
    });
  }
  return images;
}

function supportedMimeType(value: string): AttachmentMimeType | null {
  const normalized = value.toLowerCase() as AttachmentMimeType;
  return SUPPORTED_IMAGE_MIME_TYPES.has(normalized) ? normalized : null;
}

function decodeBase64Image(
  encoded: string
):
  | { success: true; data: Uint8Array }
  | { success: false; reason: 'invalid_base64' | 'image_too_large' } {
  // Bound the provider string before normalizing whitespace to avoid a second unbounded allocation.
  if (encoded.length > MAX_BASE64_LENGTH + 1024) {
    return { success: false, reason: 'image_too_large' };
  }
  const compact = encoded.replace(/\s/g, '');
  if (compact.length === 0 || compact.length > MAX_BASE64_LENGTH) {
    return {
      success: false,
      reason: compact.length > MAX_BASE64_LENGTH ? 'image_too_large' : 'invalid_base64',
    };
  }
  if (
    compact.length % 4 === 1 ||
    !/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=|[A-Za-z0-9+/]{2,3})?$/.test(
      compact
    )
  ) {
    return { success: false, reason: 'invalid_base64' };
  }

  const padding = compact.endsWith('==') ? 2 : compact.endsWith('=') ? 1 : 0;
  const estimatedBytes = Math.floor((compact.length * 3) / 4) - padding;
  if (estimatedBytes > MAX_IMAGE_BYTES) return { success: false, reason: 'image_too_large' };

  const data = new Uint8Array(Buffer.from(compact, 'base64'));
  if (data.byteLength === 0 || data.byteLength > MAX_IMAGE_BYTES) {
    return {
      success: false,
      reason: data.byteLength > MAX_IMAGE_BYTES ? 'image_too_large' : 'invalid_base64',
    };
  }
  return { success: true, data };
}

function providerImageName(
  image: ProviderImage,
  index: number,
  mimeType: AttachmentMimeType
): string {
  const fromUri = filenameFromUri(image.uri);
  if (fromUri) return fromUri;
  const extension = mimeType === 'image/jpeg' ? 'jpg' : mimeType.slice('image/'.length);
  return `generated-image-${index + 1}.${extension}`;
}

function filenameFromUri(uri: string | null | undefined): string | null {
  if (!uri || uri.startsWith('data:')) return null;
  try {
    const path = new URL(uri, 'file:///').pathname;
    const name = decodeURIComponent(path.split('/').at(-1) ?? '').trim();
    return name && name !== '.' && name !== '..' ? name : null;
  } catch {
    return null;
  }
}

function warnIgnoredImage(
  input: Pick<
    Parameters<typeof persistToolOutputAttachments>[0],
    'conversationId' | 'update' | 'logger'
  >,
  index: number,
  reason: string,
  fields: Record<string, unknown> = {}
): void {
  input.logger.warn('SessionManager: ignored provider image output', {
    conversationId: input.conversationId,
    toolCallId:
      input.update.sessionUpdate === 'tool_call' ||
      input.update.sessionUpdate === 'tool_call_update'
        ? input.update.toolCallId
        : undefined,
    imageIndex: index,
    reason,
    ...fields,
  });
}

export const TOOL_OUTPUT_MAX_IMAGE_BYTES = MAX_IMAGE_BYTES;
