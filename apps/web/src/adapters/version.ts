/**
 * Whether a newer text-to-cad is out (`cadgen/updates.py`, served by `cadgen.viewer`'s
 * `/__cad/version`): the update button's notice, or null.
 */
import type { UpdateCall, UpdateNotice } from '@text-to-cad/ui/update';

export const version: UpdateCall = async () => {
  const response = await fetch('/__cad/version');
  if (!response.ok) throw new Error(`version: ${response.status}`);
  return await response.json() as { notice: UpdateNotice | null };
};
