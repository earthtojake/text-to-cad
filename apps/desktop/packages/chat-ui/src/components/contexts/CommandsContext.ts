/**
 * CommandsContext — Solid context that provides the current ChatCommands to all
 * descendant components in the chat tree.
 *
 * ChatRoot provides a reactive accessor `() => ChatCommands`; component renderers
 * that need to fire user-action callbacks (open-file, etc.) call `useCommands()`
 * rather than receiving callbacks as props.
 *
 * Mirrors the pattern established by ThemeContext.
 */

import { createContext, useContext } from 'solid-js';
import type { ChatCommands } from '@/commands';

const EMPTY_COMMANDS: ChatCommands = {};

export const CommandsContext = createContext<() => ChatCommands>(() => EMPTY_COMMANDS);

/** Returns the current ChatCommands reactive accessor from the nearest CommandsContext. */
export const useCommands = (): (() => ChatCommands) => useContext(CommandsContext);
