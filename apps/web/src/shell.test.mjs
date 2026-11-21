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
