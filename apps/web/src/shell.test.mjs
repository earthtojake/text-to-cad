import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

// The page is translated into its locales by its own strings. A browser's page translation (Chrome's wraps
// each text node in <font> elements) moves and removes nodes React owns, and React's next commit throws
// NotFoundError and can leave the page blank. The shell asks the browser not to translate it; this holds that
// the shell asks (it cannot hold that a browser obeys).
test('the page asks browsers not to translate it', () => {
  const shell = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const root = shell.match(/<html\b[^>]*>/u)?.[0] ?? '';
  assert.match(root, /\btranslate="no"/u);
  assert.match(root, /\bclass="notranslate"/u);
  assert.match(shell, /<meta name="google" content="notranslate"\s*\/?>/u);
});

// Before the script runs, the page draws the navbar's bar (`index.html`), which the app's own navbar then replaces
// where it stood: its height, a phone's under the viewer's breakpoint, its colour and its border are the navbar's.
test("the page's bar before its script is the navbar's", () => {
  const shell = readFileSync(new URL('../index.html', import.meta.url), 'utf8');
  const ui = path => readFileSync(new URL(`../../../packages/ui/src/${path}`, import.meta.url), 'utf8');
  assert.match(shell, /<div id="root"><div aria-hidden="true" data-boot-navbar=""><\/div><\/div>/u);
  const bar = shell.match(/\[data-boot-navbar\] \{([^}]*)\}/u)?.[1] ?? '';
  assert.match(bar, /box-sizing: border-box; height: 40px; border-bottom: 1px solid var\(--border\); background: var\(--sidebar\);/u);
  const phone = shell.match(/@media \(max-width: ([\d.]+)px\) \{ \[data-boot-navbar\] \{ height: (\d+)px; \} \}/u);
  // The navbar: the control and 12px with its border inside (`border-b` in a border-box), on the chrome's colour: 40px
  // (a 28px control) and 48px (a phone's 36px) in a phone's view, a viewer under `VIEWER_MOBILE_BREAKPOINT` wide (the
  // page's whole width here).
  assert.match(ui('lib/navbarRow.js'), /NAVBAR_ROW_CLASS = "flex h-\[calc\(var\(--cad-control\)\+12px\)\] shrink-0 items-center gap-2 border-b /u);
  assert.match(ui('file-viewer/navigation/ViewerNavbar.jsx'), /cn\(NAVBAR_ROW_CLASS, "relative border-border bg-sidebar /u);
  const controls = [...ui('styles/globals.css').matchAll(/--cad-control: (\d+)px;/gu)].map(([, px]) => Number(px) + 12);
  assert.deepEqual(controls, [40, 48]);
  const breakpoint = Number(ui('file-viewer/responsive.js').match(/VIEWER_MOBILE_BREAKPOINT = (\d+)/u)?.[1]);
  assert.deepEqual([Math.ceil(Number(phone?.[1])), phone?.[2]], [breakpoint, '48']);
});
