import { useEffect, useMemo, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react';
import { ExternalLink, Maximize2 } from 'lucide-react';
import { useAnalyticsConsent } from '@text-to-cad/ui/consent';
import { translator, useI18n, useLanguage } from '@text-to-cad/ui/i18n';
import { UpdateButton, useUpdate } from '@text-to-cad/ui/update';
import { viewerLinks } from '@text-to-cad/ui/links';
import { Button } from '@text-to-cad/ui/primitives/button';
import { TooltipHint } from '@text-to-cad/ui/primitives/tooltip';
import { createTabStore, memoryTabRecord } from '@text-to-cad/ui/tab-store';
import { normalizePath } from '@text-to-cad/ui/cad-viewer';
import { version } from '../package.json';
import type { Bridge, HostContext } from './host/bridge';
import { declaresOpenLinks } from './host/channel';
import { hostDisplayName } from './host/hostName';
import { captureSettled, fitCapture } from './host/capture';
import { createLiveRegistry, describeView } from './host/live';
import { watchSupersession, type Presentation } from './host/presentation';
import { chatReach } from './host/prompt';
import { loadNextRelease, useNextRelease } from './host/release';
import type { Launch, Server } from './host/server';
import { createViewSync } from './host/sync';
import { createTunnelClient, createTunnelFetch, TUNNEL_ORIGIN } from './host/tunnel';
import ModelView, { type ViewReporter } from './ModelView';
import { Banner } from './Notice';

interface Showing { launch: Launch; sequence: number }

declare const __TEXT_TO_CAD_BUILD__: string | undefined;
// Which build this page is, where it is not the release's own: vite.config.mjs names it
// (`@text-to-cad/ui/build-id`), and the version then reads `<version>-dev.<build>` (`0.8.0-dev.<build>`).
const BUILD = typeof __TEXT_TO_CAD_BUILD__ === 'string' ? __TEXT_TO_CAD_BUILD__ : '';

// The host's sandbox need not be a secure context, where randomUUID is missing.
const newViewId = () => globalThis.crypto?.randomUUID?.() ?? `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

export function useHostContext(bridge: Pick<Bridge, 'hostContext' | 'onHostContext'>): HostContext {
  return useSyncExternalStore(listener => bridge.onHostContext(listener), () => bridge.hostContext, () => bridge.hostContext);
}

// What to do once this view's server has gone -- it answered before, and stopped: the host started
// it, and only the host starts it again. (A chat that never carried a call is another state, with its
// own words: `Unreachable`, `Connection.tsx`.)
// Each said by its key in the view's language, naming the host to quit and reopen (`{host}`: what
// the host called itself at `ui/initialize`, as a person knows it; "this app" for one not known).
export const LOST: Record<Presentation, string> = {
  tabs: 'cad.lost.tabs',
  inline: 'cad.lost.inline',
};
export function lostNotice(say: (key: string, params?: Record<string, unknown>) => string, presentation: Presentation, hostName: string | null | undefined): string {
  return say(LOST[presentation], { host: hostDisplayName(hostName) ?? say('cad.lost.thisApp') });
}

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
function Frame({ bridge, context, insets, inline = false, floatingComposer = false, overlay = null, children }: { bridge: Bridge; context: HostContext; insets: NonNullable<HostContext['safeAreaInsets']>; inline?: boolean; floatingComposer?: boolean; overlay?: ReactNode; children: ReactNode }) {
  // Where the host's composer floats over the page instead of taking room from it: the room it
  // covers, which lists scroll clear of. Keep the cube in the opposite corner so a tab's
  // composer or sidebar chat button never covers it.
  const floating = {
    ...(floatingComposer ? { '--cad-host-bottom-inset': `${context.safeAreaInsets?.bottom || 0}px`,
      '--cad-viewport-corner-left': '2px', '--cad-viewport-corner-right': 'auto' } : {}),
  } as CSSProperties;
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

/**
 * Inline, the card's way to full size, where the host can show it so: in the navbar, before the
 * host's other actions, over a file and on the home; in the file handler's corner (`CardCorner`),
 * which has no navbar. Two diagonal arrows.
 */
function FullSizeButton({ bridge }: { bridge: Bridge }) {
  const { t } = useI18n();
  const label = t('navbar.fullSize');
  const expand = () => void bridge.request('ui/request-display-mode', { mode: 'fullscreen' }).catch(() => {});
  return <TooltipHint content={label}>
    <Button variant="ghost" size="icon-xs" className="size-6 text-muted-foreground hover:text-foreground" aria-label={label} onClick={expand}>
      <Maximize2 className="size-3.5" aria-hidden="true" />
    </Button>
  </TooltipHint>;
}

/**
 * The CAD Viewer's page of each document a launch named, from its `browser` (`cad_server/mcp/server.py`'s
 * `_reach`, the link a text client's `cad_show` gives): by absolute path, the home's under ''.
 */
type Pages = ReadonlyMap<string, string>;
function withPage(pages: Pages, launch: Launch): Pages {
  if (typeof launch.browser !== 'string') return pages;
  return new Map(pages).set(launch.model ? normalizePath(launch.model) : '', launch.browser);
}

/**
 * The page of what the view shows: the one its launch named, else (a file the person opened from the
 * home, which no launch named) the web viewer's home with the same day link, where that file leads
 * the library. Null where no launch carried a page.
 */
export function pageOf(pages: Pages, model: string | null): string | null {
  const known = pages.get(model ?? '');
  if (known) return known;
  const any = pages.values().next().value;
  if (!any) return null;
  try {
    const page = new URL(any);
    const token = page.searchParams.get('token');
    return `${page.origin}/${token ? `?${new URLSearchParams({ token })}` : ''}`;
  } catch {
    return null;
  }
}

/**
 * Open the web viewer's page of `model` (the home's with none) in the person's browser. The server
 * opens it itself, from this computer (`POST /api/v1/local/browser/open`, the app's alone, naming the
 * document and never a URL), as a host may not follow a link to a loopback page (Codex does not);
 * where it cannot (no display, a remote shell) or is not reached that way (`direct`), the launch's
 * page goes through the host's open-link request where it offers one, else as a plain link.
 */
async function openBrowserPage({ tunnel, direct, bridge, model, page }: {
  tunnel: typeof fetch; direct: boolean; bridge: Bridge; model: string | null; page: string;
}) {
  if (!direct) {
    const response = await tunnel(`${TUNNEL_ORIGIN}/api/v1/local/browser/open`, {
      method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ model }),
    }).catch(() => null);
    if (response?.ok) return;
  }
  const plain = () => { window.open(page, '_blank', 'noopener,noreferrer'); };
  if (declaresOpenLinks(bridge.hostCapabilities)) await bridge.request('ui/open-link', { url: page }).catch(plain);
  else plain();
}

/** The view's page in the person's browser (`openBrowserPage`): the navbar's last control, over every file and on the home. */
function OpenInBrowserButton({ open }: { open: () => void }) {
  const { t } = useI18n();
  const label = t('navbar.openInBrowser');
  return <TooltipHint content={label}>
    <Button variant="ghost" size="icon-xs" className="size-6 text-muted-foreground hover:text-foreground" aria-label={label} onClick={open}>
      <ExternalLink className="size-3.5" aria-hidden="true" />
    </Button>
  </TooltipHint>;
}

/** A view a newer one replaced: its last frame, and where to look now. */
function Superseded({ still, label }: { still: string | null; label: string }) {
  return <div className="relative flex h-full items-center justify-center bg-background" data-cad-superseded="">
    {still ? <img src={still} alt="" className="h-full w-full object-contain opacity-60" /> : null}
    <span className="absolute bottom-3 left-1/2 -translate-x-1/2 rounded-md bg-background/90 px-2 py-1 text-xs text-muted-foreground shadow-sm">{label}</span>
  </div>;
}

/**
 * One CAD view. Which page it shows comes from its launch and from what the agent or the user
 * opens next; nothing here asks where the view is. `direct`: the engine's routes reached over HTTP rather than through the host
 * (`host/direct.ts`), where the host carries no call back (`Connection.tsx`): every viewer request
 * goes that way, and the view makes no sync, which only the host could carry -- the agent cannot read
 * or capture it, and the client reads its catalog again on its own.
 */
export default function App({ bridge, server, launch: initial, presentation = 'tabs', direct }: { bridge: Bridge; server: Server; launch: Launch; presentation?: Presentation; direct?: typeof fetch }) {
  const surface = initial.surface || initial.page;
  // The host's file handler shows the file it opened, and only that: what the agent shows goes to
  // its thread's tab, never here (the server refuses it too).
  const alone = surface === 'file';
  // Inline, the server named this view (the agent reads it by that name); a tab names itself.
  const view = useMemo(() => initial.view ?? newViewId(), [initial.view]);
  const live = useMemo(createLiveRegistry, []);
  const tabStore = useMemo(() => createTabStore(memoryTabRecord()), []);
  const context = useHostContext(bridge);
  // The person's theme, from the app menu: System follows the host's; Light or Dark is theirs, over
  // it, for as long as this view is open (its tab store is the view's own).
  const tabSettings = useSyncExternalStore(tabStore.settings.subscribe, tabStore.settings.getSnapshot, tabStore.settings.getSnapshot);
  const preference = tabSettings.appearance;
  const colorScheme = preference === 'light' || preference === 'dark' ? preference : context.theme === 'dark' ? 'dark' : 'light';
  // After every host context too: the page's first theme is the host's (`main.tsx`), and a host
  // change of theme must not undo the person's.
  useEffect(() => {
    document.documentElement.classList.toggle('dark', colorScheme === 'dark');
    document.documentElement.style.colorScheme = colorScheme;
  }, [colorScheme, context]);
  const theme = useMemo(() => ({ preference, onPreferenceChange: (value: typeof preference) => tabStore.settings.update({ appearance: value }) }), [preference, tabStore]);
  const inline = presentation === 'inline' && context.displayMode !== 'fullscreen';
  // A tab runs the page's full height, its host's composer floating over its bottom; nothing of the
  // viewer sits at the bottom centre under it. A host that mounts views inline draws its composer
  // across the bottom of a full-size view, so that view keeps clear of it.
  const insets = presentation === 'inline' ? context.safeAreaInsets || {} : { ...context.safeAreaInsets, bottom: 0 };
  const chat = useMemo(() => chatReach(bridge.hostCapabilities, presentation), [bridge, presentation]);
  const floatingComposer = presentation === 'tabs';
  // Once a newer view of this chat is up: this one's last frame (or null), and nothing else.
  const [still, setStill] = useState<string | null | undefined>(undefined);
  const superseded = still !== undefined;
  const [showing, setShowing] = useState<Showing>({ launch: initial, sequence: 0 });
  // The server stopped answering (its process has gone), or answers refusing this view (what it said):
  // the view keeps its model, and says so.
  const [lost, setLost] = useState<boolean | string>(false);
  const shown = useRef<string | null>(null);
  // What the view shows, for its page in the browser: the launch's until the view says.
  const [showingModel, setShowingModel] = useState<string | null>(() => initial.model ? normalizePath(initial.model) : null);
  // The pages the launches carried: the first one's, then each the agent's shows bring.
  const [pages, setPages] = useState<Pages>(() => withPage(new Map(), initial));
  // The model the agent last showed here, until the view shows it (or anything after it): a capture
  // asked with the show, or right after it, is of that model, not of the one it is leaving.
  const asked = useRef<string | null>(null);
  // This view's one call to the server each second: what it shows, the agent's requests for it,
  // and what changed in what it watches (`host/sync.ts`).
  const sync = useMemo(() => createViewSync(server, { id: view, surface, model: () => shown.current }, {
    show: launch => {
      if (alone) return;
      asked.current = launch.model ? normalizePath(launch.model) : '';
      setPages(current => withPage(current, launch));
      setShowing(previous => ({ launch, sequence: previous.sequence + 1 }));
    },
    capture: async () => fitCapture(await captureSettled(live, () => asked.current ?? shown.current)),
    state: () => describeView(live.current(), shown.current),
    connection: (connected, refused) => setLost(connected ? false : refused || true),
  }), [server, view, surface, alone, live]);
  const reporter = useMemo<ViewReporter>(() => ({
    showing(model) {
      shown.current = model;
      asked.current = null;
      setShowingModel(model);
      sync.focus();
    },
  }), [sync]);
  // Everything else the view asks of the server travels as viewer requests over `cad_http`: its
  // model, the library, Open, Reveal, the person's settings and the update check. The client polls
  // nothing: the sync says when the file's catalog entry moved.
  const tunnel = useMemo(() => direct ?? createTunnelFetch(server), [server, direct]);
  const client = useMemo(() => createTunnelClient(tunnel, direct ? {} : { pollIntervalMs: 0 }), [tunnel, direct]);
  useEffect(() => () => client.dispose(), [client]);

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
    if (superseded || direct) return;
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
  }, [bridge, sync, superseded, direct]);

  // The usage stats cadgen sends (its telemetry), the same as the browser viewer's: nothing asks here (a
  // cad command says it once), and the app menu's switch changes it.
  // The person's language: inferred from the host's locale (its context's `locale`), else the frame's
  // browser languages, until they choose one in the app menu, which their settings keep for every CAD
  // view (`useLanguage`, the same as the browser viewer's).
  const { locale, language } = useLanguage(client.language, { preferred: [context.locale, ...(navigator.languages ?? [navigator.language])] });
  useEffect(() => { document.documentElement.lang = locale; }, [locale]);
  const { appSettings } = useAnalyticsConsent(client.consent, locale);
  // A newer text-to-cad (`cad_server/updates.py`), from the launch's notice at once, while this install is
  // behind: the update button, an icon first among the navbar's controls (in the file handler, which
  // has no navbar, in its corner). A click updates; once the engine restarts for it -- or goes from
  // under this card, another view's click -- the card asks for its release, and loads the engine's app
  // of the new one in place of its own (the shell a host keeps: `host/shell.ts`); should the switch fail
  // and go back, the engine of its own release says so, and the button says it once and is offered again.
  const updater = useUpdate({ read: client.version, start: client.startUpdate }, initial.notice ?? null);
  useNextRelease({ read: client.version, release: initial.version, watching: updater.phase.phase === 'restarting' || Boolean(lost),
    onNewRelease: loadNextRelease, onSameRelease: updater.settle });
  // The navbar's links: the same as every app's (X, Discord, GitHub and a new issue), followed through the
  // host (a frame cannot open one itself).
  const links = useMemo(() => viewerLinks({ version, build: BUILD, open: url => bridge.request('ui/open-link', { url }).then(() => {}) }),
    [bridge]);
  // The view's page in the browser, last in the navbar, where a launch carried one; never in the file
  // handler, which shows its file alone.
  const page = alone ? null : pageOf(pages, showingModel);
  const openInBrowser = page ? () => void openBrowserPage({ tunnel, direct: Boolean(direct), bridge, model: showingModel, page }) : null;
  const { launch } = showing;
  if (superseded) {
    return <Frame bridge={bridge} context={context} insets={insets} inline={inline} floatingComposer={floatingComposer}><Superseded still={still} label={translator(locale)('cad.superseded')} /></Frame>;
  }
  return <Frame bridge={bridge} context={context} insets={insets} inline={inline} floatingComposer={floatingComposer}
    overlay={lost ? <Banner message={typeof lost === 'string' ? lost : lostNotice(translator(locale), presentation, bridge.hostInfo.name)} /> : null}>
    <ModelView launch={launch} sequence={showing.sequence} alone={alone} bridge={bridge} client={client} tunnel={tunnel}
      tabStore={tabStore} live={live} links={links} appSettings={appSettings}
      update={updater.notice || updater.phase.phase !== 'idle' ? <UpdateButton notice={updater.notice} phase={updater.phase} onUpdate={updater.update} /> : null}
      fullSize={inline && context.availableDisplayModes?.includes('fullscreen') !== false ? <FullSizeButton bridge={bridge} /> : null}
      openInBrowser={openInBrowser ? <OpenInBrowserButton open={openInBrowser} /> : null}
      colorScheme={colorScheme} theme={theme} locale={locale} language={language} platform={initial.platform || 'darwin'} reporter={reporter} sync={sync} chat={chat} />
  </Frame>;
}
