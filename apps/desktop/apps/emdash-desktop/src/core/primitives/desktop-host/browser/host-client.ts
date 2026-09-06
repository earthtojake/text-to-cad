import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { desktopHostContract, desktopHostDomain } from '../api/host-contract';

export type HostClient = ContractClient<typeof desktopHostContract>;

/** Typed client for the desktop host wire domain (shell, clipboard, dialogs, window). */
export function getHostClient(): Promise<HostClient> {
  return domainClient<HostClient>(desktopHostDomain, desktopHostContract);
}

export async function openExternal(url: string) {
  return (await getHostClient()).openExternal({ url });
}

export async function copyTextToClipboard(text: string) {
  return (await getHostClient()).clipboardWriteText({ text });
}
