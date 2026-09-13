/**
 * TurnStateContext — Solid context providing the current turn lifecycle state
 * to all descendant components in the chat tree.
 *
 * ChatRoot provides:
 *   - `currentMessageId` — the id of the last committed user-role message (the
 *     message whose turn is currently active), or null when none exists.
 *   - `turnStatus` — reactive `TurnStatus` accessor from the transcript store.
 *
 * Components (e.g. UserMessageCard) call `useTurnState()` to decide whether to
 * show the stop button and the current-message hover border.
 *
 * Mirrors the pattern established by CommandsContext.
 */

import { createContext, useContext } from 'solid-js';
import type { TurnStatus } from '@/state/transcript';

export type TurnState = {
  currentMessageId: () => string | null;
  turnStatus: () => TurnStatus;
};

const DEFAULT_TURN_STATE: TurnState = {
  currentMessageId: () => null,
  turnStatus: () => 'done',
};

export const TurnStateContext = createContext<TurnState>(DEFAULT_TURN_STATE);

/** Returns the TurnState reactive accessors from the nearest TurnStateContext. */
export const useTurnState = (): TurnState => useContext(TurnStateContext);
