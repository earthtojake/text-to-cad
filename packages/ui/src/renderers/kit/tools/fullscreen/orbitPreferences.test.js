import assert from 'node:assert/strict';
import test from 'node:test';
import { normalizeOrbit, readOrbit, writeOrbit } from './orbitPreferences.js';

test('global orbit preserves stopped and fractional speeds and bounds corrupt preferences', () => {
  let value = null;
  const storage = { getItem: () => value, setItem: (_key, next) => { value = next; } };
  for (const speed of [0, 0.05, 1.37, 5]) {
    writeOrbit(storage, { speed });
    assert.deepEqual(readOrbit(storage), { speed });
  }
  assert.deepEqual(normalizeOrbit({ speed: -1 }), { speed: 0 });
  assert.deepEqual(normalizeOrbit({ speed: 100 }), { speed: 5 });
  for (const speed of [null, 'fast', Infinity, NaN]) assert.deepEqual(normalizeOrbit({ speed }), { speed: 1 });
  value = '{broken';
  assert.deepEqual(readOrbit(storage), { speed: 1 });
  const blocked = { getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } };
  assert.deepEqual(readOrbit(blocked), { speed: 1 });
  assert.doesNotThrow(() => writeOrbit(blocked, { speed: 1.37 }));
});
