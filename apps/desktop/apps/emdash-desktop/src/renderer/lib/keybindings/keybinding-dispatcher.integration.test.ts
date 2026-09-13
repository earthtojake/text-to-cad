import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import { closeSettingsCommand } from '@core/features/settings/contributions/commands';
import { settingsScope } from '@core/features/settings/contributions/scopes';
import {
  archiveTaskCommand,
  newConversationCommand,
} from '@core/features/tasks/contributions/commands';
import { taskViewScope } from '@core/features/tasks/contributions/scopes';
import {
  closeModalCommand,
  commandPaletteCommand,
  newTaskCommand,
  settingsCommand,
} from '@core/features/workbench/contributions/commands';
import { modalScope } from '@core/features/workbench/contributions/scopes';
import { windowScope } from '@core/manifests/browser/scope-catalog';
import { buildBrowserClaims } from '@core/manifests/shared/browser-claims';
import { COMMAND_CATALOG } from '@core/manifests/shared/command-catalog';
import { detectPlatformContext, matchesElectronInput } from '@core/primitives/keybindings/api';
import { KeybindingService } from '@core/primitives/keybindings/browser/keybinding-service';
import {
  defineViewScope,
  disabled,
  enabled,
  type CommandAvailability,
  type ViewScopeDefinition,
  type ViewScopeImpl,
} from '@core/primitives/view-scopes/api';
import { ViewScopes } from '@core/primitives/view-scopes/browser';
import { KeybindingDispatcher } from './keybinding-dispatcher';

const platform = detectPlatformContext();

function implementationFor<TDefinition extends ViewScopeDefinition>(
  definition: TDefinition,
  execute: (commandId: string) => void,
  availability: Readonly<Record<string, CommandAvailability>> = {}
): ViewScopeImpl<TDefinition> {
  return Object.fromEntries(
    definition.commands.map((command) => [
      command.id,
      () => ({
        availability: () => availability[command.id] ?? enabled,
        execute: () => execute(command.id),
      }),
    ])
  ) as unknown as ViewScopeImpl<TDefinition>;
}

function eventFor(key: string, code: string, primaryModifier = true) {
  const modifier = platform.os === 'mac' ? 'Meta' : 'Control';
  return {
    key,
    code,
    ctrlKey: primaryModifier && modifier === 'Control',
    metaKey: primaryModifier && modifier === 'Meta',
    altKey: false,
    shiftKey: false,
    repeat: false,
    isComposing: false,
    target: null,
    getModifierState: (candidate: string) => primaryModifier && candidate === modifier,
    preventDefault: vi.fn(),
    stopPropagation: vi.fn(),
  } as unknown as KeyboardEvent;
}

function createRuntime(
  execute: (commandId: string) => void,
  taskAvailability: Readonly<Record<string, CommandAvailability>> = {}
) {
  const runtime = new ViewScopes(undefined);
  const root = runtime.instantiate(windowScope(), {
    impl: implementationFor(windowScope, execute),
  });
  const task = runtime.instantiate(taskViewScope({ projectId: 'project-1', taskId: 'task-1' }), {
    parent: root,
    impl: implementationFor(taskViewScope, execute, taskAvailability),
  });
  runtime.activate(task);
  return runtime;
}

describe('KeybindingDispatcher catalog integration', () => {
  it('routes Escape to a capturing modal before the settings view', () => {
    const execute = vi.fn();
    const runtime = new ViewScopes(undefined);
    const settings = runtime.instantiate(settingsScope(), {
      impl: implementationFor(settingsScope, execute),
    });
    const modal = runtime.instantiate(modalScope(), {
      parent: settings,
      impl: implementationFor(modalScope, execute),
    });
    runtime.activateCapture(modal);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, platform),
      runtime,
      platform
    );

    expect(dispatcher.dispatch(eventFor('Escape', 'Escape', false)).kind).toBe('winner');
    expect(execute).toHaveBeenCalledOnce();
    expect(execute).toHaveBeenCalledWith(closeModalCommand.id);
    expect(execute).not.toHaveBeenCalledWith(closeSettingsCommand.id);
    runtime.dispose();
  });

  it('dispatches task and window commands through the active scope path', () => {
    const execute = vi.fn();
    const runtime = createRuntime(execute);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, platform),
      runtime,
      platform
    );

    expect(dispatcher.dispatch(eventFor(',', 'Comma')).kind).toBe('winner');
    expect(execute).toHaveBeenCalledWith(settingsCommand.id);

    expect(dispatcher.dispatch(eventFor('t', 'KeyT')).kind).toBe('winner');
    expect(execute).toHaveBeenCalledWith(newConversationCommand.id);
    runtime.dispose();
  });

  it('keeps window shortcuts active after a parentless overlay closes', () => {
    const execute = vi.fn();
    const runtime = createRuntime(execute);
    const modal = runtime.instantiate(modalScope(), {
      impl: implementationFor(modalScope, execute),
    });
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, platform),
      runtime,
      platform
    );

    const popOverlay = runtime.activateCapture(modal);
    popOverlay();

    expect(dispatcher.dispatch(eventFor('n', 'KeyN')).kind).toBe('winner');
    expect(execute).toHaveBeenCalledWith(newTaskCommand.id);
    runtime.dispose();
  });

  it('consumes disabled catalog commands and applies text-input gating', () => {
    const execute = vi.fn();
    const runtime = createRuntime(execute, {
      [newConversationCommand.id]: disabled('Unavailable'),
    });
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, platform),
      runtime,
      platform
    );

    expect(dispatcher.dispatch(eventFor('t', 'KeyT'))).toEqual({
      kind: 'consumed',
      commandId: newConversationCommand.id,
    });
    expect(
      dispatcher.dispatchSynthetic(new Set([archiveTaskCommand.id]), {
        textInputFocused: true,
        editorFocused: true,
        terminalFocused: false,
        browserFocused: false,
      }).kind
    ).toBe('none');
    expect(execute).not.toHaveBeenCalled();
    runtime.dispose();
  });

  it('preserves terminal shortcuts on non-mac platforms unless explicitly allowed', () => {
    const execute = vi.fn();
    const runtime = createRuntime(execute);
    const dispatcher = new KeybindingDispatcher(
      new KeybindingService(COMMAND_CATALOG.defs, { os: 'linux' }),
      runtime,
      { os: 'linux' }
    );

    expect(
      dispatcher.dispatchSynthetic(new Set([archiveTaskCommand.id]), {
        textInputFocused: true,
        editorFocused: false,
        terminalFocused: true,
        browserFocused: false,
      }).kind
    ).toBe('none');
    expect(execute).not.toHaveBeenCalled();
    runtime.dispose();
  });

  it('projects one override through dispatch, display, menu, and browser claims', () => {
    const testScope = defineViewScope({
      id: 'test.roundtrip',
      params: z.object({}),
      commands: [commandPaletteCommand] as const,
      activation: 'logical',
    });
    const runtime = new ViewScopes(undefined);
    const execute = vi.fn();
    const instance = runtime.instantiate(testScope(), {
      impl: {
        'app.commandPalette': () => ({ execute }),
      } satisfies ViewScopeImpl<typeof testScope>,
    });
    runtime.activate(instance);
    const service = new KeybindingService([commandPaletteCommand], { os: 'mac' }, [
      commandPaletteCommand,
    ]);
    service.setOverrides({ commandPalette: 'Meta+Shift+P' });
    const dispatcher = new KeybindingDispatcher(service, runtime);
    const event = (key: string, code: string, shiftKey: boolean) =>
      ({
        type: 'keydown',
        key,
        code,
        metaKey: true,
        ctrlKey: false,
        altKey: false,
        shiftKey,
        repeat: false,
        isComposing: false,
        target: null,
        getModifierState: (modifier: string) =>
          modifier === 'Meta' || (shiftKey && modifier === 'Shift'),
        preventDefault: vi.fn(),
        stopPropagation: vi.fn(),
      }) as unknown as KeyboardEvent;

    expect(dispatcher.dispatch(event('k', 'KeyK', false)).kind).toBe('none');
    expect(dispatcher.dispatch(event('p', 'KeyP', true)).kind).toBe('winner');
    expect(service.chordFor(commandPaletteCommand.id)).toBe('Shift+Meta+P');
    expect(service.snapshotForMenu()[0]?.accelerator).toBe('Shift+Command+P');

    const claim = buildBrowserClaims({ commandPalette: 'Meta+Shift+P' }, { os: 'mac' }).find(
      (entry) => entry.commandId === commandPaletteCommand.id
    );
    expect(claim?.chord).toBe('Shift+Meta+P');
    expect(
      claim &&
        matchesElectronInput(
          {
            type: 'keyDown',
            key: 'P',
            code: 'KeyP',
            meta: true,
            shift: true,
          },
          claim.chord,
          { os: 'mac' }
        )
    ).toBe(true);
    expect(execute).toHaveBeenCalledOnce();
    runtime.dispose();
  });
});
