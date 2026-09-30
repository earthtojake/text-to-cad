import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { FolderX, Maximize2 } from 'lucide-react';
import type { ResourceRef } from '@text-to-cad/core/prompt';
import { EmptyState } from '@text-to-cad/ui/navigation';
import { Button } from '@text-to-cad/ui/primitives/button';
import { createTabStore, memoryTabRecord } from '@text-to-cad/ui/tab-store';
import type { Bridge, HostContext } from './host/bridge';
import { watchViewEvents } from './host/events';
import { createLiveRegistry, describeView } from './host/live';
import { watchSupersession, type Presentation } from './host/presentation';
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

// Inline, a view is a card in the chat: as tall as its width suits, within what the host allows.
const INLINE_ASPECT = 0.62, INLINE_MIN_HEIGHT = 320, INLINE_MAX_HEIGHT = 560;
export function inlineHeight(width: number, maxHeight?: number): number {
  const height = Math.round(Math.min(INLINE_MAX_HEIGHT, Math.max(INLINE_MIN_HEIGHT, width * INLINE_ASPECT)));
  return maxHeight ? Math.min(height, maxHeight) : height;
}

/**
 * Room for what the host draws over the page (the composer, on a full page). Inline, a card whose
 * height the host is told, with a way to full size. The one element either way, so going full size
 * keeps the view (and its model) as it is.
 */
function Frame({ bridge, context, inline = false, expandable = true, children }: { bridge: Bridge; context: HostContext; inline?: boolean; expandable?: boolean; children: ReactNode }) {
  const insets = context.safeAreaInsets || {};
  const [width, setWidth] = useState(() => window.innerWidth);
  useEffect(() => {
    if (!inline) return;
    const measure = () => setWidth(window.innerWidth);
    window.addEventListener('resize', measure);
    return () => window.removeEventListener('resize', measure);
  }, [inline]);
  const height = inlineHeight(width, context.containerDimensions?.maxHeight);
  useEffect(() => { if (inline) bridge.notify('ui/notifications/size-changed', { height }); }, [bridge, inline, height]);
  if (!inline) {
    return <div className="flex h-svh flex-col overflow-hidden" style={{ paddingTop: insets.top || 0, paddingRight: insets.right || 0, paddingBottom: insets.bottom || 0, paddingLeft: insets.left || 0 }}>
      <div className="relative min-h-0 flex-1">{children}</div>
    </div>;
  }
  const expand = () => void bridge.request('ui/request-display-mode', { mode: 'fullscreen' }).catch(() => {});
  return <div className="flex flex-col overflow-hidden" style={{ height }}>
    <div className="relative min-h-0 flex-1">
      {children}
      {expandable && context.availableDisplayModes?.includes('fullscreen') !== false
        ? <Button variant="secondary" size="icon-sm" className="absolute right-2 top-2 z-40 shadow-sm" aria-label="Full size" title="Full size" onClick={expand}>
          <Maximize2 aria-hidden="true" />
        </Button> : null}
    </div>
  </div>;
}

/** A view a newer one replaced: its last frame, and where to look now. */
function Superseded({ still }: { still: string | null }) {
  return <div className="relative flex h-full items-center justify-center bg-background" data-cad-superseded="">
    {still ? <img src={still} alt="" className="h-full w-full object-contain opacity-60" /> : null}
    <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-md bg-background/90 px-2 py-1 text-xs text-muted-foreground shadow-sm">A newer view is below</span>
  </div>;
}

/**
 * One CAD view. Which page it shows comes from its launch and from what the agent or the user
 * opens next; nothing here asks where the view is.
 */
export default function App({ bridge, server, launch: initial, session, presentation = 'tabs' }: { bridge: Bridge; server: Server; launch: Launch; session: Session; presentation?: Presentation }) {
  const surface = initial.surface || initial.page;
  // Inline, the server named this view (the agent reads it by that name); a tab names itself.
  const view = useMemo(() => initial.view ?? newViewId(), [initial.view]);
  const live = useMemo(createLiveRegistry, []);
  const tabStore = useMemo(() => createTabStore(memoryTabRecord()), []);
  const context = useHostContext(bridge);
  const colorScheme = context.theme === 'dark' ? 'dark' : 'light';
  const inline = presentation === 'inline' && context.displayMode !== 'fullscreen';
  // Once a newer view of this chat is up: this one's last frame (or null), and nothing else.
  const [still, setStill] = useState<string | null | undefined>(undefined);
  const superseded = still !== undefined;
  const [showing, setShowing] = useState<Showing>({ launch: initial, sequence: 0, fromHome: false });
  const shown = useRef<{ model: string | null; resolvePath: (resource: ResourceRef) => string }>({ model: null, resolvePath: unresolved });
  const reporter = useMemo<ViewReporter>(() => ({
    showing(model, resolvePath) {
      shown.current = { model, resolvePath };
      void server.report(view, surface, model, {}, true).catch(() => {});
    },
  }), [server, view, surface]);

  useEffect(() => {
    const order = initial.order;
    if (!order || !initial.view) return;
    let active = true;
    const stop = watchSupersession('cad-views', { view: initial.view, order }, () => void (async () => {
      let image: string | null = null;
      try { const png = await live.current()?.capture(); if (png) image = URL.createObjectURL(png); } catch { /* the note says enough */ }
      if (!active) return;
      setStill(image);
      void server.report(view, surface, shown.current.model, { closed: true }, false).catch(() => {});
    })());
    return () => { active = false; stop(); };
  }, [initial.order, initial.view, live, server, view, surface]);

  useEffect(() => {
    if (superseded) return;
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
  }, [bridge, server, view, surface, live, superseded]);

  const home = initial.page === 'home' ? initial : null;
  const { launch } = showing;
  if (superseded) {
    return <Frame bridge={bridge} context={context} inline={inline} expandable={false}><Superseded still={still} /></Frame>;
  }
  if (launch.page === 'home') {
    return <Frame bridge={bridge} context={context} inline={inline}>
      <Home server={server} onOpen={next => setShowing(previous => ({ launch: next, sequence: previous.sequence + 1, fromHome: true }))}
        onOpenLink={url => bridge.request('ui/open-link', { url }).then(() => {})} />
    </Frame>;
  }
  if (!launch.root) {
    return <Frame bridge={bridge} context={context} inline={inline}>
      <EmptyState icon={FolderX} title="No model open" description="This chat has no project folder. Ask the agent to show a model by its path." />
    </Frame>;
  }
  return <Frame bridge={bridge} context={context} inline={inline}>
    <ModelView key={rootKey(launch.root)} launch={launch} root={launch.root} sequence={showing.sequence} bridge={bridge} server={server}
      tabStore={tabStore} live={live} colorScheme={colorScheme} platform={session.platform} reporter={reporter} compact={inline}
      onHome={home && showing.fromHome ? () => setShowing(previous => ({ launch: home, sequence: previous.sequence + 1, fromHome: false })) : undefined} />
  </Frame>;
}
