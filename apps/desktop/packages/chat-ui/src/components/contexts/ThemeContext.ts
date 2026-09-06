/**
 * ThemeContext — Solid context that provides the current ChatTheme to all
 * descendant components in the chat tree.
 *
 * ChatRoot (or any test harness) provides the theme; component renderers that
 * need geometry constants (heights, paddings) call `useTheme()` to read them
 * rather than importing from per-component metrics files.
 *
 * The value is a reactive accessor `() => ChatTheme` so that a parent can
 * swap the theme without remounting the whole subtree — the accessor is
 * re-evaluated by any reactive computation that reads it.
 */

import type { ChatTheme } from '@core/theme';
import { DEFAULT_THEME } from '@core/theme';
import { createContext, useContext } from 'solid-js';

export const ThemeContext = createContext<() => ChatTheme>(() => DEFAULT_THEME);

/** Returns the current ChatTheme reactive accessor from the nearest ThemeContext. */
export const useTheme = (): (() => ChatTheme) => useContext(ThemeContext);
