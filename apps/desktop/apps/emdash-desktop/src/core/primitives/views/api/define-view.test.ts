import { describe, expect, expectTypeOf, it } from 'vitest';
import { z } from 'zod';
import { defineLayout, slot } from '@core/primitives/layouts/api';
import { defineViewScope } from '@core/primitives/view-scopes/api';
import { defineView, type ViewLocation, type ViewParams } from './define-view';

const layout = defineLayout({
  id: 'test',
  slots: { main: slot.main() },
});

describe('defineView', () => {
  it('constructs a frozen ref with schema-parsed params', () => {
    const view = defineView({
      id: 'project',
      params: z.object({ projectId: z.string() }),
      layout,
      telemetryEvent: 'project_viewed',
    });

    const ref = view({ projectId: 'project-1' });

    expect(ref).toEqual({
      viewId: 'project',
      params: { projectId: 'project-1' },
      key: 'project',
    });
    expect(Object.isFrozen(ref)).toBe(true);
    expect(Object.isFrozen(ref.params)).toBe(true);
    expect(view.telemetryEvent).toBe('project_viewed');
  });

  it('deeply freezes ref params and the traits collection', () => {
    const view = defineView({
      id: 'library',
      params: z.object({
        selection: z.object({
          tabs: z.array(z.string()),
        }),
      }),
      layout,
      traits: ['library'],
    });

    const ref = view({ selection: { tabs: ['skills'] } });

    expect(Object.isFrozen(ref.params.selection)).toBe(true);
    expect(Object.isFrozen(ref.params.selection.tabs)).toBe(true);
    expect(Object.isFrozen(view.traits)).toBe(true);
  });

  it('rejects invalid params', () => {
    const view = defineView({
      id: 'project',
      params: z.object({ projectId: z.string() }),
      layout,
    });

    expect(() => view({ projectId: 1 } as never)).toThrow();
  });

  it('makes params optional only when every field is optional', () => {
    const homeView = defineView({
      id: 'home',
      params: z.object({}),
      layout,
    });
    const libraryView = defineView({
      id: 'library',
      params: z.object({ tab: z.enum(['prompts', 'skills']).optional() }),
      layout,
    });
    const taskView = defineView({
      id: 'task',
      params: z.object({ taskId: z.string() }),
      layout,
    });

    expect(homeView()).toMatchObject({ params: {} });
    expect(libraryView()).toMatchObject({ params: {} });
    expect(libraryView({ tab: 'skills' })).toMatchObject({ params: { tab: 'skills' } });
    expectTypeOf<Parameters<typeof libraryView>>().toEqualTypeOf<
      [params?: { tab?: 'prompts' | 'skills' | undefined }]
    >();
    expectTypeOf<Parameters<typeof taskView>>().toEqualTypeOf<[params: { taskId: string }]>();
  });

  it('folds the history identity into the ref key', () => {
    const view = defineView({
      id: 'task',
      params: z.object({ taskId: z.string() }),
      layout,
      historyKey: ({ taskId }) => taskId,
    });

    expect(view({ taskId: 'task-1' }).key).toBe('task:task-1');
    expect(view({ taskId: 'task-2' }).key).toBe('task:task-2');
  });

  it('preserves a scope projection typed against view params', () => {
    const taskScope = defineViewScope({
      id: 'view.task',
      params: z.object({ taskId: z.string() }),
      commands: [],
      activation: 'logical',
      key: ({ taskId }) => taskId,
    });
    const view = defineView({
      id: 'task',
      params: z.object({ projectId: z.string(), taskId: z.string() }),
      layout,
      scope: ({ taskId }) => taskScope({ taskId }),
    });

    expect(view.scope?.({ projectId: 'project-1', taskId: 'task-1' })).toMatchObject({
      scopeId: 'view.task',
      params: { taskId: 'task-1' },
    });
  });

  it('safely rehydrates valid params and strips unknown keys', () => {
    const view = defineView({
      id: 'project',
      params: z.object({ projectId: z.string() }),
      layout,
    });

    expect(view.safeRef({ projectId: 'project-1', stale: true })).toEqual({
      viewId: 'project',
      params: { projectId: 'project-1' },
      key: 'project',
    });
    expect(view.safeRef({ projectId: 1 })).toBeUndefined();
    expect(view.safeRef(undefined)).toBeUndefined();
  });

  it('accepts undefined when safely rehydrating an optional-params view', () => {
    const view = defineView({
      id: 'home',
      params: z.object({}),
      layout,
    });

    expect(view.safeRef(undefined)).toEqual({
      viewId: 'home',
      params: {},
      key: 'home',
    });
    expect(view.safeRef(null)).toBeUndefined();
  });

  it('derives param and location values from a definition', () => {
    const view = defineView({
      id: 'task',
      params: z.object({ taskId: z.string() }),
      layout,
      location: {
        schema: z.object({ tabId: z.string() }),
        key: ({ tabId }) => tabId,
      },
    });
    const viewWithoutLocation = defineView({
      id: 'home',
      params: z.object({}),
      layout,
    });

    expectTypeOf<ViewParams<typeof view>>().toEqualTypeOf<{ taskId: string }>();
    expectTypeOf<ViewLocation<typeof view>>().toEqualTypeOf<{ tabId: string }>();
    expectTypeOf<ViewLocation<typeof viewWithoutLocation>>().toEqualTypeOf<never>();
  });

  it('rejects an empty view id', () => {
    expect(() =>
      defineView({
        id: ' ',
        params: z.object({}),
        layout,
      })
    ).toThrow('A view id must not be empty');
  });
});
