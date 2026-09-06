import type { HostFileRef } from '@emdash/core/primitives/path/api';
import { toast } from '@emdash/ui/react/primitives';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';

/**
 * Opens a file with the operating system's default application. The explicit
 * sibling verb of {@link openFile} (spec §10) — used by the chat "open
 * external" affordance and the binary/too-large placeholder actions — never a
 * silent fallback of the editor open path.
 */
export async function openWithOS(target: HostFileRef | string): Promise<void> {
  const path = typeof target === 'string' ? target : nativePathFromHost(target.path);
  const result = await (await getHostClient()).openPath({ path });
  if (!result.success) {
    toast.error(`Could not open ${path}: ${result.error}`);
  }
}
