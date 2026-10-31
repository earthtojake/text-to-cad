import { useEffect, useState, useSyncExternalStore, type ReactNode } from 'react';
import App, { inlineHeight } from './App';
import type { Bridge } from './host/bridge';
import { declaresOpenLinks, type Channel } from './host/channel';
import { createDirectFetch, engineReach, probeEngine } from './host/direct';
import type { Presentation } from './host/presentation';
import { TUNNEL_ORIGIN } from './host/tunnel';
import type { Launch, Server } from './host/server';
import { Unreachable, noticeTranslator } from './Notice';

/**
 * How this card reaches the engine:
 *
 * - `tunnel`: through its host, each request a `cad_http` call -- every host that carries an app's
 *   calls, which a host declares (`serverTools`) or a tab host does whatever it declares (Codex);
 * - `checking`: a host that said nothing either way: one cheap call says, before anything is drawn;
 * - `probing`: the host refused a call before any came back (`host/channel.ts`): the card tries the
 *   engine directly over HTTP (`host/direct.ts`);
 * - `direct`: it answered, and the card runs over that;
 * - `none`: it did not: the card says so, and links the CAD Viewer's page instead (`Unreachable`).
 */
type Route = { kind: 'checking' | 'tunnel' | 'probing' | 'none' } | { kind: 'direct'; fetch: typeof fetch };

// A card that only says it cannot connect is as tall as its words, not a viewer's height.
const NOTICE_HEIGHT = 180;

/** Inline, the card's height, which the host is told: a viewer's while nothing is drawn yet (most often
 * the viewer comes next), the notice's for the notice. A tab is the page's full height. */
function Card({ bridge, inline, height, children }: { bridge: Bridge; inline: boolean; height: number; children?: ReactNode }) {
  useEffect(() => { if (inline) bridge.notify('ui/notifications/size-changed', { height }); }, [bridge, inline, height]);
  return <div className={inline ? 'overflow-hidden' : 'h-svh'} style={inline ? { height } : undefined}>{children}</div>;
}

/** The launch's page of the CAD Viewer, where the engine gave one. */
function pageOf(launch: Launch): string | null {
  try {
    return typeof launch.browser === 'string' ? new URL(launch.browser).href : null;
  } catch {
    return null;
  }
}

function Unconnected({ bridge, launch, inline }: { bridge: Bridge; launch: Launch; inline: boolean }) {
  // Through the host where it opens links; else the link opens as an ordinary one.
  const open = declaresOpenLinks(bridge.hostCapabilities)
    ? (url: string) => { void bridge.request('ui/open-link', { url }).catch(() => { window.open(url, '_blank', 'noopener,noreferrer'); }); return true; }
    : undefined;
  return <Card bridge={bridge} inline={inline} height={NOTICE_HEIGHT}>
    <Unreachable page={pageOf(launch)} model={launch.page === 'viewer'} open={open} t={noticeTranslator(bridge.hostContext.locale)} />
  </Card>;
}

export default function Connection({ bridge, server, channel, launch, presentation = 'tabs', fetchImpl = globalThis.fetch }: {
  bridge: Bridge; server: Server; channel: Channel; launch: Launch; presentation?: Presentation; fetchImpl?: typeof fetch;
}) {
  const state = useSyncExternalStore(channel.subscribe, () => channel.state, () => channel.state);
  const trusted = presentation === 'tabs' || state === 'open';
  const [route, setRoute] = useState<Route>(() => ({ kind: state === 'none' ? 'probing' : trusted ? 'tunnel' : 'checking' }));
  // A refusal before any call came back, whenever it comes: what was drawn goes, and the probe runs.
  useEffect(() => {
    if (state === 'none') setRoute(current => current.kind === 'tunnel' || current.kind === 'checking' ? { kind: 'probing' } : current);
  }, [state]);
  useEffect(() => {
    if (route.kind !== 'checking') return;
    let active = true;
    // What the engine is: the cheapest of its reads. Any answer, even a refusal of the engine's, is
    // a channel; a timeout is too (the view's own sync then says the plugin stopped).
    void server.http({ method: 'GET', url: `${TUNNEL_ORIGIN}/__cad/server`, headers: {}, body: '' })
      .catch(() => null)
      .then(() => { if (active && channel.state !== 'none') setRoute({ kind: 'tunnel' }); });
    return () => { active = false; };
  }, [route.kind, server, channel]);
  useEffect(() => {
    if (route.kind !== 'probing') return;
    let active = true;
    const reach = engineReach(launch);
    if (!reach) { setRoute({ kind: 'none' }); return; }
    void probeEngine(reach, fetchImpl).then(ok => {
      if (active) setRoute(ok ? { kind: 'direct', fetch: createDirectFetch(reach, fetchImpl) } : { kind: 'none' });
    });
    return () => { active = false; };
  }, [route.kind, launch, fetchImpl]);
  const inline = presentation === 'inline';
  if (route.kind === 'checking' || route.kind === 'probing') {
    return <Card bridge={bridge} inline={inline} height={inlineHeight(window.innerWidth, bridge.hostContext.containerDimensions?.maxHeight)}>
      <div data-cad-connecting="" />
    </Card>;
  }
  if (route.kind === 'none') return <Unconnected bridge={bridge} launch={launch} inline={inline} />;
  return <App bridge={bridge} server={server} launch={launch} presentation={presentation}
    direct={route.kind === 'direct' ? route.fetch : undefined} />;
}
