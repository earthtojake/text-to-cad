/**
 * chat-root.css.ts — layout classes for ChatRoot.tsx.
 *
 * Previously all inline Tailwind utilities. Now typed VE style objects.
 * The `contentClass` prop API is preserved — hosts who pass a custom string
 * should now pass a VE class or a raw CSS class string.
 */

import { style } from '@vanilla-extract/css';
import { vars } from './styles/theme.css';

/** Max-width of the centered content column — matches user message cards. */
const CONTAINER_WIDTH = '42rem';

/**
 * Horizontal gutter applied to the scroll container, pinned overlay, and
 * composer slot so the centered content column keeps breathing room from the
 * viewport edge once the viewport is narrower than CONTAINER_WIDTH.
 */
const CONTENT_GUTTER = '16px';

/** Outer clip container — clips the pinned overlay during scroll handoff. */
export const outerClip = style({
  position: 'relative',
  height: '100%',
  width: '100%',
  overflow: 'hidden',
  // Base font so chrome text (headers, tool/thinking/plan rows) inherits the
  // sans font rather than the browser default. Prose/code set font-family
  // explicitly; this only affects elements that rely on inheritance.
  fontFamily: vars.fontSans,
});

/** Scroll container — the element ChatRoot attaches its scroll listener to. */
export const scrollContainer = style({
  position: 'relative',
  height: '100%',
  width: '100%',
  overflowX: 'hidden',
  overflowY: 'auto',
  // Reserve a stable gutter so the scrollbar appearing/disappearing does not
  // change contentRect.width, which would trigger prose re-wrap ("flash") and
  // transient height desync ("overlap") on every thinking expand/collapse.
  scrollbarGutter: 'stable',
  // Horizontal breathing room so the centered content column never touches the
  // viewport edge when the viewport is narrower than CONTAINER_WIDTH. Applied on
  // this flow ancestor (not the content column) so the width probe and the
  // absolutely-positioned rows both shrink correctly. The pinned overlay and
  // composer slot carry the same gutter to stay aligned.
  paddingLeft: CONTENT_GUTTER,
  paddingRight: CONTENT_GUTTER,
});

/** Virtualizer canvas — positions all rows absolutely inside this container. */
export const canvas = style({
  position: 'relative',
});

/**
 * Zero-height width probe — carries `contentClass` so it reports the capped
 * content-column width. The width ResizeObserver targets this instead of the
 * virtualizer canvas so it only fires on genuine layout-width changes (viewport
 * resize or gutter toggle), never on canvas height mutations driven by streaming
 * or expand/collapse tween updates.
 */
export const widthProbeClass = style({
  height: 0,
  overflow: 'hidden',
  pointerEvents: 'none',
});

/** Per-unit row wrapper — translates each row to its virtualizer Y position. */
export const unitRowWrapper = style({
  position: 'absolute',
  top: 0,
  left: 0,
  width: '100%',
  willChange: 'transform',
  contain: 'layout paint style',
});

/** Pinned overlay container — absolute, full-width, z above canvas. */
export const pinnedOverlay = style({
  pointerEvents: 'none',
  position: 'absolute',
  left: 0,
  right: 0,
  top: 0,
  zIndex: 10,
  willChange: 'transform',
});

/**
 * Pinned overlay column. ChatRoot positions this from the width probe's actual
 * rect so it shares the scroll container's content geometry, including any
 * scrollbar gutter reserved by the browser.
 */
export const pinnedOverlayColumn = style({
  position: 'relative',
});

/**
 * Default content centering class.
 * Replaces `mx-auto w-full max-w-2xl` from Tailwind.
 * Hosts can override via the `contentClass` prop.
 */
export const defaultContentClass = style({
  marginLeft: 'auto',
  marginRight: 'auto',
  width: '100%',
  maxWidth: CONTAINER_WIDTH,
});

/**
 * Content overlay slot — non-scrolling cover above the transcript/scroll,
 * below the composer. Click-through by default so an empty/transparent overlay
 * never blocks scrolling; host content opts into pointer-events as needed.
 * z-index 15: above pinnedOverlay (10), below composerSlotClass (20).
 */
export const contentOverlaySlotClass = style({
  position: 'absolute',
  inset: 0,
  zIndex: 15,
  pointerEvents: 'none',
});

/**
 * Composer slot — sticky positioning layer only. Transparent so the scrollbar
 * at the viewport edge remains fully visible.
 */
export const composerSlotClass = style({
  position: 'sticky',
  bottom: 0,
  left: 0,
  right: 0,
  width: '100%',
  zIndex: 20,
  // Match the scroll container gutter so the composer column aligns with the
  // message column when the viewport is narrower than CONTAINER_WIDTH.
  paddingLeft: CONTENT_GUTTER,
  paddingRight: CONTENT_GUTTER,
});

/**
 * Centered composer slot layer used for new/empty conversations. The layer
 * covers the transcript while letting only the hero/composer children receive
 * input, so the host keeps one stable portal target across placements.
 */
export const composerSlotCenteredClass = style({
  position: 'absolute',
  inset: 0,
  zIndex: 20,
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  width: '100%',
  paddingLeft: CONTENT_GUTTER,
  paddingRight: CONTENT_GUTTER,
  pointerEvents: 'none',
});

export const composerSlotAnimatingClass = style({
  transition: 'transform 420ms cubic-bezier(0.16, 1, 0.3, 1)',
});

export const heroSlotClass = style({
  marginBottom: '1rem',
  width: '100%',
  maxWidth: CONTAINER_WIDTH,
  pointerEvents: 'auto',
  transition: 'opacity 260ms ease-out, transform 360ms cubic-bezier(0.16, 1, 0.3, 1)',
});

export const heroSlotVisibleClass = style({
  position: 'relative',
  opacity: 1,
  transform: 'translateY(0)',
});

export const heroSlotHiddenClass = style({
  position: 'absolute',
  opacity: 0,
  transform: 'translateY(8px)',
  pointerEvents: 'none',
});

/**
 * Inner centering wrapper inside the composer slot — constrains the composer
 * to the same max-width as the content column so it aligns with user message
 * cards. Carries the blurred backdrop and 8px bottom gap so the blur only
 * covers the content area, leaving the scrollbar track unobscured.
 * This is the element exposed as `view.composerSlot` (portal target).
 */
export const composerSlotInnerClass = style({
  marginLeft: 'auto',
  marginRight: 'auto',
  width: '100%',
  maxWidth: CONTAINER_WIDTH,
  paddingBottom: '8px',
  pointerEvents: 'auto',
});

export const composerSlotInnerBottomClass = style({
  background: `color-mix(in srgb, ${vars.bg} 80%, transparent)`,
  backdropFilter: 'blur(8px)',
});

export const composerSlotInnerCenteredClass = style({
  paddingBottom: 0,
});
