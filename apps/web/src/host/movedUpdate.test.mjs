import assert from 'node:assert/strict';
import test from 'node:test';
import { movedPage } from './movedUpdate.js';

test('an update whose server stays sends the page to the same document on the new server, carrying its link', () => {
  const moved = { state: 'moved', target: '0.11.12', address: 'http://127.0.0.1:3246', link: '1999.sig' };
  assert.equal(movedPage(moved, { pathname: '/0f6c2d3e', hash: '#part' }), 'http://127.0.0.1:3246/0f6c2d3e?token=1999.sig#part');
  assert.equal(movedPage(moved, { pathname: '/' }), 'http://127.0.0.1:3246/?token=1999.sig', 'the home stays the home');
});

test('an update that names nowhere to go, or nowhere a page can go, leaves the page where it is', () => {
  for (const update of [null, { state: 'moved', address: null, link: 'x' }, { state: 'moved', address: 'http://127.0.0.1:3246' },
    { state: 'moved', address: 'javascript:alert(1)', link: 'x' }, { state: 'moved', address: 'not a url', link: 'x' }]) {
    assert.equal(movedPage(update, { pathname: '/' }), null, JSON.stringify(update));
  }
});
