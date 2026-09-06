import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';
import { vars } from '@theme/core/contract/contract.css';
import { tokenVars } from '@theme/tokens.css';

type CSSExtra = { [key: string]: string };

export const wrapper = style({
  position: 'sticky',
  top: 0,
  alignSelf: 'start',
  boxSizing: 'border-box',
  display: 'flex',
  minHeight: '100vh',
  maxHeight: '100vh',
  flexDirection: 'column',
  paddingTop: '2.5rem',
  paddingBottom: '0.75rem',
});

export const header = style({
  width: '13rem',
  flexShrink: 0,
  marginBottom: '0.75rem',
  ...({ WebkitAppRegion: 'no-drag' } as CSSExtra),
});

export const nav = style({
  display: 'flex',
  width: '13rem',
  flex: 1,
  flexDirection: 'column',
  gap: '0.0625rem',
  minHeight: 0,
  overflowY: 'auto',
  paddingBottom: '2.5rem',
  ...({ WebkitAppRegion: 'no-drag' } as CSSExtra),
});

export const footer = style({
  width: '13rem',
  flexShrink: 0,
  marginTop: '0.75rem',
  ...({ WebkitAppRegion: 'no-drag' } as CSSExtra),
});

export const emptyMessage = style({
  padding: '0.5rem 0.75rem',
  fontSize: tokenVars.textSm,
  color: vars.foregroundPassive,
});

export const navItem = recipe({
  base: {
    display: 'flex',
    width: '100%',
    alignItems: 'center',
    gap: '0.5rem',
    borderRadius: tokenVars.radiusMd,
    border: 'none',
    backgroundColor: 'transparent',
    paddingLeft: '0.75rem',
    paddingRight: '0.75rem',
    height: '32px',
    fontSize: tokenVars.textSm,
    fontWeight: 400,
    color: vars.foregroundMuted,
    cursor: 'pointer',
    transition: 'background-color 150ms, box-shadow 150ms, color 150ms',
    textAlign: 'left',
    selectors: {
      '&:hover': {
        backgroundColor: vars.background1,
        color: vars.foreground,
      },
    },
  },
  variants: {
    active: {
      true: {
        backgroundColor: vars.background3,
        color: vars.foreground,
        selectors: {
          '&:hover': {
            backgroundColor: vars.background3,
            color: vars.foreground,
          },
        },
      },
    },
  },
  defaultVariants: {
    active: false,
  },
});

export type NavItemVariants = NonNullable<RecipeVariants<typeof navItem>>;

// ── Icon + external-link icon ─────────────────────────────────────────────────

export const navItemIcon = style({
  color: 'inherit',
});

export const navItemLabel = style({
  flex: 1,
  minWidth: 0,
  overflow: 'hidden',
  textOverflow: 'ellipsis',
  whiteSpace: 'nowrap',
});

export const badge = style({
  marginLeft: 'auto',
  fontSize: tokenVars.textXs,
  color: vars.foregroundPassive,
  fontVariantNumeric: 'tabular-nums',
});

export const externalIcon = style({
  color: vars.foregroundMuted,
  marginLeft: 'auto',
});

// ── Divider ───────────────────────────────────────────────────────────────────

export const divider = style({
  width: '100%',
  paddingTop: '0.5rem',
  paddingBottom: '0.5rem',
  selectors: {
    '&::before': {
      content: "''",
      display: 'block',
      width: '100%',
      height: '1px',
      backgroundColor: vars.border,
    },
  },
});

export const sectionLabel = style({
  width: '100%',
  paddingTop: '1.25rem',
  paddingRight: '0.75rem',
  paddingBottom: '0.75rem',
  paddingLeft: '0.75rem',
  fontSize: tokenVars.textTiny,
  fontWeight: 400,
  lineHeight: 1,
  letterSpacing: '1.5px',
  textTransform: 'uppercase',
  color: vars.foregroundPassive,
});
