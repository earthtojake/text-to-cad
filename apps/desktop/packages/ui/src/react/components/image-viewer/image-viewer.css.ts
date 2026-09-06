import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

// ── ZoomViewerDialog ──────────────────────────────────────────────────────────

export const toolbarRow = style({
  display: 'flex',
  flexShrink: 0,
  justifyContent: 'flex-end',
  padding: '0.75rem',
  paddingBottom: '0.5rem',
});

export const toolbarGroup = style({
  display: 'flex',
  alignItems: 'center',
  gap: '2px',
  overflow: 'hidden',
  borderRadius: tokenVars.radiusMd,
  border: `1px solid ${vars.border}`,
  backgroundColor: vars.surface,
  padding: '2px',
  boxShadow: vars.shadowSm,
});

// Each hover target keeps its own visible curvature instead of relying on the
// outer group's clipping, so no middle toolbar action flashes as a square.
export const toolbarButton = style({
  '@layer': {
    utilities: { borderRadius: tokenVars.radiusSm },
  },
});

export const viewerBody = style({
  minHeight: 0,
  flex: 1,
  paddingLeft: '0.5rem',
  paddingRight: '0.5rem',
  paddingBottom: '0.5rem',
});

// Sizing is owned by the inline wrapperStyle passed to TransformComponent
// (react-zoom-pan-pinch defaults the wrapper to fit-content otherwise).
export const transformWrapper = style({
  borderRadius: tokenVars.radiusMd,
  backgroundColor: vars.background1,
});

export const unavailable = style({
  fontSize: tokenVars.textSm,
  color: vars.foregroundMuted,
});

export const unavailableContainer = style({
  display: 'flex',
  minHeight: 0,
  flex: 1,
  alignItems: 'center',
  justifyContent: 'center',
  padding: '1rem',
  paddingTop: 0,
});

// ── ContainedImage / ExpandableImage ─────────────────────────────────────────

export const containedImage = style({
  objectFit: 'contain',
});

// Inside the zoom dialog the image renders at natural size; the transform
// wrapper owns scaling, so viewport-relative caps must come off.
export const zoomTargetImage = style({
  display: 'block',
  height: 'auto',
  maxHeight: 'none',
  maxWidth: 'none',
});

export const expandableContainer = style({
  position: 'relative',
  display: 'inline-block',
  maxWidth: '100%',
  verticalAlign: 'top',
});

export const expandButton = style({
  position: 'absolute',
  top: '0.25rem',
  right: '0.25rem',
  zIndex: 10,
  opacity: 0,
  transition: 'opacity 150ms',
  backgroundColor: vars.surface,
  boxShadow: `${vars.shadowSm}, 0 0 0 1px color-mix(in srgb, ${vars.border} 80%, transparent)`,
  selectors: {
    [`${expandableContainer}:hover &`]: { opacity: 1 },
    '&:focus-visible': { opacity: 1 },
  },
});
