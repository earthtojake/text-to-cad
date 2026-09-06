import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { defineCommand } from '@core/primitives/commands/api';
import { defineViewScope, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { ViewScopes, type ViewScopeInstance } from '@core/primitives/view-scopes/browser';
import { useViewScope, ViewScopeInstanceProvider } from '@core/primitives/view-scopes/react';

const command = defineCommand({
  id: 'task.test',
  title: 'Test',
  category: 'Test',
});
const rootScope = defineViewScope({
  id: 'window',
  params: z.object({}),
  commands: [command],
  activation: 'logical',
});
const taskScope = defineViewScope({
  id: 'view.task',
  params: z.object({ taskId: z.string() }),
  commands: [command],
  activation: 'logical',
  key: ({ taskId }) => taskId,
});
const rootImpl: ViewScopeImpl<typeof rootScope> = {
  'task.test': () => ({ execute: () => undefined }),
};
const taskImpl: ViewScopeImpl<typeof taskScope> = {
  'task.test': () => ({ execute: () => undefined }),
};

let container: HTMLDivElement;
let root: Root;

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe('useViewScope', () => {
  it('creates nested instances, attaches the DOM marker, and disposes on unmount', async () => {
    const runtime = new ViewScopes(document);
    let parentInstance: ViewScopeInstance | undefined;
    let childInstance: ViewScopeInstance | undefined;

    function Child() {
      const scope = useViewScope(taskScope({ taskId: 'task-1' }), taskImpl, runtime);
      childInstance = scope.instance;
      return createElement('div', { id: 'child', ref: scope.attachRef });
    }

    function Parent() {
      const scope = useViewScope(rootScope(), rootImpl, runtime);
      parentInstance = scope.instance;
      return createElement(
        ViewScopeInstanceProvider,
        { instance: scope.instance },
        createElement('div', { id: 'parent', ref: scope.attachRef }),
        scope.instance ? createElement(Child) : null
      );
    }

    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(Parent));
    });

    expect(parentInstance).toBeDefined();
    expect(childInstance?.parent).toBe(parentInstance);
    expect(container.querySelector('#parent')?.getAttribute('data-view-scope')).toBe(
      parentInstance?.id
    );
    expect(container.querySelector('#child')?.getAttribute('data-view-scope')).toBe(
      childInstance?.id
    );

    const mountedParent = parentInstance;
    const mountedChild = childInstance;
    act(() => root.unmount());
    expect(mountedParent?.isDisposed).toBe(true);
    expect(mountedChild?.isDisposed).toBe(true);
    runtime.dispose();

    root = createRoot(container);
  });

  it('replaces the instance when the ref key changes', async () => {
    const runtime = new ViewScopes(document);
    let currentInstance: ViewScopeInstance | undefined;

    function Task({ taskId }: { readonly taskId: string }) {
      const scope = useViewScope(taskScope({ taskId }), taskImpl, runtime);
      currentInstance = scope.instance;
      return createElement('div', { ref: scope.attachRef });
    }

    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(Task, { taskId: 'task-1' }));
    });
    const first = currentInstance;

    await act(async () => {
      root.render(createElement(Task, { taskId: 'task-2' }));
    });

    expect(first?.isDisposed).toBe(true);
    expect(currentInstance?.ref.key).toBe('view.task:task-2');
    expect(currentInstance).not.toBe(first);
    runtime.dispose();
  });

  it('keeps the instance while using the latest inline implementation', async () => {
    const runtime = new ViewScopes(document);
    const firstExecute = vi.fn();
    const secondExecute = vi.fn();
    let currentInstance: ViewScopeInstance | undefined;

    function Task({ execute }: { readonly execute: () => void }) {
      const implementation: ViewScopeImpl<typeof taskScope> = {
        'task.test': () => ({ execute }),
      };
      const scope = useViewScope(taskScope({ taskId: 'task-1' }), implementation, runtime);
      currentInstance = scope.instance;
      return createElement('div', { ref: scope.attachRef });
    }

    container = document.createElement('div');
    document.body.append(container);
    root = createRoot(container);
    await act(async () => {
      root.render(createElement(Task, { execute: firstExecute }));
    });
    const firstInstance = currentInstance;
    void currentInstance?.getCommand(command)?.execute(undefined);
    expect(firstExecute).toHaveBeenCalledOnce();

    await act(async () => {
      root.render(createElement(Task, { execute: secondExecute }));
    });

    expect(currentInstance).toBe(firstInstance);
    void currentInstance?.getCommand(command)?.execute(undefined);
    expect(firstExecute).toHaveBeenCalledOnce();
    expect(secondExecute).toHaveBeenCalledOnce();
    runtime.dispose();
  });
});
