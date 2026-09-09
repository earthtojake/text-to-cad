/**
 * Row geometry constants for the engine-level row layout.
 *
 * These values are fixed — they are not themeable. They live here, colocated
 * with the engine row infrastructure that owns them.
 */

/** Standard single-line row height (px) for tool/plan/diff/resource-link rows. */
export const ROW_H = 32;

/** Horizontal inset (px) applied to both sides of non-user-message rows. */
export const ROW_INSET_X = 16;

/**
 * Extra vertical space (px) added to body line-height to produce the
 * collapsible header row height.
 */
export const HEADER_ROW_EXTRA_H = 8;
