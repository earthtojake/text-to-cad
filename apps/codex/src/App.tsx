import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { FolderX } from 'lucide-react';
import type { ResourceRef } from '@text-to-cad/core/prompt';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { createTabStore, memoryTabRecord } from '@text-to-cad/ui/tab-store';
import type { Bridge, HostContext } from './host/bridge';
import { watchViewEvents } from './host/events';
import { createLiveRegistry, describeView } from './host/live';
import type { Launch, Root, Server, Session } from './host/server';
import Home from './Home';
import ModelView, { type ViewReporter } from './ModelView';

interface Showing { launch: Launch; sequence: number; fromHome: boolean }

const rootKey = (root: Root) => `${root.kind}:${root.path}`;
// The host's sandbox need not be a secure context, where randomUUID is missing.
const newViewId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
const unresolved = () => { throw new Error('No model is showing.'); };

export function useHostContext(bridge: Pick<Bridge, 'hostContext' | 'onHostContext'>): HostContext {
  return useSyncExternalStore(listener => bridge.onHostContext(listener), () => bridge.hostContext, () => bridge.hostContext);
}

/** Room for what the host draws over the page (the composer, on a full page). */
function Frame({ context, children }: { context: HostContext; children: ReactNode }) {
  const insets = context.safeAreaInsets || {};
  return <div className="flex h-svh flex-col overflow-hidden" style={{ paddingTop: insets.top || 0, paddingRight: insets.right || 0, paddingBottom: insets.bottom || 0, paddingLeft: insets.left || 0 }}>
    <div className="relative min-h-0 flex-1">{children}</div>
  </div>;
}

/**
 * One CAD view. Which page it shows comes from its launch and from what the agent or the user
 * opens next; nothing here asks where the view is.
 */
export default function App({ bridge, server, launch: initial, session }: { bridge: Bridge; server: Server; launch: Launch; session: Session }) {
  const surface = initial.surface || initial.page;
  const view = useMemo(newViewId, []);
  const live = useMemo(createLiveRegistry, []);
  const tabStore = useMemo(() => createTabStore(memoryTabRecord()), []);
  const context = useHostContext(bridge);
  const colorScheme = context.theme === 'dark' ? 'dark' : 'light';
  const [showing, setShowing] = useState<Showing>({ launch: initial, sequence: 0, fromHome: false });
  const shown = useRef<{ model: string | null; resolvePath: (resource: ResourceRef) => string }>({ model: null, resolvePath: unresolved });
  const reporter = useMemo<ViewReporter>(() => ({
    showing(model, resolvePath) {
      shown.current = { model, resolvePath };
      void server.report(view, surface, model, {}, true).catch(() => {});
    },
  }), [server, view, surface]);

  useEffect(() => {
    const lifetime = new AbortController();
    watchViewEvents(server, { id: view, surface, model: () => shown.current.model }, {
      show: launch => setShowing(previous => ({ launch, sequence: previous.sequence + 1, fromHome: previous.fromHome || previous.launch.page === 'home' })),
      capture: async () => {
        const controller = live.current();
        if (!controller) throw new Error('No model is showing in this CAD view.');
        return controller.capture();
      },
      describe: () => describeView(live.current(), shown.current.model, shown.current.resolvePath),
    }, lifetime.signal);
    const stop = bridge.onTeardown(() => lifetime.abort());
    // The view a person last touched is the one the agent's tools mean.
    let last = 0;
    const touched = () => {
      if (Date.now() - last < 2000) return;
      last = Date.now();
      void server.report(view, surface, shown.current.model, {}, true).catch(() => {});
    };
    window.addEventListener('pointerdown', touched, true);
    window.addEventListener('focus', touched);
    return () => { lifetime.abort(); stop(); window.removeEventListener('pointerdown', touched, true); window.removeEventListener('focus', touched); };
  }, [bridge, server, view, surface, live]);

  const home = initial.page === 'home' ? initial : null;
  const { launch } = showing;
  if (launch.page === 'home') {
    return <Frame context={context}>
      <Home server={server} onOpen={next => setShowing(previous => ({ launch: next, sequence: previous.sequence + 1, fromHome: true }))}
        onOpenLink={url => bridge.request('ui/open-link', { url }).then(() => {})} />
    </Frame>;
  }
  if (!launch.root) {
    return <Frame context={context}>
      <EmptyState icon={FolderX} title="No model open" description="This chat has no project folder. Ask the agent to show a model by its path." />
    </Frame>;
  }
  return <Frame context={context}>
    <ModelView key={rootKey(launch.root)} launch={launch} root={launch.root} sequence={showing.sequence} bridge={bridge} server={server}
      tabStore={tabStore} live={live} colorScheme={colorScheme} platform={session.platform} reporter={reporter}
      onHome={home && showing.fromHome ? () => setShowing(previous => ({ launch: home, sequence: previous.sequence + 1, fromHome: false })) : undefined} />
  </Frame>;
}
