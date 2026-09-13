import type { SessionUpdate, ToolCallContent } from '@agentclientprotocol/sdk';

const DATA_IMAGE_URL = /data:image\/[a-z0-9.+-]+(?:;[^,\s]*)?;base64,[a-z0-9+/_=-]+/gi;

/**
 * Remove provider-owned image bytes before raw ACP diagnostics or enrichment.
 * The original update still flows to attachment ingress; every persisted or
 * normalized representation must contain only the durable attachment ref.
 */
export function redactToolOutputImageData(update: SessionUpdate): SessionUpdate {
  if (update.sessionUpdate !== 'tool_call' && update.sessionUpdate !== 'tool_call_update') {
    return update;
  }
  const redactedValues = imageRedactionValues(update);
  if (redactedValues.size === 0) return update;

  const content = update.content?.map((block): ToolCallContent => {
    if (block.type !== 'content' || block.content.type !== 'image') return block;
    return {
      ...block,
      content: {
        ...block.content,
        data: '',
        ...(isImageDataUrl(block.content.uri) ? { uri: undefined } : {}),
        _meta: {
          ...(block.content._meta ?? {}),
          'emdash/attachment': {
            redacted: true,
          },
        },
      },
    };
  });

  return {
    ...update,
    ...(content !== undefined ? { content } : {}),
    ...('rawOutput' in update
      ? { rawOutput: redactMatchingStrings(update.rawOutput, redactedValues) }
      : {}),
    ...(update._meta
      ? { _meta: redactMatchingStrings(update._meta, redactedValues) as SessionUpdate['_meta'] }
      : {}),
  } as SessionUpdate;
}

function imageRedactionValues(update: SessionUpdate): Set<string> {
  const values = new Set<string>();
  if (update.sessionUpdate !== 'tool_call' && update.sessionUpdate !== 'tool_call_update') {
    return values;
  }
  for (const block of update.content ?? []) {
    if (block.type !== 'content' || block.content.type !== 'image') continue;
    if (block.content.data) values.add(block.content.data);
    if (isImageDataUrl(block.content.uri)) values.add(block.content.uri);
  }
  return values;
}

function isImageDataUrl(value: string | null | undefined): value is string {
  return typeof value === 'string' && /^data:image\//i.test(value);
}

function redactMatchingStrings(value: unknown, redactedValues: ReadonlySet<string>): unknown {
  if (typeof value === 'string') {
    if (redactedValues.has(value)) return '';
    let redacted = value.replace(DATA_IMAGE_URL, '');
    for (const candidate of redactedValues) {
      // Exact short values were handled above. Substring replacement is for
      // real image payloads wrapped in provider prose or serialized JSON.
      if (candidate.length >= 64 && redacted.includes(candidate)) {
        redacted = redacted.split(candidate).join('');
      }
    }
    return redacted;
  }
  if (Array.isArray(value)) {
    return value.map((item) => redactMatchingStrings(item, redactedValues));
  }
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [key, redactMatchingStrings(item, redactedValues)])
  );
}
