import { reaction } from 'mobx';
import { describe, expect, it } from 'vitest';
import { createMobxLogStore } from './mobx-log-store';
import { createImmutableMobxStore, createReactiveMobxStore } from './mobx-store';

describe('createImmutableMobxStore', () => {
  it('tracks reset and patch updates through MobX reactions', () => {
    const store = createImmutableMobxStore<{ count: number }>();
    store.reset({ count: 1 });

    const seen: number[] = [];
    const dispose = reaction(
      () => store.current().count,
      (count) => seen.push(count),
      { fireImmediately: true }
    );

    store.apply([{ op: 'replace', path: ['count'], value: 2 }]);

    expect(seen).toEqual([1, 2]);
    expect(store.serialize()).toEqual({ count: 2 });
    dispose();
  });
});

describe('createReactiveMobxStore', () => {
  it('only notifies reactions for touched observable paths', () => {
    const store = createReactiveMobxStore<{ left: { count: number }; right: { count: number } }>();
    store.reset({ left: { count: 1 }, right: { count: 10 } });

    const seen: number[] = [];
    const dispose = reaction(
      () => store.current().left.count,
      (count) => seen.push(count),
      { fireImmediately: true }
    );

    store.apply([{ op: 'replace', path: ['right', 'count'], value: 11 }]);
    store.apply([{ op: 'replace', path: ['left', 'count'], value: 2 }]);

    expect(seen).toEqual([1, 2]);
    expect(store.serialize()).toEqual({ left: { count: 2 }, right: { count: 11 } });
    dispose();
  });

  it('handles root replacement', () => {
    const store = createReactiveMobxStore<{ count: number }>();
    store.reset({ count: 1 });

    store.apply([{ op: 'replace', path: [], value: { count: 2 } }]);

    expect(store.current().count).toBe(2);
    expect(store.serialize()).toEqual({ count: 2 });
  });
});

describe('createMobxLogStore', () => {
  it('tracks reset and append updates through MobX reactions', () => {
    const store = createMobxLogStore();
    store.reset({ baseOffset: 0, text: 'seed', truncated: false });

    const seen: string[] = [];
    const dispose = reaction(
      () => store.text(),
      (text) => seen.push(text),
      { fireImmediately: true }
    );

    store.append('\nnext');

    expect(seen).toEqual(['seed', 'seed\nnext']);
    dispose();
  });
});
