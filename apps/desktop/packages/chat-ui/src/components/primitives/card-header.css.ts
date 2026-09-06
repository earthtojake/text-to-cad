import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';

// Uses content-box intentionally: the borderBottom is counted by card chrome
// measurement helpers as the header separator.
export const cardHeader = style({
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: '6px',
  paddingLeft: '8px',
  paddingRight: '8px',
  cursor: 'pointer',
  color: vars.fgMuted,
  fontSize: vars.typeBodyFontSize,
  borderBottom: `1px solid ${vars.border}`,
  transition: 'background 150ms',
  userSelect: 'none',
  selectors: {
    '&:hover': { background: vars.bg3 },
  },
});

export const cardHeaderLeft = style({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  minWidth: 0,
});

export const cardHeaderTitle = style({
  minWidth: 0,
});

export const cardHeaderRight = style({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  flexShrink: 0,
});

export const cardLeadingSlot = style({
  position: 'relative',
  width: '14px',
  height: '14px',
  flexShrink: 0,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
});

export const cardLeadingIcon = style({
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  transition: 'opacity 120ms ease-out',
  selectors: {
    [`${cardHeader}:hover &`]: { opacity: 0 },
  },
});

export const cardHoverChevron = style({
  position: 'absolute',
  inset: 0,
  display: 'inline-flex',
  alignItems: 'center',
  justifyContent: 'center',
  fontSize: '10px',
  opacity: 0,
  transition: 'opacity 120ms ease-out, transform 150ms ease-out',
  selectors: {
    [`${cardHeader}:hover &`]: { opacity: 1 },
  },
});

export const cardChevronExpanded = style({
  transform: 'rotate(90deg)',
});

export const cardErrorIcon = style({
  display: 'flex',
  color: vars.fgError,
});

export const cardPermissionIcon = style({
  display: 'flex',
  color: vars.planActive,
});
