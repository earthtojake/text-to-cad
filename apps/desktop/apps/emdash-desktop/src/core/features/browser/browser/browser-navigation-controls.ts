import { normalizeBrowserUrl } from '@core/primitives/browser/api';

export type BrowserReloadDecision =
  | { kind: 'reload-adapter' }
  | { kind: 'stop-adapter' }
  | { kind: 'retry-url'; url: string }
  | { kind: 'noop' };

export function decideBrowserReload(input: {
  currentUrl: string;
  isLoading: boolean;
  hasAdapter: boolean;
}): BrowserReloadDecision {
  if (input.hasAdapter) {
    return input.isLoading ? { kind: 'stop-adapter' } : { kind: 'reload-adapter' };
  }

  const normalized = normalizeBrowserUrl(input.currentUrl);
  return normalized.ok ? { kind: 'retry-url', url: normalized.url } : { kind: 'noop' };
}
