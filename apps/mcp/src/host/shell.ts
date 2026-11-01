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
 */
import { version } from '../../package.json';
import { createBridge, HostError, type ToolResult } from './bridge';
import { readPresentation, type Presentation } from './presentation';
import { readLaunch, toolText, type Launch } from './server';

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
    const headers: Record<string, string> = { 'x-cadgen-app': token, range, ...(etag ? { 'if-range': etag } : {}) };
    const result = await bridge.callTool('cad_http', { method: 'GET', url: `${TUNNEL_ORIGIN}${APP_ROUTE}`, headers, body: '' },
      { timeoutMs: 120_000 });
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
  if (!link) throw new Error('This chat cannot reach the CAD engine.');
  const response = await fetchImpl(`${origin}${APP_ROUTE}`, { headers: { authorization: `Bearer ${link}` }, credentials: 'omit',
    cache: 'no-store', referrerPolicy: 'no-referrer' });
  if (!response.ok) throw new Error(`CAD could not load its app (HTTP ${response.status}).`);
  return response.text();
}

/** The engine's CAD app, read and imported: its module starts it on `globalThis.__cadShell`. */
export async function loadApp(shell: Pick<CadShell, 'bridge' | 'launch' | 'result'>,
  read: { tunnel?: typeof viaTunnel; engine?: typeof viaEngine } = {}): Promise<void> {
  const token = shell.result._meta?.['dev.texttocad/httpToken'];
  let code: string;
  try {
    code = await (read.tunnel ?? viaTunnel)(shell.bridge, typeof token === 'string' ? token : '');
  } catch (error) {
    // A host that refuses the call itself carries none: the engine directly, as the app does then.
    if (!(error instanceof HostError && error.kind === 'refused')) throw error;
    code = await (read.engine ?? viaEngine)(shell.launch);
  }
  const url = URL.createObjectURL(new Blob([code], { type: 'text/javascript' }));
  await import(/* @vite-ignore */ url);
}

export function say(message: string) {
  const root = document.getElementById('root');
  if (root) root.textContent = message;
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
  const { launch, result } = await launched;
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
  await loadApp(shell);
}

