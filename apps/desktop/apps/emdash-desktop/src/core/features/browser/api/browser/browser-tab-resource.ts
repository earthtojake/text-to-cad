import { reaction } from 'mobx';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import type { BrowserSessionSnapshot } from '@core/primitives/browser/api';
import type {
  TabEntry,
  TabHandle,
  TabResource,
} from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';
import type { BrowserState } from './browser-tab-state';
import { getBrowserClient } from './client';

/**
 * Domain resource for a single open browser tab.
 *
 * On construction, restores the browser session if needed (from snapshot).
 * On dispose, removes the session and unregisters from RPC.
 *
 * Subscribes to the open-in-new-tab event and opens a sibling browser tab via
 * handle.open('browser', { initialUrl }).
 *
 * Maintains a MobX reaction to keep entry.state.session current so that
 * snapshots always reflect the live URL/title — no `getSerializablePayload` needed.
 */
export class BrowserTabResource implements TabResource {
  readonly browserId: string;
  private _unsubscribeOpenInNewTab: () => void = () => {};
  private readonly _disposeSessionSync: () => void;
  private _disposed = false;

  constructor(entry: TabEntry<BrowserState>, handle: TabHandle) {
    const payload = entry.state;
    this.browserId = payload.browserId;

    // Restore the session if it doesn't exist yet (snapshot restore path).
    // On fresh open, the session was already created in onBeforeOpen().
    if (!browserSessionStore.getSession(payload.browserId)) {
      browserSessionStore.restoreSession(payload.session, undefined);
    }

    // Subscribe to open-in-new-tab requests for this browser.
    void this._subscribeOpenInNewTab(handle);

    // Keep entry.state.session in sync with the live session store so that
    // snapshots captured from entry.state always reflect the current URL/title.
    this._disposeSessionSync = reaction(
      () => browserSessionStore.getSession(this.browserId),
      (liveSession) => {
        if (liveSession) {
          entry.state = { ...entry.state, session: liveSession };
        }
      }
    );
  }

  dispose(): void {
    this._disposed = true;
    this._unsubscribeOpenInNewTab();
    this._disposeSessionSync();
    browserSessionStore.removeSession(this.browserId);
    void getBrowserClient().then((client) =>
      client.unregisterSession({ browserId: this.browserId })
    );
  }

  /** Current live session snapshot (for display). */
  get session(): BrowserSessionSnapshot | undefined {
    return browserSessionStore.getSession(this.browserId);
  }

  private async _subscribeOpenInNewTab(handle: TabHandle): Promise<void> {
    const client = await getBrowserClient();
    const unsubscribe = await client.events.subscribe(undefined, {
      onEvent: (event) => {
        if (event.type !== 'open-in-new-tab' || event.sourceBrowserId !== this.browserId) return;
        handle.open('browser', { initialUrl: event.url });
      },
      onGap: () => {},
    });
    if (this._disposed) unsubscribe();
    else this._unsubscribeOpenInNewTab = unsubscribe;
  }
}
