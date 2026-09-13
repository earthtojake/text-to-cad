import { stableStringify } from '@emdash/shared/util';

export function encodeTopic(refId: string, key: unknown): string {
  if (key === undefined) return refId;
  return `${refId}|${stableStringify(key)}`;
}

export function splitTopic(topic: string): { refId: string; rawKey: unknown } {
  const index = topic.indexOf('|');
  if (index === -1) return { refId: topic, rawKey: undefined };
  const encoded = topic.slice(index + 1);
  return {
    refId: topic.slice(0, index),
    rawKey: encoded.length === 0 ? undefined : JSON.parse(encoded),
  };
}
