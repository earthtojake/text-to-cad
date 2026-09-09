/**
 * Keymap extension:
 *  - Configured shortcut → submit.
 *    When a suggestion popup is active the suggestion plugin intercepts Enter
 *    first (returning `true`) so this handler only fires when no popup is open.
 *  - Shift+Enter → insert a hard break in every mode.
 *  - Unconfigured Enter shortcuts fall through to StarterKit.
 */

import { Extension } from '@tiptap/core';
import type { PromptSubmitShortcut } from '../types';

interface SubmitKeymapOptions {
  getShortcut: () => PromptSubmitShortcut;
  onSubmit: () => void;
}

export function buildSubmitKeymap({ getShortcut, onSubmit }: SubmitKeymapOptions): Extension {
  const submit = (shortcut: PromptSubmitShortcut) => {
    if (getShortcut() !== shortcut) return false;
    onSubmit();
    return true;
  };

  return Extension.create({
    name: 'submitKeymap',
    addKeyboardShortcuts() {
      return {
        Enter: () => submit('enter'),

        'Mod-Enter': () => submit('mod-enter'),

        'Shift-Enter': ({ editor }) => {
          editor.commands.setHardBreak();
          return true;
        },
      };
    },
  });
}
