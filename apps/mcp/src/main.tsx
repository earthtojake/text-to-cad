import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { createCrashReporter, type CadPageCrash } from '@text-to-cad/core/client';
import { installTessellationLadder } from '@text-to-cad/core/lib/surf/lodPolicy.js';
import { version } from '../package.json';
import App from './App';
import Notice from './Notice';
import { createBridge, type HostContext } from './host/bridge';
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

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element, {
  onUncaughtError: error => {
    reportCrash(error);
    root.render(<Notice title="CAD stopped" message="Something went wrong in this view. Close the tab and open CAD again." details={error instanceof Error ? `${error.name}: ${error.message}` : String(error)} />);
  },
  // Logged as React logs one, and counted: the page went on, with the view's "could not display".
  onCaughtError: (error, info) => { console.error(error, info.componentStack); reportCrash(error, { handled: true }); },
});

function applyTheme(context: HostContext) {
  const dark = context.theme === 'dark';
  document.documentElement.classList.toggle('dark', dark);
  document.documentElement.style.colorScheme = dark ? 'dark' : 'light';
}

async function start() {
  const presentation = readPresentation();
  const bridge = createBridge(window.parent);
  bridge.onHostContext(applyTheme);
  const server = createServer(bridge);
  // What to show comes as the result of the tool that opened this view.
  const launched = new Promise<Launch>((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('CAD did not receive anything to show. Close this tab and open CAD again.')), 30_000);
    const stop = bridge.onToolResult(result => {
      const launch = readLaunch(result);
      if (!launch && !result.isError) return;
      clearTimeout(timer);
      stop();
      if (launch) resolve(launch); else reject(new Error(toolText(result, 'CAD could not open.')));
    });
  });
  try {
    await bridge.initialize({ name: 'CAD', version }, presentation === 'inline' ? { displayModes: ['inline', 'fullscreen'] } : undefined);
    const reporting = createTunnelClient(createTunnelFetch(server), { pollIntervalMs: 0 });
    sendCrash = crash => reporting.reportActivity({ crash });
    waiting.splice(0).forEach(sendCrash);
    // The page starts on its launch alone: the launch carries what the server is (its protocol,
    // version and platform). One from another build -- a tab the host restored after an update, a
    // past chat's card -- says so: this page reads only its own protocol's.
    const launch = await launched;
    if (launch.protocol !== PROTOCOL) {
      root.render(<Notice title="CAD was updated" message="Close this tab and open CAD again to use the new version." details={`view ${PROTOCOL} · launch ${launch.protocol}${launch.version ? ` (${launch.version})` : ''}`} />);
      return;
    }
    // The display tessellation ladder is cadgen's: the launch says it, the page draws by it.
    installTessellationLadder(launch.tessellation);
    root.render(<StrictMode><App bridge={bridge} server={server} launch={launch} presentation={presentation} /></StrictMode>);
  } catch (error) {
    root.render(<Notice title="CAD could not open" message={error instanceof Error ? error.message : String(error)} details={`CAD ${version}`} />);
  }
}

if (window.parent === window) root.render(<Notice title="CAD" message="This page runs inside an agent app. Install the CAD plugin to use it." />);
else void start();
