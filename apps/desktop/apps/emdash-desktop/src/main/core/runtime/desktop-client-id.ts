import { randomUUID } from 'node:crypto';
import { desktopKeyValueStore } from '@main/db/kv';

const DESKTOP_CLIENT_ID_KEY = 'desktop-client-id';

let cachedClientId: string | undefined;

export async function getDesktopClientId(): Promise<string> {
  if (cachedClientId) return cachedClientId;

  const existing = await desktopKeyValueStore.get(DESKTOP_CLIENT_ID_KEY);
  if (existing.success && typeof existing.data === 'string' && existing.data.length > 0) {
    cachedClientId = existing.data;
    return existing.data;
  }

  const next = randomUUID();
  const saved = await desktopKeyValueStore.set(DESKTOP_CLIENT_ID_KEY, next);
  if (!saved.success) throw new Error(saved.error.message);
  cachedClientId = next;
  return next;
}
