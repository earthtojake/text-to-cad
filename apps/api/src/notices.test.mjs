import assert from 'node:assert/strict';
import { test } from 'node:test';

import { NOTICES_MAX, noticesOf } from './notices.mjs';

// Notices: `CAD_NOTICES`, the words the project shows to every cad older than a release (README, "Posting a notice").
const NOTICE = { id: 'install-moved', below: '0.12.4', text: 'cad now installs another way: see the install guide.',
  url: 'https://texttocad.dev/docs/install' };
const noticesFrom = (value, logged = []) => noticesOf({ CAD_NOTICES: typeof value === 'string' ? value : JSON.stringify(value) },
  (...line) => logged.push(line.join(' ')));

test('no CAD_NOTICES, or a blank one, posts no notice and logs nothing', () => {
  const logged = [];
  for (const env of [{}, { CAD_NOTICES: '' }, { CAD_NOTICES: '  \n' }, undefined, null]) {
    assert.deepEqual(noticesOf(env, (...line) => logged.push(line.join(' '))), []);
  }
  assert.deepEqual(logged, []);
});

test('a valid notice is kept with its own keys alone, in order, and logged by id', () => {
  const logged = [];
  const second = { id: 'a-2', below: '1.0.0', text: 'Plain words, at most 240 of them.', extra: 'left out' };
  assert.deepEqual(noticesFrom([NOTICE, second, { ...NOTICE, url: 'https://github.com/earthtojake/text-to-cad/issues/1', id: 'b' }], logged), [
    NOTICE, { id: 'a-2', below: '1.0.0', text: 'Plain words, at most 240 of them.' },
    { ...NOTICE, id: 'b', url: 'https://github.com/earthtojake/text-to-cad/issues/1' }]);
  assert.deepEqual(logged, ['notices: install-moved (below 0.12.4), a-2 (below 1.0.0), b (below 0.12.4)']);
  // The longest text, by characters as Python counts them (an emoji is one), is kept.
  assert.equal(noticesFrom([{ ...NOTICE, text: '\u{1F527}'.repeat(240) }]).length, 1);
  for (const url of ['https://texttocad.dev', 'https://texttocad.dev/', 'https://texttocad.dev/docs?x=1#y', 'https://github.com/earthtojake/text-to-cad']) {
    assert.equal(noticesFrom([{ ...NOTICE, url }]).length, 1, url);
  }
});

test('an entry that breaks a rule is dropped and logged by its rule; the rest are kept', () => {
  const bad = [
    [{ ...NOTICE, id: 'Install' }, 'id'], [{ ...NOTICE, id: '' }, 'id'], [{ ...NOTICE, id: 'a'.repeat(41) }, 'id'], [{ ...NOTICE, id: 7 }, 'id'],
    [{ ...NOTICE, below: '0.12' }, 'below'], [{ ...NOTICE, below: 'v0.12.4' }, 'below'], [{ ...NOTICE, below: '0.12.4rc1' }, 'below'],
    [{ ...NOTICE, text: 'x'.repeat(241) }, 'text'], [{ ...NOTICE, text: 'two\nlines' }, 'text'], [{ ...NOTICE, text: 'a\rb' }, 'text'],
    [{ ...NOTICE, text: 'a\u2028b' }, 'text'], [{ ...NOTICE, text: 'tab\there' }, 'text'], [{ ...NOTICE, text: 'bell\u0007' }, 'text'],
    [{ ...NOTICE, text: '' }, 'text'], [{ ...NOTICE, text: '   ' }, 'text'], [{ ...NOTICE, text: null }, 'text'],
    [{ ...NOTICE, url: 'http://texttocad.dev/docs' }, 'url'], [{ ...NOTICE, url: 'https://example.com/' }, 'url'],
    [{ ...NOTICE, url: 'https://texttocad.dev.example.com/' }, 'url'], [{ ...NOTICE, url: 'https://texttocad.dev@example.com/' }, 'url'],
    [{ ...NOTICE, url: 'https://www.texttocad.dev/' }, 'url'], [{ ...NOTICE, url: 'https://github.com/earthtojake/text-to-cad-x' }, 'url'],
    [{ ...NOTICE, url: 'https://github.com/someone/text-to-cad' }, 'url'], [{ ...NOTICE, url: 'javascript:alert(1)' }, 'url'],
    [{ ...NOTICE, url: 'https://texttocad.dev/a b' }, 'url'], [{ ...NOTICE, url: null }, 'url'],
    [{ ...NOTICE, url: `https://texttocad.dev/${'a'.repeat(500)}` }, 'url'], ['words', 'not an object'], [null, 'not an object'],
    [[NOTICE], 'not an object'],
  ];
  for (const [entry, rule] of bad) {
    const logged = [];
    assert.deepEqual(noticesFrom([entry, { ...NOTICE, id: 'kept' }], logged), [{ ...NOTICE, id: 'kept' }], JSON.stringify(entry));
    assert.deepEqual(logged, [`notices: CAD_NOTICES entry 0 dropped: ${rule}`, 'notices: kept (below 0.12.4)']);
  }
  // An id named twice: the first stands. More than the most: the rest are dropped.
  const logged = [];
  assert.deepEqual(noticesFrom([NOTICE, { ...NOTICE, text: 'again' }], logged), [NOTICE]);
  assert.equal(logged[0], 'notices: CAD_NOTICES entry 1 dropped: id named twice');
  const many = Array.from({ length: NOTICES_MAX + 2 }, (_, at) => ({ ...NOTICE, id: `n${at}` }));
  assert.equal(noticesFrom(many).length, NOTICES_MAX);
});

test('CAD_NOTICES that is not JSON, or not a list, posts none and says so', () => {
  for (const [value, said] of [['[{"id": ', 'not JSON'], ['{"id": "a"}', 'not a list'], ['"words"', 'not a list'], ['null', 'not a list']]) {
    const logged = [];
    assert.deepEqual(noticesFrom(value, logged), []);
    assert.deepEqual(logged, [`notices: CAD_NOTICES is ${said}`]);
  }
});
