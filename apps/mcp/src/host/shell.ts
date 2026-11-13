/**
 * The CAD app as a host keeps it: a small page that loads the CAD app the engine serves, so a page a
 * host cached, or kept open across an update, runs the engine's release, not its own.
 *
 * Hosts may keep a UI resource by its URI (OpenAI's guidance makes the URI the cache key; Claude
 * Desktop keeps a thread's page until it restarts), so the resource is this shell, and the app is
 * the engine's (`GET /app`: the app's code as one module, `cad_server/mcp/ui.py`). The shell
 * greets the host and waits for the launch, as the app did (`host/bridge.ts`), then reads the app
 * through the call the host carries back to CAD's server (`cad_http`, in parts as the tunnel sends
 * long bodies), or, where the host carries no call, from the engine directly with the launch's link
 * (`host/direct.ts`'s way); imports it, and hands it what it greeted: `globalThis.__cadShell` (its
 * bridge, the launch and its result), which the app starts on (`main.tsx`). After an update the app
 * asks the shell to load the engine's app again (`reload`), in place.
 *
 * Where the host carries none of the card's calls and the engine cannot be read from the card either
 * (the Claude app's Code tab, which refuses a card's calls and keeps it off this machine's loopback),
 * the app cannot be loaded, so the shell says what the app's own notice says (`unconnected`): this
 * chat cannot connect to CAD's engine, and the browser page of what it was to show.
 */
import { resolveLocale } from '@cad/ui/i18n/locale';
import words from 'virtual:cad-shell-words';
import { version } from '../../package.json';
import { createBridge, HostError, type Bridge, type ToolResult } from './bridge';
import { declaresOpenLinks } from './channel';
import { readPresentation, type Presentation } from './presentation';
import { readLaunch, toolText, type Launch, type Refusal } from './server';
import noticeCss from '../notice.css?inline';
import { appCapability } from './capability';
import { OPEN_IN_VIEWER, noticeHeight, refusalOf, unreachableKey, viewerPage } from './unreachable.js';

/** The engine's route that serves the CAD app's code (`cad_server/viewer/http_app.py`). */
export const APP_ROUTE = '/app';
/** The origin a `cad_http` request is spelled on (`host/tunnel.ts`'s `TUNNEL_ORIGIN`): the server reads its path alone. */
const TUNNEL_ORIGIN = 'http://cad.invalid';
/** The most body one `cad_http` reply carries (`host/tunnel.ts`'s `TUNNEL_REPLY_MAX_BYTES`). */
const PART_BYTES = 4 * 1024 * 1024;

export interface CadShell {
  bridge: ReturnType<typeof createBridge>;
  presentation: Presentation;
  launch: Launch;
  result: ToolResult;
  /** The engine's CAD app loaded again, in place of the one running (`globalThis.__cadApp`): after an update, the new release's. */
  reload(): Promise<void>;
}

declare global {
  // eslint-disable-next-line no-var
  var __cadShell: CadShell | undefined;
  // eslint-disable-next-line no-var
  var __cadApp: { unmount(): void } | undefined;
}

interface Reply { status: number; headers: Record<string, string>; body: string; encoding?: string }

function bytesOf(text: string): Uint8Array<ArrayBuffer> {
  const binary = atob(text || '');
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
  return bytes;
}

async function bodyOf(reply: Reply): Promise<Uint8Array<ArrayBuffer>> {
  const bytes = bytesOf(reply.body);
  if (reply.encoding === undefined) return bytes;
  if (reply.encoding !== 'gzip') throw new TypeError(`cad_http answered in an encoding this page cannot read: ${reply.encoding}`);
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** The CAD app's code through the call the host carries to CAD's server: its first part, then the rest a range at a time. */
export async function viaTunnel(bridge: Pick<CadShell['bridge'], 'callTool'>, token: string): Promise<string> {
  const ask = async (range: string, etag?: string): Promise<Reply> => {
    const headers: Record<string, string> = { 'x-cad-app': token, range, ...(etag ? { 'if-range': etag } : {}) };
    const result = await bridge.callTool('cad_http', { method: 'GET', url: `${TUNNEL_ORIGIN}${APP_ROUTE}`, headers, body: '' },
      { timeoutMs: 120_000 });
    // CAD's server refused the shell's capability (none, or one from before CAD restarted): it cannot connect.
    const refused = refusalOf(result);
    if (refused) throw new Unconnected(refused);
    if (result.isError) throw new Error(toolText(result, 'CAD could not load its app.'));
    return result.structuredContent as unknown as Reply;
  };
  const first = await ask(`bytes=0-${PART_BYTES - 1}`);
  if (first.status === 200) return new TextDecoder().decode(await bodyOf(first));
  const part = /^bytes (\d+)-(\d+)\/(\d+)$/.exec(first.headers?.['content-range'] || '');
  if (first.status !== 206 || !part) throw new Error(`CAD could not load its app (HTTP ${first.status}).`);
  const length = Number(part[3]);
  const parts = [await bodyOf(first)];
  let offset = parts[0].byteLength;
  while (offset < length) {
    const next = await ask(`bytes=${offset}-${Math.min(length, offset + PART_BYTES) - 1}`, first.headers.etag);
    if (next.status !== 206) throw new Error('CAD could not load its app: it changed while it was read.');
    const bytes = await bodyOf(next);
    parts.push(bytes);
    offset += bytes.byteLength;
  }
  const whole = new Uint8Array(offset);
  let at = 0;
  for (const bytes of parts) { whole.set(bytes, at); at += bytes.byteLength; }
  return new TextDecoder().decode(whole);
}

/**
 * The card's chat carries none of its calls to CAD's server, and the engine could not be read from the
 * card either: its launch gave no way to it, its sandbox, the host's network rules or local network
 * access refused the request, or the engine refused the link. The shell then says so (`unconnected`).
 */
export class Unconnected extends Error {
  /** Where CAD's server answered and refused the card's capability, why (`host/unreachable.js`'s `refusalOf`). */
  readonly refused: Refusal | null;
  constructor(refused: Refusal | null = null) {
    super('This chat cannot connect to CAD\'s engine.');
    this.name = 'Unconnected';
    this.refused = refused;
  }
}

/** The CAD app's code from the engine directly, with the launch's link: a host that carries no call. */
export async function viaEngine(launch: Pick<Launch, 'browser' | 'engine'>, fetchImpl: typeof fetch = globalThis.fetch): Promise<string> {
  let origin: string, link: string | null;
  try {
    const page = new URL(String(launch.browser));
    origin = new URL(String(launch.engine)).origin;
    link = page.origin === origin ? page.searchParams.get('token') : null;
  } catch {
    link = null;
    origin = '';
  }
  if (!link) throw new Unconnected();
  let response: Response;
  try {
    response = await fetchImpl(`${origin}${APP_ROUTE}`, { headers: { authorization: `Bearer ${link}` }, credentials: 'omit',
      cache: 'no-store', referrerPolicy: 'no-referrer' });
  } catch {
    throw new Unconnected(); // the fetch's own "Failed to fetch": blocked before it reached the engine
  }
  if (!response.ok) throw new Unconnected();
  return response.text();
}

/** The engine's CAD app, read and imported: its module starts it on `globalThis.__cadShell`. */
export async function loadApp(shell: Pick<CadShell, 'bridge' | 'launch' | 'result'>,
  read: { tunnel?: typeof viaTunnel; engine?: typeof viaEngine } = {}): Promise<void> {
  const token = appCapability(shell.result, shell.bridge.hostContext);
  let code: string;
  try {
    code = await (read.tunnel ?? viaTunnel)(shell.bridge, token ?? '');
  } catch (error) {
    // A host that refuses the call itself carries none: the engine directly, as the app does then.
    if (!(error instanceof HostError && error.kind === 'refused')) throw error;
    code = await (read.engine ?? viaEngine)(shell.launch);
  }
  const url = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }));
  await import(/* @vite-ignore */ url);
}

/** The notice's look (`notice.css`), once in the page: the shell has no stylesheet of its own. */
function styleNotices(): void {
  if (document.getElementById('cad-notice-style')) return;
  const style = document.createElement('style');
  style.id = 'cad-notice-style';
  style.textContent = noticeCss;
  document.head.append(style);
}

/**
 * Show `notice` (a `.cad-notice`, `notice.css`) as the whole card: inline, the card as tall as it is at
 * the card's width, told to the host again whenever its words reflow.
 */
function showNotice(notice: HTMLElement, presentation: Presentation | null, bridge?: Pick<Bridge, 'notify'>,
  root: HTMLElement | null = document.getElementById('root')): void {
  if (!root) return;
  styleNotices();
  root.replaceChildren(notice);
  if (presentation !== 'inline' || !bridge) return;
  let told = 0;
  const tell = () => {
    const height = noticeHeight(notice);
    if (height !== told) bridge.notify('ui/notifications/size-changed', { height: told = height });
  };
  tell();
  if (typeof ResizeObserver === 'function') new ResizeObserver(tell).observe(notice.firstElementChild ?? notice);
}

/** A notice of one line: the shell's own words, or why the app could not be loaded. */
export function say(message: string, bridge?: Pick<Bridge, 'notify'>, presentation: Presentation | null = null) {
  const notice = document.createElement('div');
  notice.className = 'cad-notice';
  notice.setAttribute('role', 'alert');
  const body = document.createElement('div');
  body.className = 'cad-notice-body';
  const line = document.createElement('p');
  line.className = 'cad-notice-line';
  line.textContent = message;
  body.append(line);
  notice.append(body);
  showNotice(notice, presentation, bridge);
}

/**
 * What the card shows where it cannot connect (`Unconnected`), as the app's notice shows it
 * (`Notice.tsx`'s `Unreachable`): the line in the host's language (its locale, else the frame's
 * languages), and the viewer's page of what the card was to show, opened through the host where it
 * opens links (`ui/open-link`), else as an ordinary link in a new window. Inline, the card is the
 * notice's height.
 */
export function unconnected(bridge: Pick<Bridge, 'hostContext' | 'hostCapabilities' | 'request' | 'notify'>, launch: Launch,
  presentation: Presentation, root: HTMLElement | null = document.getElementById('root'), refused: Refusal | null = null): void {
  if (!root) return;
  const languages = typeof navigator === 'undefined' ? [] : (navigator.languages ?? [navigator.language]);
  const said = words[resolveLocale([bridge.hostContext.locale, ...languages])] ?? words.en;
  const t = (key: string) => said[key] ?? words.en[key] ?? key;
  const page = viewerPage(launch);
  document.documentElement.style.colorScheme = bridge.hostContext.theme === 'dark' ? 'dark' : 'light';
  // The app's notice (`Notice.tsx`'s `Unreachable`), element for element, in the same look (`notice.css`).
  const notice = document.createElement('div');
  notice.className = 'cad-notice';
  notice.setAttribute('role', 'alert');
  notice.dataset.cadUnreachable = '';
  const body = document.createElement('div');
  body.className = 'cad-notice-body';
  const line = document.createElement('p');
  line.className = 'cad-notice-line';
  line.textContent = t(unreachableKey(Boolean(page), launch.page === 'viewer', refused));
  body.append(line);
  if (page) {
    const open = document.createElement('a');
    Object.assign(open, { href: page, target: '_blank', rel: 'noopener noreferrer', textContent: t(OPEN_IN_VIEWER), className: 'cad-notice-button' });
    if (declaresOpenLinks(bridge.hostCapabilities)) {
      open.addEventListener('click', event => {
        event.preventDefault();
        void bridge.request('ui/open-link', { url: page }).catch(() => { window.open(page, '_blank', 'noopener,noreferrer'); });
      });
    }
    body.append(open);
  }
  notice.append(body);
  showNotice(notice, presentation, bridge, root);
}

export async function start() {
  const presentation = readPresentation();
  const bridge = createBridge(window.parent);
  // What to show comes as the result of the tool that opened this view.
  const launched = new Promise<{ launch: Launch; result: ToolResult }>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('CAD was given nothing to show.')), 30_000);
    const stop = bridge.onToolResult(result => {
      const launch = readLaunch(result);
      if (!launch && !result.isError) return;
      clearTimeout(timer);
      stop();
      if (launch) resolve({ launch, result }); else reject(new Error(toolText(result, 'CAD could not open that.')));
    });
  });
  await bridge.initialize({ name: 'CAD', version }, presentation === 'inline' ? { displayModes: ['inline', 'fullscreen'] } : undefined);
  let opened: { launch: Launch; result: ToolResult };
  try {
    opened = await launched;
  } catch (error) {
    say(error instanceof Error ? error.message : String(error), bridge, presentation); // the tool's own failure, said in the notice
    return;
  }
  const { launch, result } = opened;
  const shell: CadShell = {
    bridge, presentation, launch, result,
    async reload() {
      globalThis.__cadApp?.unmount();
      globalThis.__cadApp = undefined;
      document.getElementById('root')?.replaceChildren();
      await loadApp(shell);
    },
  };
  globalThis.__cadShell = shell;
  try {
    await loadApp(shell);
  } catch (error) {
    if (!(error instanceof Unconnected)) {
      say(error instanceof Error ? error.message : String(error), bridge, presentation);
      return;
    }
    unconnected(bridge, launch, presentation, undefined, error.refused);
  }
}

