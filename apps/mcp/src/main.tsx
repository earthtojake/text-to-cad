import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { version } from '../package.json';
import App from './App';
import Notice from './Notice';
import { createBridge, type HostContext } from './host/bridge';
import { readPresentation } from './host/presentation';
import { createServer, PROTOCOL, readLaunch, toolText, type Launch } from './host/server';
import './styles.css';

const element = document.getElementById('root');
if (!element) throw new Error('Missing #root mount point.');
const root = createRoot(element, {
  onUncaughtError: error => root.render(<Notice title="CAD stopped" message="Something went wrong in this view. Close the tab and open CAD again." details={error instanceof Error ? `${error.name}: ${error.message}` : String(error)} />),
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
    // The page starts on its launch alone: the launch carries what the server is (its protocol,
    // version and platform). One from another build -- a tab the host restored after an update, a
    // past chat's card -- says so: this page reads only its own protocol's.
    const launch = await launched;
    if (launch.protocol !== PROTOCOL) {
      root.render(<Notice title="CAD was updated" message="Close this tab and open CAD again to use the new version." details={`view ${PROTOCOL} · launch ${launch.protocol}${launch.version ? ` (${launch.version})` : ''}`} />);
      return;
    }
    root.render(<StrictMode><App bridge={bridge} server={server} launch={launch} presentation={presentation} /></StrictMode>);
  } catch (error) {
    root.render(<Notice title="CAD could not open" message={error instanceof Error ? error.message : String(error)} details={`CAD ${version}`} />);
  }
}

if (window.parent === window) root.render(<Notice title="CAD" message="This page runs inside an agent app. Install the CAD plugin to use it." />);
else void start();
