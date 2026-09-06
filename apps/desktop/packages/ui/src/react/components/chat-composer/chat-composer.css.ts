import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

export const composerRoot = style({
  display: 'flex',
  flexDirection: 'column',
});

export const noticeBand = recipe({
  base: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '0.5rem',
    borderRadius: `${tokenVars.radius2xl} ${tokenVars.radius2xl} 0 0`,
    border: '1px solid',
    borderBottomWidth: 0,
    paddingLeft: '0.75rem',
    paddingRight: '0.75rem',
    paddingTop: '0.5rem',
    paddingBottom: '0.5rem',
    fontSize: tokenVars.textXs,
  },
  variants: {
    variant: {
      error: {
        backgroundColor: vars.surfaceDestructive,
        borderColor: vars.surfaceDestructiveBorder,
        color: vars.surfaceDestructiveForeground,
      },
      warning: {
        backgroundColor: vars.surfaceWarning,
        borderColor: vars.surfaceWarningBorder,
        color: vars.surfaceWarningForeground,
      },
      info: {
        backgroundColor: vars.surfaceInfo,
        borderColor: vars.surfaceInfoBorder,
        color: vars.surfaceInfoForeground,
      },
    },
  },
  defaultVariants: { variant: 'info' },
});

export const noticeBandBody = style({ flex: 1 });

export const noticeBandHeader = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.375rem',
});

export const noticeBandTitle = style({
  fontSize: tokenVars.textSm,
  lineHeight: 1.375,
});

export const noticeBandMessage = style({ lineHeight: 1.375 });

export const noticeBandMessageIndented = style({
  marginTop: '0.25rem',
  opacity: 0.8,
});

export const noticeDismiss = style({
  display: 'grid',
  width: '1.5rem',
  height: '1.5rem',
  marginLeft: '0.25rem',
  flexShrink: 0,
  placeItems: 'center',
  borderRadius: tokenVars.radiusMd,
  opacity: 0.7,
  outline: 'none',
  transition: 'background-color 150ms, box-shadow 150ms, opacity 150ms',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceHover, opacity: 1 },
    '&:focus-visible': {
      boxShadow: `0 0 0 2px color-mix(in srgb, ${vars.borderFocus} 38%, transparent)`,
      opacity: 1,
    },
  },
});

export const noticeAnimWrapper = style({
  display: 'grid',
  transition: 'grid-template-rows 200ms ease-out, opacity 200ms ease-out',
});

export const noticeAnimVisible = style({ gridTemplateRows: '1fr', opacity: 1 });
export const noticeAnimHidden = style({ gridTemplateRows: '0fr', opacity: 0 });

export const noticeOverflowClip = style({ overflow: 'hidden' });

// ── Composer shell ────────────────────────────────────────────────────────────

export const composerShell = recipe({
  base: {
    // Host-overridable via `--composer-bg`; defaults to the elevated surface.
    backgroundColor: `var(--composer-bg, ${vars.surfaceBaseEmphasis})`,
    display: 'flex',
    flexDirection: 'column',
    gap: 0,
    border: `1px solid ${vars.border}`,
    transition: 'border-color 150ms',
    selectors: {
      '&:hover': { borderColor: vars.border1 },
      '&:focus-within': {
        borderColor: vars.border1,
      },
    },
  },
  variants: {
    hasBand: {
      true: { borderRadius: `0 0 ${tokenVars.radius2xl} ${tokenVars.radius2xl}` },
      false: { borderRadius: tokenVars.radius2xl },
    },
    dragActive: {
      true: {
        borderColor: vars.border1,
        boxShadow: `0 0 0 1px ${vars.border1}`,
      },
      false: {},
    },
  },
  defaultVariants: { hasBand: false, dragActive: false },
});

// ── Image attachments ─────────────────────────────────────────────────────────

export const attachmentStrip = style({
  display: 'flex',
  flexWrap: 'wrap',
  gap: '0.5rem',
  paddingLeft: '0.75rem',
  paddingRight: '0.75rem',
  paddingTop: '0.75rem',
});

export const attachmentThumb = style({
  position: 'relative',
  width: '2rem',
  height: '2rem',
});

export const attachmentThumbBtn = style({
  display: 'block',
  width: '2rem',
  height: '2rem',
  padding: 0,
  borderRadius: tokenVars.radiusMd,
  selectors: {
    '&:focus-visible': { outlineWidth: 2, outlineOffset: 1 },
  },
});

export const attachmentThumbImg = style({
  width: '2rem',
  height: '2rem',
  borderRadius: tokenVars.radiusMd,
  objectFit: 'cover',
  boxShadow: `0 0 0 1px ${vars.border}`,
});

export const attachmentRemoveBtn = style({
  position: 'absolute',
  top: '-0.375rem',
  right: '-0.375rem',
  display: 'grid',
  placeItems: 'center',
  width: '1rem',
  height: '1rem',
  borderRadius: tokenVars.radiusFull,
  backgroundColor: vars.surface,
  color: vars.foreground,
  opacity: 0,
  boxShadow: `0 0 0 1px ${vars.border}`,
  transition: 'opacity 150ms',
  selectors: {
    // Show on hover of parent thumb
    '[data-attachment-thumb]:hover &': { opacity: 1 },
  },
});

// ── Editor area ───────────────────────────────────────────────────────────────

export const editorArea = style({
  maxHeight: '200px',
  overflowY: 'auto',
  paddingLeft: '0.75rem',
  paddingRight: '0.75rem',
  paddingTop: '0.75rem',
  paddingBottom: '0.5rem',
});

// ── Toolbar ───────────────────────────────────────────────────────────────────

export const toolbar = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.25rem',
  paddingBottom: '0.5rem',
});

export const toolbarLeft = style({
  display: 'flex',
  minWidth: 0,
  flex: 1,
  alignItems: 'center',
  gap: '0.375rem',
  overflow: 'hidden',
});
export const toolbarRight = style({
  display: 'flex',
  flexShrink: 0,
  alignItems: 'center',
  gap: '0.25rem',
});

export const permissionModeTrigger = style({
  paddingLeft: '0.1875rem',
  paddingRight: '0.1875rem',
});

export const mcpTrigger = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '0.25rem',
  borderRadius: tokenVars.radiusMd,
  paddingLeft: '0.1875rem',
  paddingRight: '0.1875rem',
  color: vars.foreground,
  fontSize: tokenVars.textXs,
  lineHeight: 1,
  outline: 'none',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceBaseSelected },
    '&[data-popup-open]': { backgroundColor: vars.surfaceBaseSelected },
  },
});

export const mcpPopoverContent = style({
  width: '16rem',
  padding: '0.5rem',
});

export const mcpList = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '0.25rem',
});

export const mcpRow = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '0.75rem',
  borderRadius: tokenVars.radiusMd,
  padding: '0.375rem 0.5rem',
  fontSize: tokenVars.textSm,
  color: vars.foreground,
});

export const mcpName = style({
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const mcpBadge = style({
  flexShrink: 0,
  borderRadius: tokenVars.radiusSm,
  border: `1px solid ${vars.border}`,
  padding: '0.0625rem 0.3125rem',
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});

// ── Agent trigger ─────────────────────────────────────────────────────────────

export const agentTrigger = style({
  display: 'flex',
  width: '1.75rem',
  height: '1.75rem',
  alignItems: 'center',
  justifyContent: 'center',
  borderRadius: tokenVars.radiusMd,
  border: '1px solid transparent',
  color: vars.foreground,
  outline: 'none',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceBaseSelected },
    '&[data-popup-open]': { backgroundColor: vars.surfaceBaseSelected },
  },
});

export const agentIconPlaceholder = style({
  width: '1rem',
  height: '1rem',
  borderRadius: tokenVars.radiusSm,
  backgroundColor: vars.border,
});

// ── Model detail card ─────────────────────────────────────────────────────────

export const modelDetailCard = style({
  width: '14rem',
  padding: '0.75rem',
  fontSize: tokenVars.textSm,
  color: vars.foreground,
});

export const modelDetailName = style({
  lineHeight: 1.25,
  fontWeight: 400,
});

export const modelDetailDesc = style({
  marginTop: '0.25rem',
  fontSize: tokenVars.textXs,
  lineHeight: 1.375,
  color: vars.foregroundMuted,
});

export const modelDetailFeatures = style({
  marginTop: '0.5rem',
  borderTop: `1px solid ${vars.border}`,
  paddingTop: '0.5rem',
});

export const modelDetailRow = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '0.75rem',
  fontSize: tokenVars.textXs,
});

export const modelDetailLabel = style({
  color: vars.foregroundMuted,
  fontSize: tokenVars.textTiny,
});
export const modelDetailValue = style({ color: vars.foreground });

export const barMeter = style({ display: 'flex', alignItems: 'center', gap: '0.125rem' });

/** Codex-style primary composer action. */
export const sendButtonRound = style({ borderRadius: tokenVars.radiusFull });

export const stopIcon = style({
  width: '0.5rem',
  height: '0.5rem',
  borderRadius: '0.0625rem',
  backgroundColor: 'currentColor',
});

// ── Context usage indicator ────────────────────────────────────────────────────

/** Donut SVG container — sized to match other toolbar icons. */
export const donut = style({
  width: '1rem',
  height: '1rem',
  display: 'block',
  overflow: 'visible',
});

/** Background track ring. */
export const donutTrack = style({ stroke: vars.border });

/** Foreground fill ring — normal state. */
export const donutProgress = style({ stroke: vars.foreground });

/** Foreground fill ring — warning state (>= 90% full). */
export const donutProgressWarn = style({ stroke: vars.surfaceWarningForeground });

/** Cost row shown below the description in the popover when cost is available. */
export const usageCostRow = style({
  marginTop: '0.625rem',
  fontSize: tokenVars.textXs,
  color: vars.foregroundMuted,
});

export const usagePopoverBody = style({
  width: '16rem',
});

export const usageStatsRow = style({
  display: 'flex',
  alignItems: 'baseline',
  justifyContent: 'space-between',
  gap: '1rem',
  fontSize: tokenVars.textXs,
});

export const usagePercent = style({
  fontWeight: 400,
  color: vars.foreground,
});

export const usageTokenCount = style({
  color: vars.foregroundMuted,
  whiteSpace: 'nowrap',
});

export const usageBarTrack = style({
  marginTop: '0.5rem',
  height: '0.375rem',
  overflow: 'hidden',
  borderRadius: tokenVars.radiusFull,
  backgroundColor: vars.border,
});

export const usageBarFill = style({
  height: '100%',
  borderRadius: tokenVars.radiusFull,
  backgroundColor: vars.foreground,
});

export const usageBarFillWarn = style({
  backgroundColor: vars.surfaceWarningForeground,
});

export const barDotFilled = style({
  width: '0.375rem',
  height: '0.375rem',
  borderRadius: '9999px',
  background: vars.foregroundMuted,
});

export const barDotEmpty = style({
  width: '0.375rem',
  height: '0.375rem',
  borderRadius: '9999px',
  background: vars.border,
});

// ── Effort row (footer inside the model popover) ───────────────────────────────

/**
 * Full-width row rendered in the model popover footer that acts as the trigger
 * for the effort/thought-level submenu flyout.
 */
export const effortRow = style({
  display: 'flex',
  width: '100%',
  alignItems: 'center',
  justifyContent: 'space-between',
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingTop: '0.375rem',
  paddingBottom: '0.375rem',
  borderRadius: tokenVars.radiusMd,
  fontSize: tokenVars.textSm,
  color: vars.foreground,
  background: 'transparent',
  border: 'none',
  cursor: 'default',
  outline: 'none',
  selectors: {
    '&:hover': { backgroundColor: vars.surfaceHover },
    '&[data-popup-open]': { backgroundColor: vars.surfaceHover },
  },
});

export const effortRowLabel = style({
  color: vars.foregroundMuted,
  fontSize: tokenVars.textTiny,
});

export const effortRowValue = style({
  display: 'flex',
  alignItems: 'center',
  gap: '0.25rem',
  color: vars.foregroundMuted,
  fontSize: tokenVars.textXs,
});
