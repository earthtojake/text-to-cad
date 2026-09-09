import { defineCommand } from '@core/primitives/commands/api';
import { keybinding } from '@core/primitives/keybindings/api';

export const newConversationCommand = defineCommand({
  id: 'task.newConversation',
  title: 'New Conversation',
  description: 'Create a new conversation in the current task',
  category: 'Conversations',
  icon: 'message-square-plus',
  keybinding: keybinding.settings('newConversation', 'Mod+T'),
});

export const newConversationSplitRightCommand = defineCommand({
  id: 'task.newConversationSplitRight',
  title: 'New Conversation in Right Split',
  description: 'Create a new conversation in a split pane to the right',
  category: 'Conversations',
  icon: 'columns-2',
  keybinding: keybinding.settings('newConversationSplitRight', 'Mod+D'),
});

export const sidebarChangesCommand = defineCommand({
  id: 'task.sidebarChanges',
  title: 'View Changes',
  description: 'Open the Changes panel in the right sidebar',
  category: 'View',
  icon: 'file-diff',
  keybinding: keybinding.settings('sidebarChanges', 'Mod+Shift+1'),
});

export const sidebarConversationsCommand = defineCommand({
  id: 'task.sidebarConversations',
  title: 'View Conversations',
  description: 'Open the Conversations panel in the right sidebar',
  category: 'View',
  icon: 'message-square',
  keybinding: keybinding.settings('sidebarConversations', 'Mod+Shift+3'),
});

export const sidebarFilesCommand = defineCommand({
  id: 'task.sidebarFiles',
  title: 'View Files',
  description: 'Open the Files panel in the right sidebar',
  category: 'View',
  icon: 'folder-open',
  keybinding: keybinding.settings('sidebarFiles', 'Mod+Shift+2'),
});

export const fileContentSearchCommand = defineCommand({
  id: 'task.fileContentSearch',
  title: 'Search File Contents',
  description: 'Focus file content search in the right sidebar',
  category: 'Search',
  icon: 'search',
  keybinding: keybinding.settings('fileContentSearch', 'Mod+Shift+F', {
    allowWhenTerminalFocused: true,
  }),
});

export const viewTerminalsCommand = defineCommand({
  id: 'task.viewTerminals',
  title: 'View Terminals',
  description: 'Open the terminal drawer',
  category: 'View',
  icon: 'terminal',
});

export const toggleTerminalDrawerCommand = defineCommand({
  id: 'task.toggleTerminalDrawer',
  title: 'Toggle Terminal Drawer',
  description: 'Show or hide the terminal drawer',
  category: 'Panel',
  icon: 'terminal',
  keybinding: keybinding.settings('toggleTerminalDrawer', 'Mod+J'),
});

export const toggleRightSidebarCommand = defineCommand({
  id: 'task.toggleRightSidebar',
  title: 'Toggle Right Sidebar',
  description: 'Show or hide the right sidebar',
  category: 'Panel',
  icon: 'panel-right',
  keybinding: keybinding.settings('toggleRightSidebar', 'Mod+.'),
});

export const newTerminalCommand = defineCommand({
  id: 'task.newTerminal',
  title: 'New Terminal',
  description: 'Create a new terminal session',
  category: 'Terminals',
  icon: 'square-terminal',
  keybinding: keybinding.settings('newTerminal', 'Mod+Shift+`'),
});

export const openBrowserCommand = defineCommand({
  id: 'task.openBrowser',
  title: 'Open Browser',
  description: 'Open an in-app browser for this task',
  category: 'Browser',
  icon: 'globe',
  keybinding: keybinding.settings('openBrowser', 'Mod+Shift+B'),
});

export const browserGoBackCommand = defineCommand({
  id: 'task.browserGoBack',
  title: 'Browser Back',
  description: 'Go back in the active browser tab',
  category: 'Browser',
  icon: 'arrow-left',
});

export const browserGoForwardCommand = defineCommand({
  id: 'task.browserGoForward',
  title: 'Browser Forward',
  description: 'Go forward in the active browser tab',
  category: 'Browser',
  icon: 'arrow-right',
});

export const browserReloadCommand = defineCommand({
  id: 'task.browserReload',
  title: 'Reload Browser',
  description: 'Reload the active browser tab',
  category: 'Browser',
  icon: 'refresh-cw',
});

export const browserFocusUrlCommand = defineCommand({
  id: 'task.browserFocusUrl',
  title: 'Focus Browser URL',
  description: 'Focus the URL field in the active browser tab',
  category: 'Browser',
  icon: 'text-cursor-input',
});

export const browserOpenExternalCommand = defineCommand({
  id: 'task.browserOpenExternal',
  title: 'Open Browser URL Externally',
  description: 'Open the active browser URL in the system browser',
  category: 'Browser',
  icon: 'external-link',
});

export const browserCopyUrlCommand = defineCommand({
  id: 'task.browserCopyUrl',
  title: 'Copy Browser URL',
  description: 'Copy the active browser URL',
  category: 'Browser',
  icon: 'copy',
  keybinding: keybinding.settings('browserCopyUrl', 'Mod+Shift+C'),
});

export const gitFetchCommand = defineCommand({
  id: 'task.gitFetch',
  title: 'Git Fetch',
  description: 'Fetch latest changes from remote',
  category: 'Git',
  icon: 'git-pull-request',
});

export const gitPullCommand = defineCommand({
  id: 'task.gitPull',
  title: 'Git Pull',
  description: 'Pull latest changes from remote',
  category: 'Git',
  icon: 'arrow-down-to-line',
});

export const gitPushCommand = defineCommand({
  id: 'task.gitPush',
  title: 'Git Push',
  description: 'Push commits to remote',
  category: 'Git',
  icon: 'arrow-up-to-line',
});

export const pinTaskCommand = defineCommand({
  id: 'task.pin',
  title: 'Pin Task',
  description: 'Pin this task to keep it at the top',
  category: 'Task',
  icon: 'pin',
});

export const archiveTaskCommand = defineCommand({
  id: 'task.archive',
  title: 'Archive Task',
  description: 'Archive the current task',
  category: 'Task',
  icon: 'archive',
  keybinding: keybinding.settings('archiveTask', 'Mod+Shift+E', {
    ignoreWhenEditorFocused: true,
  }),
});

export const convertAutomationCommand = defineCommand({
  id: 'task.convertAutomation',
  title: 'Convert to Regular Task',
  description: 'Detach this task from its automation run',
  category: 'Task',
  icon: 'message-square',
});

export const nextTaskCommand = defineCommand({
  id: 'task.nextTask',
  title: 'Next Task',
  description: 'Switch to the next task',
  category: 'Navigation',
  icon: 'chevron-down',
  keybinding: keybinding.settings('taskNext', 'Mod+Alt+ArrowDown', {
    ignoreWhenEditorFocused: true,
  }),
});

export const previousTaskCommand = defineCommand({
  id: 'task.prevTask',
  title: 'Previous Task',
  description: 'Switch to the previous task',
  category: 'Navigation',
  icon: 'chevron-up',
  keybinding: keybinding.settings('taskPrev', 'Mod+Alt+ArrowUp', {
    ignoreWhenEditorFocused: true,
  }),
});

export const deleteSelectedTasksCommand = defineCommand({
  id: 'task.deleteSelected',
  title: 'Delete Selected Tasks',
  description: 'Delete the selected tasks',
  category: 'Task',
  keybinding: keybinding.settings('deleteSelectedTasks', 'Mod+Backspace', {
    ignoreWhenTextInputFocused: true,
  }),
});

export const TASK_COMMAND_DEFS = [
  newConversationCommand,
  newConversationSplitRightCommand,
  sidebarChangesCommand,
  sidebarConversationsCommand,
  sidebarFilesCommand,
  fileContentSearchCommand,
  viewTerminalsCommand,
  toggleTerminalDrawerCommand,
  toggleRightSidebarCommand,
  newTerminalCommand,
  openBrowserCommand,
  browserGoBackCommand,
  browserGoForwardCommand,
  browserReloadCommand,
  browserFocusUrlCommand,
  browserOpenExternalCommand,
  browserCopyUrlCommand,
  gitFetchCommand,
  gitPullCommand,
  gitPushCommand,
  pinTaskCommand,
  archiveTaskCommand,
  convertAutomationCommand,
  nextTaskCommand,
  previousTaskCommand,
] as const;

export const TASK_LIST_COMMAND_DEFS = [deleteSelectedTasksCommand] as const;
