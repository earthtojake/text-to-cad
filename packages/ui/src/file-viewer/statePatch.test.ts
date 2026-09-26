import { expect, test } from 'vitest';
import { mergeChangedRecords } from './statePatch.js';

test('a view writes only the keys it changed, over whatever the host holds now', () => {
  // `b` changed elsewhere since this view read it, and `c` arrived: both survive this view's write.
  expect(mergeChangedRecords({ a: 'latest-a', b: 'new-b', c: 'new-c' }, { a: 'old-a', b: 'old-b' }, { a: 'changed-a', b: 'old-b' }))
    .toEqual({ a: 'changed-a', b: 'new-b', c: 'new-c' });
  // A key this view dropped is removed; one it never had stays.
  expect(mergeChangedRecords({ a: 'latest-a', b: 'new-b' }, { a: 'old-a' }, {})).toEqual({ b: 'new-b' });
  // Equal by value is unchanged, whatever the object identity.
  expect(mergeChangedRecords({ a: { x: 2 } }, { a: { x: 1 } }, { a: { x: 1 } })).toEqual({ a: { x: 2 } });
});
