import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { defineCommand } from '@core/primitives/commands/api';
import { keybinding } from '@core/primitives/keybindings/api';
import { KeybindingService } from '@core/primitives/keybindings/browser/keybinding-service';
import { defineViewScope, disabled, type ViewScopeImpl } from '@core/primitives/view-scopes/api';
import { ViewScopes } from '@core/primitives/view-scopes/browser';
import { KeybindingDispatcher } from './keybinding-dispatcher';

const outerCommand = defineCommand({
  id: 'test.outer',
  title: 'Outer',
  category: 'Test',
  keybinding: keybinding.fixed('Control+K'),
});
const innerCommand = defineCommand({
  id: 'test.inner',
  title: 'Inner',
  category: 'Test',
  keybinding: keybinding.fixed('Control+K'),
});
const textCommand = defineCommand({
  id: 'test.text',
  title: 'Text gated',
  category: 'Test',
  keybinding: keybinding.fixed('Control+T', { ignoreWhenTextInputFocused: true }),
});

const outerScope = defineViewScope({
  id: 'test.outerScope',
  params: z.object({}),
  commands: [outerCommand] as const,
  activation: 'logical',
});
const innerScope = defineViewScope({
  id: 'test.innerScope',
  params: z.object({}),
  commands: [innerCommand] as const,
  activation: 'logical',
});
const textScope = defineViewScope({
  id: 'test.textScope',
  params: z.object({}),
  commands: [textCommand] as const,
  activation: 'logical',
  traits: ['text-input'],
});

function eventFor(key: string, code: string, modifier = 'Control') {
  const preventDefault = vi.fn();
  const stopPropagation = vi.fn();
  return {
    key,
    code,
    ctrlKey: modifier === 'Control',
    metaKey: modifier === 'Meta',
    altKey: false,
    shiftKey: false,
    repeat: false,
    isComposing: false,
    target: null,
    getModifierState: (value: string) => value === modifier,
    preventDefault,
    stopPropagation,
  } as unknown as KeyboardEvent & {
    preventDefault: ReturnType<typeof vi.fn>;
    stopPropagation: ReturnType<typeof vi.fn>;
  };
}

describe('KeybindingDispatcher', () => {
  it('collects all matches and lets the active scope choose the winner', () => {
    const outerExecute = vi.fn();
    const innerExecute = vi.fn();
    const runtime = new ViewScopes(undefined);
    const outer = runtime.instantiate(outerScope(), {
      impl: {
        'test.outer': () => ({ execute: outerExecute }),
      } satisfies ViewScopeImpl<typeof outerScope>,
    });
    const inner = runtime.instantiate(innerScope(), {
      parent: outer,
      impl: {
        'test.inner': () => ({ execute: innerExecute }),
      } satisfies ViewScopeImpl<typeof innerScope>,
    });
    runtime.activate(inner);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService([outerCommand, innerCommand], { os: 'linux' }),
      runtime
    );
    const event = eventFor('k', 'KeyK');

    const hit = dispatcher.dispatch(event);

    expect(hit.kind).toBe('winner');
    expect(innerExecute).toHaveBeenCalledWith(undefined, 'keybinding');
    expect(outerExecute).not.toHaveBeenCalled();
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(event.stopPropagation).toHaveBeenCalledOnce();
    runtime.dispose();
  });

  it('consumes a disabled inner match without falling through', () => {
    const outerExecute = vi.fn();
    const innerExecute = vi.fn();
    const runtime = new ViewScopes(undefined);
    const outer = runtime.instantiate(outerScope(), {
      impl: {
        'test.outer': () => ({ execute: outerExecute }),
      } satisfies ViewScopeImpl<typeof outerScope>,
    });
    const inner = runtime.instantiate(innerScope(), {
      parent: outer,
      impl: {
        'test.inner': () => ({
          availability: () => disabled('Unavailable'),
          execute: innerExecute,
        }),
      } satisfies ViewScopeImpl<typeof innerScope>,
    });
    runtime.activate(inner);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService([outerCommand, innerCommand], { os: 'linux' }),
      runtime
    );
    const event = eventFor('k', 'KeyK');

    expect(dispatcher.dispatch(event)).toEqual({
      kind: 'consumed',
      commandId: 'test.inner',
    });
    expect(innerExecute).not.toHaveBeenCalled();
    expect(outerExecute).not.toHaveBeenCalled();
    expect(event.preventDefault).toHaveBeenCalledOnce();
    expect(event.stopPropagation).not.toHaveBeenCalled();
    runtime.dispose();
  });

  it('gates text-input commands for DOM and synthetic dispatch', () => {
    const execute = vi.fn();
    const runtime = new ViewScopes(undefined);
    const instance = runtime.instantiate(textScope(), {
      impl: {
        'test.text': () => ({ execute }),
      } satisfies ViewScopeImpl<typeof textScope>,
    });
    runtime.activate(instance);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService([textCommand], { os: 'linux' }),
      runtime
    );

    expect(dispatcher.dispatch(eventFor('t', 'KeyT')).kind).toBe('none');
    expect(
      dispatcher.dispatchSynthetic(new Set([textCommand.id]), {
        textInputFocused: true,
        editorFocused: false,
        terminalFocused: false,
        browserFocused: false,
      }).kind
    ).toBe('none');
    expect(execute).not.toHaveBeenCalled();
    runtime.dispose();
  });

  it('passes through unclaimed events', () => {
    const runtime = new ViewScopes(undefined);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService([outerCommand], { os: 'linux' }),
      runtime
    );
    const event = eventFor('p', 'KeyP');

    expect(dispatcher.dispatch(event).kind).toBe('none');
    expect(event.preventDefault).not.toHaveBeenCalled();
    expect(event.stopPropagation).not.toHaveBeenCalled();
    runtime.dispose();
  });

  it('attaches a capture-phase listener and returns cleanup', () => {
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService([], { os: 'linux' }),
      new ViewScopes(undefined)
    );
    const target = {
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as Window;

    const dispose = dispatcher.attach(target);
    const handler = vi.mocked(target.addEventListener).mock.calls[0]?.[1];

    expect(target.addEventListener).toHaveBeenCalledWith('keydown', handler, { capture: true });
    dispose();
    expect(target.removeEventListener).toHaveBeenCalledWith('keydown', handler, { capture: true });
  });
});
