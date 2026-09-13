import { JSDOM } from 'jsdom';
import { describe, expect, it, vi } from 'vitest';
import { z } from 'zod';
import {
  newConversationCommand,
  sidebarChangesCommand,
  sidebarConversationsCommand,
  sidebarFilesCommand,
  toggleTerminalDrawerCommand,
} from '@core/features/tasks/contributions/commands';
import {
  newProjectCommand,
  newTaskCommand,
  settingsCommand,
  toggleThemeCommand,
} from '@core/features/workbench/contributions/commands';
import { defineCommandCatalog } from '@core/primitives/commands/api';
import {
  defineCommandPaletteCatalog,
  defineCommandPaletteItem,
  definePaletteProviderCatalog,
  PaletteController,
  type PaletteProviderMatch,
} from '@core/primitives/palette/api';
import { defineViewScope, disabled, hidden } from '@core/primitives/view-scopes/api';
import { ViewScopes } from '@core/primitives/view-scopes/browser';
import {
  createCommandsPaletteProvider,
  type CommandPaletteMatch,
} from './commands-palette-provider';

function requireSynchronous(
  matches: readonly PaletteProviderMatch[] | Promise<readonly PaletteProviderMatch[]>
) {
  expect(matches).not.toBeInstanceOf(Promise);
  return matches as readonly CommandPaletteMatch[];
}

describe('commands palette provider', () => {
  it('synchronously fuzzy-matches titles and aliases before descriptions', async () => {
    const commandCatalog = defineCommandCatalog([settingsCommand, toggleThemeCommand]);
    const paletteCatalog = defineCommandPaletteCatalog(commandCatalog, [
      defineCommandPaletteItem({ command: settingsCommand }),
      defineCommandPaletteItem({
        command: toggleThemeCommand,
        aliases: ['appearance', 'color scheme', 'dark mode', 'light mode'],
      }),
    ]);
    const viewScope = defineViewScope({
      id: 'test.commands',
      params: z.object({}),
      commands: commandCatalog.defs,
      activation: 'logical',
    });
    const viewScopes = new ViewScopes(undefined);
    const active = viewScopes.instantiate(viewScope(), {
      impl: {
        'app.settings': () => ({ execute: vi.fn() }),
        'app.toggleTheme': () => ({ execute: vi.fn() }),
      },
    });
    viewScopes.activate(active);
    const provider = createCommandsPaletteProvider({
      catalog: paletteCatalog,
      viewScopes,
      chordFor: () => null,
    });

    expect(provider.kind).toBe('commands');
    expect(provider.keyword).toBe('@commands');
    expect(provider.minQueryLength).toBe(1);

    for (const query of ['theme', 'tth', 'appearance', 'color scheme', 'dark mode', 'light mode']) {
      const matches = requireSynchronous(provider.search({ query, context: {} }));
      const themeMatch = matches.find(({ id }) => id === toggleThemeCommand.id);
      expect(themeMatch, query).toBeDefined();
      expect(themeMatch?.relevance.band, query).not.toBe('secondary');
    }

    const descriptionMatches = requireSynchronous(
      provider.search({ query: 'application', context: {} })
    );
    expect(descriptionMatches.map(({ id }) => id)).toEqual([settingsCommand.id]);
    expect(descriptionMatches[0]?.relevance.band).toBe('secondary');

    const controller = new PaletteController(definePaletteProviderCatalog([provider]));
    await controller.setInput('tth', {});
    expect(controller.getSnapshot().results[0]?.match.id).toBe(toggleThemeCommand.id);

    const fileSearch = vi.fn(() => []);
    const unifiedController = new PaletteController(
      definePaletteProviderCatalog([
        provider,
        {
          kind: 'files',
          keyword: '@files',
          minQueryLength: 1,
          search: fileSearch,
          render: () => null,
        },
      ])
    );
    await unifiedController.setInput('@commands theme', {});
    expect(unifiedController.getSnapshot().mode?.keyword).toBe('@commands');
    expect(unifiedController.getSnapshot().results[0]?.match.id).toBe(toggleThemeCommand.id);
    expect(fileSearch).not.toHaveBeenCalled();

    await unifiedController.setInput('theme', {});
    expect(unifiedController.getSnapshot().mode).toBeUndefined();
    expect(fileSearch).toHaveBeenCalledOnce();
    viewScopes.dispose();
  });

  it('uses the exact ordered app, project, and task idle command lists', () => {
    const commandCatalog = defineCommandCatalog([
      settingsCommand,
      newProjectCommand,
      newTaskCommand,
      toggleThemeCommand,
      newConversationCommand,
      sidebarChangesCommand,
      sidebarConversationsCommand,
      sidebarFilesCommand,
      toggleTerminalDrawerCommand,
    ]);
    const paletteCatalog = defineCommandPaletteCatalog(
      commandCatalog,
      commandCatalog.defs.map((command) => defineCommandPaletteItem({ command }))
    );
    const viewScope = defineViewScope({
      id: 'test.idleCommands',
      params: z.object({}),
      commands: commandCatalog.defs,
      activation: 'logical',
    });
    const viewScopes = new ViewScopes(undefined);
    const active = viewScopes.instantiate(viewScope(), {
      impl: {
        'app.settings': () => ({ execute: vi.fn() }),
        'app.newProject': () => ({ execute: vi.fn() }),
        'app.newTask': () => ({ execute: vi.fn() }),
        'app.toggleTheme': () => ({ execute: vi.fn() }),
        'task.newConversation': () => ({ execute: vi.fn() }),
        'task.sidebarChanges': () => ({ execute: vi.fn() }),
        'task.sidebarConversations': () => ({ execute: vi.fn() }),
        'task.sidebarFiles': () => ({ execute: vi.fn() }),
        'task.toggleTerminalDrawer': () => ({ execute: vi.fn() }),
      },
    });
    viewScopes.activate(active);
    const provider = createCommandsPaletteProvider({
      catalog: paletteCatalog,
      viewScopes,
      chordFor: () => null,
    });
    const idleIds = (context: { projectId?: string; taskId?: string }) =>
      requireSynchronous(provider.idle?.(context) ?? []).map(({ id }) => id);

    expect(idleIds({})).toEqual([newProjectCommand.id, settingsCommand.id]);
    expect(idleIds({ projectId: 'project-1' })).toEqual([newTaskCommand.id, settingsCommand.id]);
    expect(idleIds({ projectId: 'project-1', taskId: 'task-1' })).toEqual([
      newConversationCommand.id,
      sidebarChangesCommand.id,
      sidebarFilesCommand.id,
      sidebarConversationsCommand.id,
      toggleTerminalDrawerCommand.id,
    ]);
    expect([...idleIds({}), ...idleIds({ projectId: 'project-1' })]).not.toContain(
      toggleThemeCommand.id
    );
    viewScopes.dispose();
  });

  it('uses captured view-scope availability and executes only enabled commands', () => {
    const commandCatalog = defineCommandCatalog([
      settingsCommand,
      toggleThemeCommand,
      newProjectCommand,
    ]);
    const paletteCatalog = defineCommandPaletteCatalog(
      commandCatalog,
      commandCatalog.defs.map((command) => defineCommandPaletteItem({ command }))
    );
    const originScope = defineViewScope({
      id: 'test.commandOrigin',
      params: z.object({}),
      commands: commandCatalog.defs,
      activation: 'logical',
    });
    const capturingScope = defineViewScope({
      id: 'test.commandPalette',
      params: z.object({}),
      commands: [],
      activation: 'focus',
      traits: ['capturing'],
    });
    const dom = new JSDOM('<div id="palette" tabindex="-1"></div>');
    const viewScopes = new ViewScopes(dom.window.document);
    const hiddenExecute = vi.fn();
    const disabledExecute = vi.fn();
    const enabledExecute = vi.fn();
    const origin = viewScopes.instantiate(originScope(), {
      impl: {
        'app.settings': () => ({ availability: () => hidden, execute: hiddenExecute }),
        'app.toggleTheme': () => ({
          availability: () => disabled('Theme switching is unavailable'),
          execute: disabledExecute,
        }),
        'app.newProject': () => ({ execute: enabledExecute }),
      },
    });
    const capture = viewScopes.instantiate(capturingScope(), { parent: origin, impl: {} });
    capture.attachRef(dom.window.document.querySelector<HTMLElement>('#palette'));
    viewScopes.activate(origin);
    viewScopes.activateCapture(capture);
    dom.window.document
      .querySelector<HTMLElement>('#palette')
      ?.dispatchEvent(new dom.window.FocusEvent('focusin', { bubbles: true }));
    const provider = createCommandsPaletteProvider({
      catalog: paletteCatalog,
      viewScopes,
      chordFor: () => null,
    });

    expect(requireSynchronous(provider.search({ query: 'settings', context: {} }))).toEqual([]);
    const disabledMatch = requireSynchronous(provider.search({ query: 'theme', context: {} }))[0];
    expect(disabledMatch?.disabledReason).toBe('Theme switching is unavailable');
    expect(disabledMatch?.execute()).toBe(false);
    expect(disabledExecute).not.toHaveBeenCalled();

    const enabledMatch = requireSynchronous(
      provider.search({ query: 'new project', context: {} })
    )[0];
    expect(enabledMatch?.execute()).toBe(true);
    expect(enabledExecute).toHaveBeenCalledWith(undefined, 'palette');
    expect(hiddenExecute).not.toHaveBeenCalled();
    viewScopes.dispose();
  });
});
