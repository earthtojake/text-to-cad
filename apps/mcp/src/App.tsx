import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';
import { Maximize2 } from 'lucide-react';
import type { ResourceRef } from '@text-to-cad/core/prompt';
import { ConsentCard, useAnalyticsConsent } from '@text-to-cad/ui/consent';
import { useFeatures } from '@text-to-cad/ui/features';
import { UpdateButton, useUpdateNotice } from '@text-to-cad/ui/update';
import { viewerLinks } from '@text-to-cad/ui/links';
import { Button } from '@text-to-cad/ui/primitives/button';
import { TooltipHint } from '@text-to-cad/ui/primitives/tooltip';
import { createTabStore, memoryTabRecord } from '@text-to-cad/ui/tab-store';
import { version } from '../package.json';
import type { Bridge, HostContext } from './host/bridge';
import { fitCapture } from './host/capture';
import { frameClipboard } from './host/clipboard';
import { createLiveRegistry, describeView } from './host/live';
import { watchSupersession, type Presentation } from './host/presentation';
import { chatReach } from './host/prompt';
import type { Launch, Root, Server } from './host/server';
import { createViewSync } from './host/sync';
import ModelView, { type ViewReporter } from './ModelView';
import { Banner } from './Notice';

interface Showing { launch: Launch; sequence: number }

const rootKey = (root: Root) => `${root.kind}:${root.path}`;
// The host's sandbox need not be a secure context, where randomUUID is missing.
const newViewId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
const unresolved = () => { throw new Error('No model is showing.'); };

export function useHostContext(bridge: Pick<Bridge, 'hostContext' | 'onHostContext'>): HostContext {
  return useSyncExternalStore(listener => bridge.onHostContext(listener), () => bridge.hostContext, () => bridge.hostContext);
}

// A tab host's composer floats over the bottom of the page, its middle this far above the edge: the
// viewer's playback bars sit on that same line (Codex: a 45px box, 17px up).
const TAB_BOTTOM_CENTER = '40px';

// What to do once this view's server has gone: the host started it, and only the host starts it again.
const LOST: Record<Presentation, string> = {
  tabs: 'The CAD plugin stopped responding in this thread. Restart Codex to reconnect it.',
  inline: 'The CAD plugin stopped responding. Restart the app to reconnect it.',
};

// Inline, a view is a card in the chat: as tall as its width suits, within what the host allows.
const INLINE_ASPECT = 0.62, INLINE_MIN_HEIGHT = 320, INLINE_MAX_HEIGHT = 560;
export function inlineHeight(width: number, maxHeight?: number): number {
  const height = Math.round(Math.min(INLINE_MAX_HEIGHT, Math.max(INLINE_MIN_HEIGHT, width * INLINE_ASPECT)));
  return maxHeight ? Math.min(height, maxHeight) : height;
}

/**
 * Room for what the host draws over the page (`insets`). Inline, a card whose height the host is
 * told. The one element either way, so going full size keeps the view (and its model) as it is.
 */
function Frame({ bridge, context, insets, inline = false, bottomCenter, overlay = null, children }: { bridge: Bridge; context: HostContext; insets: NonNullable<HostContext['safeAreaInsets']>; inline?: boolean; bottomCenter?: string; overlay?: ReactNode; children: ReactNode }) {
  // Where the host's composer floats over the page instead of taking room from it: the line the
  // viewer's playback bars sit on, and the strip lists scroll clear of.
  const floating = bottomCenter ? { '--cad-viewport-bottom-center': bottomCenter, '--cad-host-bottom-inset': `${context.safeAreaInsets?.bottom || 0}px` } as CSSProperties : {};
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
    return <div className="flex h-svh flex-col overflow-hidden" style={{ paddingTop: insets.top || 0, paddingRight: insets.right || 0, paddingBottom: insets.bottom || 0, paddingLeft: insets.left || 0, ...floating }}>
      <div className="relative min-h-0 flex-1">{children}{overlay}</div>
    </div>;
  }
  return <div className="flex flex-col overflow-hidden" style={{ height }}>
    <div className="relative min-h-0 flex-1">{children}{overlay}</div>
  </div>;
}

/** Inline, the card's way to full size: the navbar's last control, and the home's. */
function FullSizeButton({ bridge }: { bridge: Bridge }) {
  const expand = () => void bridge.request('ui/request-display-mode', { mode: 'fullscreen' }).catch(() => {});
  return <TooltipHint content="Full size">
    <Button variant="ghost" size="icon-xs" className="size-6 text-muted-foreground hover:text-foreground" aria-label="Full size" onClick={expand}>
      <Maximize2 className="size-3.5" aria-hidden="true" />
    </Button>
  </TooltipHint>;
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
export default function App({ bridge, server, launch: initial, presentation = 'tabs' }: { bridge: Bridge; server: Server; launch: Launch; presentation?: Presentation }) {
  const surface = initial.surface || initial.page;
  // Inline, the server named this view (the agent reads it by that name); a tab names itself.
  const view = useMemo(() => initial.view ?? newViewId(), [initial.view]);
  const live = useMemo(createLiveRegistry, []);
  const tabStore = useMemo(() => createTabStore(memoryTabRecord()), []);
  const context = useHostContext(bridge);
  const colorScheme = context.theme === 'dark' ? 'dark' : 'light';
  const inline = presentation === 'inline' && context.displayMode !== 'fullscreen';
  // A tab runs the page's full height: what a tab host draws over its bottom (its composer) sits
  // clear of the viewer's centred playbar. A host that mounts views inline draws its composer
  // across the bottom of a full-size view, so that view keeps clear of it.
  const insets = presentation === 'inline' ? context.safeAreaInsets || {} : { ...context.safeAreaInsets, bottom: 0 };
  const chat = useMemo(() => chatReach(bridge.hostCapabilities, presentation), [bridge, presentation]);
  const bottomCenter = presentation === 'tabs' ? TAB_BOTTOM_CENTER : undefined;
  // Once a newer view of this chat is up: this one's last frame (or null), and nothing else.
  const [still, setStill] = useState<string | null | undefined>(undefined);
  const superseded = still !== undefined;
  const [showing, setShowing] = useState<Showing>({ launch: initial, sequence: 0 });
  // The server stopped answering (its process has gone): the view keeps its model, and says so.
  const [lost, setLost] = useState(false);
  const shown = useRef<{ model: string | null; resolvePath: (resource: ResourceRef) => string }>({ model: null, resolvePath: unresolved });
  // This view's one call to the server each second: what it shows, the agent's requests for it,
  // and what changed in what it watches (`host/sync.ts`).
  const sync = useMemo(() => createViewSync(server, { id: view, surface, model: () => shown.current.model }, {
    show: launch => setShowing(previous => ({ launch, sequence: previous.sequence + 1 })),
    capture: async () => {
      const controller = live.current();
      if (!controller) throw new Error('No model is showing in this CAD view.');
      return fitCapture(await controller.capture());
    },
    state: () => describeView(live.current(), shown.current.model, shown.current.resolvePath),
    connection: connected => setLost(!connected),
  }), [server, view, surface, live]);
  const reporter = useMemo<ViewReporter>(() => ({
    showing(model, resolvePath) {
      shown.current = { model, resolvePath };
      sync.focus();
    },
  }), [sync]);

  useEffect(() => {
    const order = initial.order;
    if (!order || !initial.view) return;
    let active = true;
    const stop = watchSupersession('cad-views', { view: initial.view, order }, () => void (async () => {
      let image: string | null = null;
      try { const png = await live.current()?.capture(); if (png) image = URL.createObjectURL(png); } catch { /* the note says enough */ }
      if (!active) return;
      setStill(image);
      void sync.close();
    })());
    return () => { active = false; stop(); };
  }, [initial.order, initial.view, live, sync]);

  useEffect(() => {
    if (superseded) return;
    const lifetime = new AbortController();
    sync.run(lifetime.signal);
    const stop = bridge.onTeardown(() => lifetime.abort());
    // The view a person last touched is the one the agent's tools mean: it says so on a sync now.
    let last = 0;
    const touched = () => {
      if (Date.now() - last < 2000) return;
      last = Date.now();
      sync.focus();
    };
    window.addEventListener('pointerdown', touched, true);
    window.addEventListener('focus', touched);
    return () => { lifetime.abort(); stop(); window.removeEventListener('pointerdown', touched, true); window.removeEventListener('focus', touched); };
  }, [bridge, sync, superseded]);

  // Asked once, of everyone, unless their environment answered or no answer could be kept
  // (`cadgen/analytics.py`): the card, and Settings' Analytics section after it.
  const { consent, answer, appSettings: analyticsSettings } = useAnalyticsConsent(server.consent);
  // Settings' Features (Quick edit), on until the person turns one off: kept by the server beside
  // the analytics answer, one choice for the sidebar, every thread's tab and the browser viewer.
  const { features, appSettings: featureSettings } = useFeatures(server.features);
  const appSettings = useMemo(() => [...analyticsSettings ?? [], ...featureSettings ?? []], [analyticsSettings, featureSettings]);
  // A newer text-to-cad (`cadgen/updates.py`): the blue update button, first in the navbar and on the
  // home while this install is behind. Its prompt goes to the chat where the host takes messages, so
  // the agent updates CAD; elsewhere it is copied.
  const updateNotice = useUpdateNotice(server.version);
  const sendPrompt = chat.send
    ? (prompt: string) => bridge.request('ui/message', { role: 'user', content: [{ type: 'text', text: prompt }] }, { timeoutMs: 30_000 }).then(() => {})
    : undefined;
  const openLink = (url: string) => void bridge.request('ui/open-link', { url }).catch(() => {});
  // The navbar's links: the same as every app's (X, Discord, GitHub and a new issue), followed through the
  // host (a frame cannot open one itself).
  const links = useMemo(() => viewerLinks({ version, open: url => bridge.request('ui/open-link', { url }).then(() => {}) }),
    [bridge]);
  // A view opened on the home (the sidebar's) goes back to it; one opened on a model has no home.
  // The home's launch carried its library as it stood when the sidebar opened: going back reads it anew.
  const home = initial.page === 'home' ? { ...initial, recents: undefined } : null;
  const goHome = home ? () => setShowing(previous => ({ launch: home, sequence: previous.sequence + 1 })) : undefined;
  const show = (launch: Launch) => setShowing(previous => ({ launch, sequence: previous.sequence + 1 }));
  const { launch } = showing;
  if (superseded) {
    return <Frame bridge={bridge} context={context} insets={insets} inline={inline} bottomCenter={bottomCenter}><Superseded still={still} /></Frame>;
  }
  return <Frame bridge={bridge} context={context} insets={insets} inline={inline} bottomCenter={bottomCenter}
    overlay={lost ? <Banner message={LOST[presentation]} /> : null}>
    <ModelView key={rootKey(launch.root)} launch={launch} root={launch.root} sequence={showing.sequence} bridge={bridge} server={server}
      tabStore={tabStore} live={live} links={links} appSettings={appSettings} features={features}
      notice={consent?.ask ? <ConsentCard policy={consent.policy} onAnswer={answer} onPolicy={openLink} /> : null}
      update={updateNotice ? <UpdateButton notice={updateNotice} send={sendPrompt} copy={prompt => frameClipboard.writeText(prompt)}
        onLink={openLink} /> : null}
      fullSize={inline && context.availableDisplayModes?.includes('fullscreen') !== false ? <FullSizeButton bridge={bridge} /> : null}
      colorScheme={colorScheme} platform={initial.platform || 'darwin'} reporter={reporter} sync={sync} chat={chat}
      onLaunch={show} onHome={goHome} />
  </Frame>;
}
