import {
  BROWSER_DEFAULT_URL,
  BROWSER_PARTITION_PREFIX,
  normalizeBrowserUrl,
} from '@core/primitives/browser/api';

const BROWSER_PARTITION_INSTANCE_PREFIX = `${BROWSER_PARTITION_PREFIX}-`;

export type WebviewAttachParams = {
  src?: string;
  partition?: string;
  preload?: string;
  [key: string]: unknown;
};

export type WebviewPreferences = {
  nodeIntegration?: boolean;
  nodeIntegrationInSubFrames?: boolean;
  nodeIntegrationInWorker?: boolean;
  contextIsolation?: boolean;
  sandbox?: boolean;
  webSecurity?: boolean;
  allowRunningInsecureContent?: boolean;
  preload?: string;
};

export type WebviewAttachValidation =
  | { ok: true; partition: string; url: string }
  | { ok: false; reason: 'missing-partition' | 'unregistered-partition' | 'unsupported-url' };

export function isBrowserPartition(partition: string): boolean {
  return partition.startsWith(BROWSER_PARTITION_INSTANCE_PREFIX);
}

export function validateBrowserWebviewAttach(
  params: WebviewAttachParams,
  registeredPartitions: ReadonlySet<string>
): WebviewAttachValidation {
  const partition = typeof params.partition === 'string' ? params.partition : '';
  if (!isBrowserPartition(partition)) {
    return { ok: false, reason: 'missing-partition' };
  }
  if (!registeredPartitions.has(partition)) {
    return { ok: false, reason: 'unregistered-partition' };
  }

  const normalized = normalizeBrowserUrl(
    typeof params.src === 'string' && params.src.trim() ? params.src : BROWSER_DEFAULT_URL,
    { allowSearchQueries: false }
  );
  if (!normalized.ok) {
    return { ok: false, reason: 'unsupported-url' };
  }

  return { ok: true, partition, url: normalized.url };
}

export function hardenBrowserWebviewPreferences(webPreferences: WebviewPreferences): void {
  webPreferences.nodeIntegration = false;
  webPreferences.nodeIntegrationInSubFrames = false;
  webPreferences.nodeIntegrationInWorker = false;
  webPreferences.contextIsolation = true;
  webPreferences.sandbox = true;
  webPreferences.webSecurity = true;
  webPreferences.allowRunningInsecureContent = false;
  delete webPreferences.preload;
}

export function stripBrowserWebviewParams(params: WebviewAttachParams): void {
  delete params.preload;
}
