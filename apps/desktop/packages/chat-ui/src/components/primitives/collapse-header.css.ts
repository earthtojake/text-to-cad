import { style } from '@vanilla-extract/css';
import { sx } from '@styles/sprinkles.css';
import { vars } from '@styles/theme.css';

export const collapseRow = sx({
  display: 'flex',
  alignItems: 'center',
  gap: '1.5',
  cursor: 'pointer',
  color: 'fgPassive',
  userSelect: 'none',
});

export const collapseRowHover = style({
  selectors: {
    '&:hover': { color: vars.fgMuted },
  },
});

/** Combined class for the header row element. */
export const collapseHeader = style([
  collapseRow,
  collapseRowHover,
  { fontSize: vars.typeBodyFontSize },
]);

export const chevron = style({
  display: 'inline-block',
  fontSize: '10px',
  transition: 'transform 150ms ease-out',
});

export const chevronExpanded = style({
  transform: 'rotate(90deg)',
});

export const collapseStatusError = style({
  marginLeft: 'auto',
  display: 'flex',
  color: vars.fgError,
});

export const collapseStatusPermission = style({
  marginLeft: 'auto',
  display: 'flex',
  color: vars.planActive,
});
