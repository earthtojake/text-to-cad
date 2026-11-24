// The CAD app as a Claude artifact (`host/artifact.ts`): reach CAD's server on this computer through the
// Claude app, open CAD, and start the engine's own app. Where it cannot (a browser, no server, no consent),
// the page says how to connect it.
import { createArtifactBridge, createReplayMcp, openCad, unreachable, type ArtifactMcp, type Recording } from './host/artifact';
import { loadApp, Unconnected, type CadShell } from './host/shell';

/** The server entry the Claude app needs, in its `claude_desktop_config.json`. */
const CONFIG = JSON.stringify({ mcpServers: { 'text-to-cad': {
  command: '/full/path/to/cad', args: ['mcp'], env: { CAD_MCP_PRESENTATION: 'artifact' },
} } }, null, 2);

const root = () => document.getElementById('root')!;

function element<K extends keyof HTMLElementTagNameMap>(tag: K, text?: string, className?: string): HTMLElementTagNameMap[K] {
  const made = document.createElement(tag);
  if (text !== undefined) made.textContent = text;
  if (className) made.className = className;
  return made;
}

/** A screen of the page's own, in place of the app: `.cad-artifact` (artifact.html's styles). */
function screen(...children: Node[]): HTMLElement {
  const page = element('div', undefined, 'cad-artifact');
  const body = element('div', undefined, 'cad-artifact-body');
  body.append(...children);
  page.append(body);
  return page;
}

/** A Copy button for `text`, which says when it copied. */
function copyButton(text: string, label = 'Copy'): HTMLButtonElement {
  const button = element('button', label);
  button.type = 'button';
  button.addEventListener('click', () => {
    navigator.clipboard.writeText(text).then(() => { button.textContent = 'Copied'; }, () => { button.textContent = 'Select and copy it'; });
    setTimeout(() => { button.textContent = label; }, 2000);
  });
  return button;
}

/** How to connect this page to CAD, and why it is not connected now. */
function setup(why: string | null): void {
  const install = element('li');
  const command = 'curl -fsSL https://texttocad.dev/install.sh | sh';
  install.append('Install text-to-cad, if you have not: ', element('code', command), ' (on Windows, see ');
  const guide = Object.assign(element('a', 'texttocad.dev'), { href: 'https://texttocad.dev', target: '_blank', rel: 'noopener noreferrer' });
  install.append(guide, ').');
  const config = element('li');
  const pre = element('pre');
  pre.append(element('code', CONFIG));
  config.append('In the Claude desktop app, open Settings, Developer, Edit Config, and add CAD\'s server to ',
    element('code', 'claude_desktop_config.json'), '. For ', element('code', 'command'), ', use the path ',
    element('code', 'command -v cad'), ' prints in a terminal.', pre);
  const row = element('div', undefined, 'cad-artifact-row');
  row.append(copyButton(CONFIG, 'Copy config'));
  config.append(row);
  const reopen = element('li', 'Quit and reopen Claude, then open this page in the Claude app. To keep it in its own window, choose Install as app from its Share menu.');
  const steps = element('ol');
  steps.append(install, config, reopen);
  const again = element('button', 'Try again');
  again.type = 'button';
  again.addEventListener('click', () => { location.reload(); });
  const actions = element('div', undefined, 'cad-artifact-row');
  actions.append(again);
  root().replaceChildren(screen(
    element('h1', 'Your CAD models, in Claude'),
    element('p', 'This page opens the models on your computer in cad\'s own viewer: turn them, pick faces and edges, try their parameters. It reaches cad through the Claude desktop app, so it works there, not in a browser.'),
    ...(why ? [element('p', `Not connected: ${why}`, 'muted')] : []),
    steps, actions,
  ));
}

/** A one-line notice that fades: what Send did. */
function toast(text: string): void {
  const note = element('div', text, 'cad-artifact-copied');
  note.setAttribute('role', 'status');
  document.body.append(note);
  setTimeout(() => note.remove(), 4000);
}

/** The message Send made, for the person to copy where the clipboard refused it. */
function showMessage(text: string): void {
  const dialog = element('div', undefined, 'cad-artifact-dialog');
  const area = element('textarea');
  area.value = text;
  area.readOnly = true;
  const close = element('button', 'Close');
  close.type = 'button';
  close.addEventListener('click', () => dialog.remove());
  const row = element('div', undefined, 'cad-artifact-row');
  row.append(copyButton(text), close);
  dialog.append(screen(element('p', 'Paste this into your agent\'s chat:'), area, row));
  document.body.append(dialog);
  area.select();
}

/** The artifact's `mcp` capability, or null where this view has none (a browser tab, a page opened elsewhere). */
async function capability(): Promise<ArtifactMcp | null> {
  const claude = (globalThis as { claude?: { use?: (name: string) => Promise<unknown> } }).claude;
  if (typeof claude?.use !== 'function') return null;
  try { return (await claude.use('mcp')) as ArtifactMcp | null; } catch { return null; }
}

/** The sample models published beside the page (`demo.json`, a `Recording`), or null where there are none. */
async function samples(): Promise<Recording | null> {
  try {
    const response = await fetch('demo.json');
    return response.ok ? ((await response.json()) as Recording) : null;
  } catch { return null; }
}

/** The pill over the samples: what they are, and the way to connect the person's own CAD. */
function samplesPill(why: string): void {
  const pill = element('button', 'Sample models · Open your own', 'cad-artifact-pill');
  pill.type = 'button';
  pill.addEventListener('click', () => { pill.remove(); setup(why); });
  document.body.append(pill);
}

/** Start the engine's app on `mcp`: CAD on this computer, or the samples' recording. Throws where CAD cannot open. */
async function run(mcp: ArtifactMcp): Promise<void> {
  const bridge = createArtifactBridge(mcp, {
    copy: async text => { await navigator.clipboard.writeText(text); toast('Copied. Paste it into your agent\'s chat.'); },
    show: showMessage,
  });
  const opened = await openCad(bridge);
  const shell: CadShell = { bridge, presentation: 'tabs', ...opened };
  globalThis.__cadShell = shell;
  await loadApp(shell);
}

async function start(): Promise<void> {
  const mcp = await capability();
  let why = 'this view cannot reach servers on this computer. Open it in the Claude desktop app.';
  if (mcp) {
    try { await run(mcp); return; } catch (error) {
      const message = error instanceof Error ? error.message : String(error);
      why = error instanceof Unconnected ? 'CAD\'s server refused this page. Reopen it to connect again.'
        : unreachable(error) ? `the Claude app has no CAD server for this page (${message}).` : message;
    }
  }
  // No CAD here: the samples, where the page has them, with the way to connect it over them.
  const recording = await samples();
  if (!recording) { setup(why); return; }
  try { await run(createReplayMcp(recording)); samplesPill(why); } catch { setup(why); }
}

void start();
