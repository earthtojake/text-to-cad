/**
 * Whether a newer text-to-cad is out (`cadgen/updates.py`, served by `cadgen.viewer`'s
 * `/__cad/version`), and the person's answer to the update card: the release they copied the
 * prompt for, or closed the card on, which is not offered again.
 */
import type { UpdateCall, UpdateNotice } from '@text-to-cad/ui/update';

const HEADERS = { 'x-cadgen-viewer': '1', 'content-type': 'application/json' };

export const version: UpdateCall = async dismiss => {
  const response = dismiss === undefined
    ? await fetch('/__cad/version')
    : await fetch('/__cad/version', { method: 'POST', headers: HEADERS, body: JSON.stringify({ dismiss }) });
  if (!response.ok) throw new Error(`version: ${response.status}`);
  return await response.json() as { notice: UpdateNotice | null };
};
