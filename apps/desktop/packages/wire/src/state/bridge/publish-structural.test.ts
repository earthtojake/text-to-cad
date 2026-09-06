import { createScope } from '@emdash/shared/concurrency';
import { describe, expect, it } from 'vitest';
import { cell, observe, snapshot } from '../core';
import { publishStructural } from './publish-structural';

describe('publishStructural', () => {
  it('preserves the current revision when the next value is structurally unchanged', () => {
    const scope = createScope();
    const source = cell({ nested: { count: 1 } });
    let notifications = 0;
    observe(
      source,
      () => {
        notifications += 1;
      },
      { scope }
    );
    notifications = 0;

    const before = snapshot(source);
    const revision = publishStructural(source, { nested: { count: 1 } });

    expect(revision.revision).toBe(before.revision);
    expect(snapshot(source).revision).toBe(before.revision);
    expect(notifications).toBe(0);
    void scope.dispose();
  });

  it('publishes structural changes through the cell', () => {
    const source = cell({ nested: { count: 1 }, label: 'one' });

    const revision = publishStructural(source, { nested: { count: 2 }, label: 'one' });

    expect(revision.revision).toBe(1);
    expect(snapshot(source).value).toEqual({ nested: { count: 2 }, label: 'one' });
  });
});
