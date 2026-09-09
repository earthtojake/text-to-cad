import { createScope } from '@emdash/shared/concurrency';
import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import { query } from '../query';
import { settleAsync } from '../testing';
import { family } from './family';
import { cell, observe, snapshot } from './index';

describe('state family', () => {
  it('never disposes a member while one of its cells is observed', async () => {
    const clock = createManualClock();
    const disposed: string[] = [];
    const members = family(
      (key: string, scope) => {
        scope.add(() => {
          disposed.push(key);
        });
        return { key, count: cell(0) };
      },
      { clock, lingerMs: 10 }
    );

    const member = members('one');
    const observer = createScope();
    observe(member.count, () => {}, { scope: observer });

    await clock.advanceBy(50);
    expect(members.peekMember('one')).toBe(member);
    expect(disposed).toEqual([]);

    await observer.dispose();
    await clock.advanceBy(10);
    expect(members.peekMember('one')).toBeUndefined();
    expect(disposed).toEqual(['one']);
    await members.dispose();
  });

  it('starts the linger window when the last observer detaches', async () => {
    const clock = createManualClock();
    const disposed: string[] = [];
    const members = family(
      (key: string, scope) => {
        scope.add(() => {
          disposed.push(key);
        });
        return { first: cell(0), second: cell(0) };
      },
      { clock, lingerMs: 10 }
    );

    const member = members('one');
    const firstObserver = createScope();
    const secondObserver = createScope();
    observe(member.first, () => {}, { scope: firstObserver });
    observe(member.second, () => {}, { scope: secondObserver });

    await firstObserver.dispose();
    await clock.advanceBy(15);
    expect(members.peekMember('one')).toBe(member);

    await secondObserver.dispose();
    await clock.advanceBy(9);
    expect(members.peekMember('one')).toBe(member);
    await clock.advanceBy(1);
    expect(members.peekMember('one')).toBeUndefined();
    expect(disposed).toEqual(['one']);
    await members.dispose();
  });

  it('retain keeps an unobserved member warm until released', async () => {
    const clock = createManualClock();
    const members = family((key: string) => ({ value: cell(key) }), { clock, lingerMs: 10 });

    const release = members.retain('one');
    const member = members.peekMember('one');
    expect(member).toBeDefined();
    await clock.advanceBy(100);
    expect(members.peekMember('one')).toBe(member);

    release();
    await clock.advanceBy(10);
    expect(members.peekMember('one')).toBeUndefined();
    await members.dispose();
  });

  it('keeps an observed keyed query alive across the linger window (README example)', async () => {
    const clock = createManualClock();
    let fetches = 0;
    const members = family(
      (key: { projectId: string }, scope) =>
        query({
          fetch: async () => {
            fetches += 1;
            return { projectId: key.projectId, fetches };
          },
          clock,
          scope,
        }),
      { clock, lingerMs: 10 }
    );

    const taskList = members({ projectId: 'p1' });
    const observer = createScope();
    observe(taskList, () => {}, { scope: observer });
    await clock.advanceBy(0);
    await settleAsync();

    expect(snapshot(taskList).value).toEqual({ projectId: 'p1', fetches: 1 });
    await clock.advanceBy(50);
    expect(members.peekMember({ projectId: 'p1' })).toBe(taskList);

    await observer.dispose();
    await clock.advanceBy(10);
    expect(members.peekMember({ projectId: 'p1' })).toBeUndefined();
    await members.dispose();
  });

  it('does not resurrect a disposed member when a stale cell is observed later', async () => {
    const clock = createManualClock();
    const members = family((key: string) => ({ value: cell(key) }), { clock, lingerMs: 10 });

    const stale = members('one');
    await clock.advanceBy(10);
    expect(members.peekMember('one')).toBeUndefined();

    const observer = createScope();
    observe(stale.value, () => {}, { scope: observer });
    expect(members.peekMember('one')).toBeUndefined();

    const fresh = members('one');
    expect(fresh).not.toBe(stale);
    await observer.dispose();
    await members.dispose();
  });

  it('disposes unretained entries after their linger window', async () => {
    const clock = createManualClock();
    const disposed: string[] = [];
    const members = family(
      (key: string, scope) => {
        scope.add(() => {
          disposed.push(key);
        });
        return { key };
      },
      { clock, lingerMs: 10 }
    );

    const member = members('one');
    expect(members.peekMember('one')).toBe(member);

    await clock.advanceBy(9);
    expect(members.peekMember('one')).toBe(member);
    await clock.advanceBy(1);

    expect(members.peekMember('one')).toBeUndefined();
    expect(disposed).toEqual(['one']);
    await members.dispose();
  });

  it('re-arms linger when an unretained entry is accessed during its linger window', async () => {
    const clock = createManualClock();
    const disposed: string[] = [];
    const members = family(
      (key: string, scope) => {
        scope.add(() => {
          disposed.push(key);
        });
        return { key };
      },
      { clock, lingerMs: 10 }
    );

    const member = members('one');
    await clock.advanceBy(5);
    expect(members('one')).toBe(member);
    await clock.advanceBy(5);
    expect(members.peekMember('one')).toBe(member);
    await clock.advanceBy(5);

    expect(members.peekMember('one')).toBeUndefined();
    expect(disposed).toEqual(['one']);
    await members.dispose();
  });

  it('keeps retained entries alive until the retain handle is released', async () => {
    const clock = createManualClock();
    const disposed: string[] = [];
    const members = family(
      (key: string, scope) => {
        scope.add(() => {
          disposed.push(key);
        });
        return { key };
      },
      { clock, lingerMs: 10 }
    );

    const release = members.retain('one');
    const member = members.peekMember('one');
    await clock.advanceBy(20);
    expect(members.peekMember('one')).toBe(member);

    release();
    await clock.advanceBy(10);
    expect(members.peekMember('one')).toBeUndefined();
    expect(disposed).toEqual(['one']);
    await members.dispose();
  });

  it('disposes all entry scopes when the family is disposed', async () => {
    const disposed: string[] = [];
    const members = family((key: string, scope) => {
      scope.add(() => {
        disposed.push(key);
      });
      return { key };
    });

    members('one');
    members('two');
    await members.dispose();

    expect(disposed.sort()).toEqual(['one', 'two']);
  });
});
