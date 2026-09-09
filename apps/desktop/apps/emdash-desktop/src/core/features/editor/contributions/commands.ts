import { defineCommand } from '@core/primitives/commands/api';
import { keybinding } from '@core/primitives/keybindings/api';

const fileTreeKeybindingOptions = { ignoreWhenTextInputFocused: true } as const;

export const fileTreeRenameCommand = defineCommand({
  id: 'editor.fileTree.rename',
  title: 'Rename File Tree Item',
  description: 'Rename the selected file tree item',
  category: 'Files',
  icon: 'file-pen',
  keybinding: keybinding.settings('fileTreeRename', 'Mod+Shift+R', fileTreeKeybindingOptions),
});

export const fileTreeCutCommand = defineCommand({
  id: 'editor.fileTree.cut',
  title: 'Cut File Tree Items',
  description: 'Cut the selected file tree items',
  category: 'Files',
  icon: 'scissors',
  keybinding: keybinding.settings('fileTreeCut', 'Mod+X', fileTreeKeybindingOptions),
});

export const fileTreeCopyCommand = defineCommand({
  id: 'editor.fileTree.copy',
  title: 'Copy File Tree Items',
  description: 'Copy the selected file tree items',
  category: 'Files',
  icon: 'copy',
  keybinding: keybinding.settings('fileTreeCopy', 'Mod+C', fileTreeKeybindingOptions),
});

export const fileTreePasteCommand = defineCommand({
  id: 'editor.fileTree.paste',
  title: 'Paste File Tree Items',
  description: 'Paste cut or copied file tree items',
  category: 'Files',
  icon: 'clipboard-paste',
  keybinding: keybinding.settings('fileTreePaste', 'Mod+V', fileTreeKeybindingOptions),
});

export const fileTreeDeleteCommand = defineCommand({
  id: 'editor.fileTree.delete',
  title: 'Delete File Tree Items',
  description: 'Delete the selected file tree items',
  category: 'Files',
  icon: 'trash-2',
  keybinding: keybinding.settings('fileTreeDelete', 'Mod+Backspace', fileTreeKeybindingOptions),
});

export const EDITOR_FILE_TREE_COMMAND_DEFS = [
  fileTreeRenameCommand,
  fileTreeCutCommand,
  fileTreeCopyCommand,
  fileTreePasteCommand,
  fileTreeDeleteCommand,
] as const;
