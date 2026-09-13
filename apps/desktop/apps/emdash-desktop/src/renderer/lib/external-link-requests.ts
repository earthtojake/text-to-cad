import { confirmOpenExternalLink } from '@core/features/workbench/api/browser/open-external-link';
import { getDesktopWireClient } from './runtime/desktop-wire-client';

export function wireExternalLinkRequests() {
  let disposed = false;
  let unsubscribe: (() => void) | undefined;
  void getDesktopWireClient().then(async (client) => {
    const nextUnsubscribe = await client.host.events.subscribe(undefined, {
      onEvent: (event) => {
        if (event.type === 'external-link-open-requested') confirmOpenExternalLink(event.url);
      },
      onGap: () => {},
    });
    if (disposed) nextUnsubscribe();
    else unsubscribe = nextUnsubscribe;
  });
  return () => {
    disposed = true;
    unsubscribe?.();
  };
}
