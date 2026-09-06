import { z } from 'zod';
import { defineCommand } from '@core/primitives/commands/api';
import { code, keybinding } from '@core/primitives/keybindings/api';

export const settingsCommand = defineCommand({
  id: 'app.settings',
  title: 'Open Settings',
  description: 'Open application settings',
  category: 'App',
  icon: 'settings',
  keybinding: keybinding.settings('settings', 'Mod+,'),
});

export const newProjectCommand = defineCommand({
  id: 'app.newProject',
  title: 'New Project',
  description: 'Create or open a folder for chats and engineering files',
  category: 'App',
  icon: 'folder-plus',
  keybinding: keybinding.settings('newProject', 'Mod+Shift+N'),
});

export const newTaskCommand = defineCommand({
  id: 'app.newTask',
  title: 'New Chat',
  description: 'Start a chat in the current project folder',
  category: 'App',
  icon: 'square-plus',
  // Keybindings invoke without input; contextual callers may supply a project.
  input: z.object({ projectId: z.string().optional() }).optional(),
  keybinding: keybinding.settings('newTask', 'Mod+N'),
});

export const toggleThemeCommand = defineCommand({
  id: 'app.toggleTheme',
  title: 'Toggle Theme',
  description: 'Switch between light and dark themes',
  category: 'View',
  icon: 'palette',
});

export const navigateBackCommand = defineCommand({
  id: 'app.navigateBack',
  title: 'Go Back',
  description: 'Navigate to the previous location',
  category: 'Navigation',
  icon: 'arrow-left',
  keybinding: keybinding.settings('navigateBack', code(['Mod'], 'BracketLeft')),
});

export const navigateForwardCommand = defineCommand({
  id: 'app.navigateForward',
  title: 'Go Forward',
  description: 'Navigate to the next location',
  category: 'Navigation',
  icon: 'arrow-right',
  keybinding: keybinding.settings('navigateForward', code(['Mod'], 'BracketRight')),
});

export const commandPaletteCommand = defineCommand({
  id: 'app.commandPalette',
  title: 'Command Palette',
  description: 'Open the command palette to quickly search and navigate',
  category: 'Navigation',
  keybinding: keybinding.settings('commandPalette', 'Mod+K'),
});

export const openInEditorCommand = defineCommand({
  id: 'app.openInEditor',
  title: 'Open in Editor',
  description: 'Open the project in the default editor',
  category: 'Navigation',
  keybinding: keybinding.settings('openInEditor', 'Mod+O'),
});

export const confirmCommand = defineCommand({
  id: 'app.confirm',
  title: 'Confirm',
  description: 'Confirm the current action',
  category: 'App',
  keybinding: keybinding.settings('confirm', 'Mod+Enter'),
});

export const closeModalCommand = defineCommand({
  id: 'modal.close',
  title: 'Close Modal',
  description: 'Close the current modal or dialog',
  category: 'Navigation',
  keybinding: keybinding.fixed('Escape'),
});

export const nextTabCommand = defineCommand({
  id: 'workbench.tabNext',
  title: 'Next Tab',
  description: 'Switch to the next tab',
  category: 'Tab Navigation',
  keybinding: keybinding.settings('tabNext', 'Mod+Alt+ArrowRight'),
});

export const previousTabCommand = defineCommand({
  id: 'workbench.tabPrev',
  title: 'Previous Tab',
  description: 'Switch to the previous tab',
  category: 'Tab Navigation',
  keybinding: keybinding.settings('tabPrev', 'Mod+Alt+ArrowLeft'),
});

export const closeTabCommand = defineCommand({
  id: 'workbench.tabClose',
  title: 'Close Tab',
  description: 'Close the active tab',
  category: 'Tab Navigation',
  keybinding: keybinding.settings('tabClose', 'Mod+W'),
});

export const reopenTabCommand = defineCommand({
  id: 'workbench.tabReopen',
  title: 'Reopen Closed Tab',
  description: 'Reopen the most recently closed tab',
  category: 'Tab Navigation',
  keybinding: keybinding.settings('tabReopen', 'Mod+Shift+T'),
});

export const renameTabCommand = defineCommand({
  id: 'workbench.tabRename',
  title: 'Rename Tab',
  description: 'Rename the active tab',
  category: 'Tab Navigation',
  keybinding: keybinding.settings('tabRename', 'Mod+Shift+R'),
});

export const splitPaneCommand = defineCommand({
  id: 'workbench.splitPane',
  title: 'Split Pane',
  description: 'Move the active tab to a new pane on the right',
  category: 'Tab Navigation',
  keybinding: keybinding.settings('splitPane', code(['Mod'], 'Backslash')),
});

export const cycleNextTabCommand = defineCommand({
  id: 'workbench.tabCycleNext',
  title: 'Cycle to Next Tab',
  description: 'Switch to the next tab',
  category: 'Tab Navigation',
  keybinding: keybinding.fixed('Control+Tab', { allowWhenTerminalFocused: true }),
});

export const cyclePreviousTabCommand = defineCommand({
  id: 'workbench.tabCyclePrev',
  title: 'Cycle to Previous Tab',
  description: 'Switch to the previous tab',
  category: 'Tab Navigation',
  keybinding: keybinding.fixed('Control+Shift+Tab', { allowWhenTerminalFocused: true }),
});

export const saveEditorCommand = defineCommand({
  id: 'editor.save',
  title: 'Save File',
  description: 'Save the active editor file',
  category: 'Editor',
  keybinding: keybinding.fixed('Mod+S', { ignoreWhenBrowserFocused: true }),
});

export const saveAllEditorsCommand = defineCommand({
  id: 'editor.saveAll',
  title: 'Save All Files',
  description: 'Save all open editor files',
  category: 'Editor',
  keybinding: keybinding.fixed('Mod+Shift+S', { ignoreWhenBrowserFocused: true }),
});

export const findInTerminalCommand = defineCommand({
  id: 'terminal.find',
  title: 'Find in Terminal',
  description: 'Search the focused terminal',
  category: 'Terminal',
  keybinding: keybinding.fixed('Mod+F', { allowWhenTerminalFocused: true }),
});

export const closeTerminalSearchCommand = defineCommand({
  id: 'terminalSearch.close',
  title: 'Close Terminal Search',
  description: 'Close terminal search',
  category: 'Terminal',
  keybinding: keybinding.fixed('Escape'),
});

function defineTabIndexCommand<const TIndex extends number>(index: TIndex) {
  return defineCommand({
    id: `workbench.tab${index}` as const,
    title: `Open Tab ${index}`,
    description: `Switch to tab ${index}`,
    category: 'Tab Navigation',
    keybinding: keybinding.fixed(`Mod+${index}`),
  });
}

export const tabIndexCommands = [
  defineTabIndexCommand(1),
  defineTabIndexCommand(2),
  defineTabIndexCommand(3),
  defineTabIndexCommand(4),
  defineTabIndexCommand(5),
  defineTabIndexCommand(6),
  defineTabIndexCommand(7),
  defineTabIndexCommand(8),
  defineTabIndexCommand(9),
] as const;

export const toggleLeftSidebarCommand = defineCommand({
  id: 'workbench.toggleLeftSidebar',
  title: 'Toggle Left Sidebar',
  description: 'Show or hide the left sidebar',
  category: 'View',
  keybinding: keybinding.settings('toggleLeftSidebar', 'Mod+B'),
});

export const zenModeCommand = defineCommand({
  id: 'workbench.zenMode',
  title: 'Zen Mode',
  description: 'Hide both sidebars',
  category: 'View',
  keybinding: keybinding.settings('zenMode', 'Control+Z', {
    ignoreWhenEditorFocused: true,
    ignoreWhenBrowserFocused: true,
  }),
});

export const WINDOW_COMMAND_DEFS = [
  settingsCommand,
  newProjectCommand,
  newTaskCommand,
  toggleThemeCommand,
  navigateBackCommand,
  navigateForwardCommand,
  commandPaletteCommand,
  openInEditorCommand,
  confirmCommand,
  toggleLeftSidebarCommand,
  zenModeCommand,
] as const;

export const WORKBENCH_COMMAND_DEFS = [
  ...WINDOW_COMMAND_DEFS,
  closeModalCommand,
  nextTabCommand,
  previousTabCommand,
  closeTabCommand,
  reopenTabCommand,
  renameTabCommand,
  splitPaneCommand,
  cycleNextTabCommand,
  cyclePreviousTabCommand,
  saveEditorCommand,
  saveAllEditorsCommand,
  findInTerminalCommand,
  closeTerminalSearchCommand,
  ...tabIndexCommands,
] as const;

export const PANE_COMMAND_DEFS = [
  nextTabCommand,
  previousTabCommand,
  closeTabCommand,
  reopenTabCommand,
  renameTabCommand,
  splitPaneCommand,
  cycleNextTabCommand,
  cyclePreviousTabCommand,
  ...tabIndexCommands,
] as const;
