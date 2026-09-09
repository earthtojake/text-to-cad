import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { defineCommand } from '@core/primitives/commands/api';
import {
  defineViewScope,
  disabled,
  enabled,
  hidden,
  viewScopeDefFor,
  type ViewScopeImpl,
  type ViewScopeParams,
} from './define-view-scope';

const archiveCommand = defineCommand({
  id: 'task.archive',
  title: 'Archive Task',
  category: 'Task',
});

const createBranchCommand = defineCommand({
  id: 'task.createBranch',
  title: 'Create Branch',
  category: 'Git',
  input: z.object({ branchName: z.string(), baseRef: z.string() }),
});

describe('defineViewScope', () => {
  it('constructs a keyed, frozen ref with schema-parsed params', () => {
    const scope = defineViewScope({
      id: 'view.task',
      params: z.object({ projectId: z.string(), taskId: z.string() }),
      commands: [archiveCommand],
      activation: 'logical',
      key: ({ taskId }) => taskId,
    });

    const ref = scope({ projectId: 'project-1', taskId: 'task-1' });

    expect(ref).toMatchObject({
      scopeId: 'view.task',
      params: { projectId: 'project-1', taskId: 'task-1' },
      key: 'view.task:task-1',
    });
    expect(viewScopeDefFor(ref)).toBe(scope);
    expect(Object.isFrozen(ref)).toBe(true);
    expect(Object.isFrozen(ref.params)).toBe(true);
    expect(scope.commands).toEqual([archiveCommand]);
  });

  it('uses stable sorted JSON for the default instance key', () => {
    const scope = defineViewScope({
      id: 'selection',
      params: z.object({ z: z.string(), a: z.object({ y: z.number(), b: z.number() }) }),
      commands: [],
      activation: 'logical',
    });

    expect(scope({ z: 'last', a: { y: 2, b: 1 } }).key).toBe(
      'selection:{"a":{"b":1,"y":2},"z":"last"}'
    );
  });

  it('makes empty params optional and rejects invalid params', () => {
    const windowScope = defineViewScope({
      id: 'window',
      params: z.object({}),
      commands: [],
      activation: 'logical',
    });

    expect(windowScope()).toMatchObject({ scopeId: 'window', params: {} });
    expect(windowScope.safeRef(undefined)).toMatchObject({ params: {} });
    expectTypeOf<Parameters<typeof windowScope>>().toEqualTypeOf<
      [params?: Record<string, never>]
    >();
  });

  it('rejects duplicate command ids', () => {
    expect(() =>
      defineViewScope({
        id: 'duplicate',
        params: z.object({}),
        commands: [archiveCommand, archiveCommand],
        activation: 'logical',
      })
    ).toThrow('Duplicate command id in view scope duplicate: task.archive');
  });

  it('requires an implementation factory for every declared command', () => {
    const scope = defineViewScope({
      id: 'view.task',
      params: z.object({ projectId: z.string(), taskId: z.string() }),
      commands: [archiveCommand, createBranchCommand],
      activation: 'logical',
    });

    const complete: ViewScopeImpl<typeof scope> = {
      'task.archive': () => ({ execute: () => undefined }),
      'task.createBranch': () => ({ execute: () => undefined }),
    };
    // @ts-expect-error task.createBranch is deliberately missing.
    const incomplete: ViewScopeImpl<typeof scope> = {
      'task.archive': () => ({ execute: () => undefined }),
    };

    expect(Object.keys(complete)).toHaveLength(2);
    expect(Object.keys(incomplete)).toHaveLength(1);
    expectTypeOf<ViewScopeParams<typeof scope>>().toEqualTypeOf<{
      projectId: string;
      taskId: string;
    }>();
  });

  it('provides frozen availability values', () => {
    expect(enabled).toEqual({ kind: 'enabled' });
    expect(hidden).toEqual({ kind: 'hidden' });
    expect(disabled('Unavailable')).toEqual({ kind: 'disabled', reason: 'Unavailable' });
    expect(Object.isFrozen(disabled('Unavailable'))).toBe(true);
  });
});
