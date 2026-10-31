import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createCrashReporter, type CadPageCrash } from '@text-to-cad/core/client';
import { version } from '../package.json';
import Connection from './Connection';
import Notice, { noticeTranslator } from './Notice';
import { createBridge, type HostContext, type ToolResult } from './host/bridge';
import { createChannel, declaresServerTools } from './host/channel';
import { readPresentation } from './host/presentation';
import { createServer, PROTOCOL, readLaunch, toolText, type Launch } from './host/server';
import { createTunnelClient, createTunnelFetch } from './host/tunnel';
import './styles.css';

// The page's crashes -- an error nothing caught, or one a view's boundary caught -- told to the CAD
// app's server for its telemetry (`cadgen/analytics.py`), each once a page and never its message.
// There is no way to the server until the host has answered (`start`): until then they wait. A frame
// names its chunk, which the page's loader made a blob URL of and kept which is which (vite.config.mjs).
const waiting: CadPageCrash[] = [];
let sendCrash = (crash: CadPageCrash) => { waiting.push(crash); };
const chunkOf = (url: string) => (globalThis as { __cadChunks?: Record<string, string> }).__cadChunks?.[url] ?? '<?>';
const reportCrash = createCrashReporter(crash => sendCrash(crash), { fileOf: chunkOf });
window.addEventListener('error', event => reportCrash(event.error));
window.addEventListener('unhandledrejection', event => reportCrash(event.reason));

// The notices this page shows itself, before a view knows the person's language setting: in the
// host's locale once it has said one, else the frame's browser languages.
let hostLocale: string | undefined;
const say = (key: string, params?: Record<string, unknown>) => noticeTranslator(hostLocale)(key, params);

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element, {
  onUncaughtError: error => {
    reportCrash(error);
    root.render(<Notice title={say('cad.stopped.title')} message={say('cad.stopped.message')} details={error instanceof Error ? `${error.name}: ${error.message}` : String(error)} t={say} />);
  },
  // Logged as React logs one, and counted: the page went on, with the view's "could not display".
  onCaughtError: (error, info) => { console.error(error, info.componentStack); reportCrash(error, { handled: true }); },
});
// The shell that loaded this page takes it down to load the engine's next release in its place (an update).
globalThis.__cadApp = { unmount: () => root.unmount() };

function applyTheme(context: HostContext) {
  const dark = context.theme === 'dark';
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
}

async function start() {
  // Started by the shell a host keeps (`host/shell.ts`): the host greeted and the launch read already,
  // its bridge this page's. Else this page is the resource itself, and greets the host as a shell would.
  const shell = globalThis.__cadShell;
  const presentation = shell?.presentation ?? readPresentation();
  const bridge = shell?.bridge ?? createBridge(window.parent);
  bridge.onHostContext(applyTheme);
  bridge.onHostContext(context => { hostLocale = context.locale || hostLocale; });
  // What to show comes as the result of the tool that opened this view.
  const launched = shell ? Promise.resolve({ launch: shell.launch, result: shell.result }) : new Promise<{ launch: Launch; result: ToolResult }>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(say('cad.nothingToShow'))), 30_000);
    const stop = bridge.onToolResult(result => {
      const launch = readLaunch(result);
      if (!launch && !result.isError) return;
      clearTimeout(timer);
      stop();
      if (launch) resolve({ launch, result }); else reject(new Error(toolText(result, say('cad.couldNotOpen'))));
    });
  });
  try {
    if (shell) applyTheme(bridge.hostContext);
    else await bridge.initialize({ name: 'CAD', version }, presentation === 'inline' ? { displayModes: ['inline', 'fullscreen'] } : undefined);
    hostLocale = bridge.hostContext.locale || hostLocale;
    // The page starts on its launch alone: the launch carries what the server is (its protocol,
    // version and platform). One from another build -- a tab the host restored after an update, a
    // past chat's card -- says so: this page reads only its own protocol's.
    const { launch, result } = await launched;
    if (launch.protocol !== PROTOCOL) {
      root.render(<Notice title={say('cad.updated.title')} message={say('cad.updated.message')} t={say} details={`view ${PROTOCOL} · launch ${launch.protocol}${launch.version ? ` (${launch.version})` : ''}`} />);
      return;
    }
    const token = result._meta?.['dev.texttocad/httpToken'];
    if (typeof token !== 'string' || !token) throw new Error(say('cad.noCapability'));
    // Whether the host carries this page's calls to CAD's server: what it declared, until a call says
    // (`host/channel.ts`). A host that refuses them all gets the CAD Viewer's page instead.
    const channel = createChannel(declaresServerTools(bridge.hostCapabilities));
    const server = createServer(bridge, token, channel);
    const reporting = createTunnelClient(createTunnelFetch(server), { pollIntervalMs: 0 });
    sendCrash = crash => reporting.reportActivity({ crash });
    waiting.splice(0).forEach(sendCrash);
    root.render(<StrictMode><Connection bridge={bridge} server={server} channel={channel} launch={launch} presentation={presentation} /></StrictMode>);
  } catch (error) {
    root.render(<Notice title={say('cad.couldNotOpenTitle')} message={error instanceof Error ? error.message : String(error)} details={`CAD ${version}`} t={say} />);
  }
}

if (window.parent === window) root.render(<Notice title="CAD" message={say('cad.outsideAgent')} t={say} />);
else void start();
