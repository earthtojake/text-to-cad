/**
 * sprinkles.css.ts — atomic CSS utilities replacing Tailwind.
 *
 * Covers the recurring utility patterns in ~25 chat-ui components.
 * Component-specific one-off rules use VE style() / recipe() directly
 * in companion *.css.ts files.
 *
 * Usage:
 *   import { sx } from '../../styles/sprinkles.css';
 *   class={sx({ display: 'flex', alignItems: 'center', color: 'fgMuted' })}
 */

import { createSprinkles, defineProperties } from '@vanilla-extract/sprinkles';
import { vars } from './theme.css';

// ── Layout ────────────────────────────────────────────────────────────────────

const layoutProps = defineProperties({
  properties: {
    display: ['flex', 'grid', 'block', 'inline-block', 'inline-flex', 'none'],
    flexDirection: ['row', 'row-reverse', 'column', 'column-reverse'],
    alignItems: ['stretch', 'flex-start', 'center', 'flex-end', 'baseline'],
    justifyContent: ['stretch', 'flex-start', 'center', 'flex-end', 'space-between'],
    flexWrap: ['nowrap', 'wrap'],
    flex: { '1': '1 1 0%', none: 'none', auto: '1 1 auto' },
    flexShrink: { 0: 0, 1: 1 },
    flexGrow: { 0: 0, 1: 1 },
    position: ['static', 'relative', 'absolute', 'sticky', 'fixed'],
    overflow: ['visible', 'hidden', 'auto', 'scroll'],
    overflowX: ['visible', 'hidden', 'auto'],
    overflowY: ['visible', 'hidden', 'auto'],
    width: {
      full: '100%',
      auto: 'auto',
      '0': '0',
    },
    height: {
      full: '100%',
      auto: 'auto',
      '0': '0',
    },
    minWidth: {
      '0': '0',
      full: '100%',
    },
    maxWidth: {
      full: '100%',
      none: 'none',
      '150': '150px',
    },
    inset: {
      '0': '0',
    },
    top: { '0': '0', auto: 'auto' },
    right: { '0': '0', auto: 'auto' },
    bottom: { '0': '0', auto: 'auto' },
    left: { '0': '0', auto: 'auto' },
    zIndex: { '0': 0, '10': 10, '20': 20 },
    pointerEvents: ['none', 'auto', 'all'],
  },
});

// ── Spacing ───────────────────────────────────────────────────────────────────

const SPACE = {
  '0': '0',
  '0.5': '2px',
  '1': '4px',
  '1.5': '6px',
  '2': '8px',
  '2.5': '10px',
  '3': '12px',
  '4': '16px',
  '5': '20px',
  '6': '24px',
  '8': '32px',
} as const;

const spacingProps = defineProperties({
  properties: {
    padding: SPACE,
    paddingTop: SPACE,
    paddingBottom: SPACE,
    paddingLeft: SPACE,
    paddingRight: SPACE,
    gap: SPACE,
    columnGap: SPACE,
    rowGap: SPACE,
    marginTop: SPACE,
    marginBottom: SPACE,
  },
});

// ── Typography ─────────────────────────────────────────────────────────────────

const typographyProps = defineProperties({
  properties: {
    fontSize: {
      '9': '9px',
      '10': '10px',
      '11': '11px',
      '12': '12px',
      '13': '13px',
      '14': '14px',
      '17': '17px',
      '20': '20px',
      xs: '0.75rem',
      sm: '0.875rem',
    },
    fontWeight: {
      normal: 400,
      medium: 500,
      semibold: 600,
      bold: 700,
    },
    lineHeight: {
      none: 1,
      tight: 1.25,
      normal: 1.5,
    },
    whiteSpace: ['nowrap', 'pre', 'normal', 'pre-wrap'],
    textOverflow: ['ellipsis', 'clip'],
    userSelect: ['none', 'auto', 'all', 'text'],
    cursor: ['default', 'pointer', 'text', 'not-allowed'],
  },
});

// ── Colors ────────────────────────────────────────────────────────────────────

const colorProps = defineProperties({
  properties: {
    color: {
      inherit: 'inherit',
      current: 'currentColor',
      white: '#fff',
      fg: vars.fg,
      fgBody: vars.fgBody,
      fgMuted: vars.fgMuted,
      fgPassive: vars.fgPassive,
      link: vars.link,
      diffAdded: vars.diffAdded,
      diffDeleted: vars.diffDeleted,
      diffModified: vars.diffModified,
      planDone: vars.planDone,
      planActive: vars.planActive,
      mentionFg: vars.mentionFg,
      mentionChipFg: vars.mentionChipFg,
    },
    background: {
      transparent: 'transparent',
      bg: vars.bg,
      bg1: vars.bg1,
      bg2: vars.bg2,
      bg3: vars.bg3,
      userCard: vars.userCardBg,
      mentionChip: vars.mentionChipBg,
      mentionBg: vars.mentionBg,
      codeBg: vars.codeBg,
      codeInlineBg: vars.codeInlineBg,
      tableHeaderBg: vars.tableHeaderBg,
      // Opacity-blended diff backgrounds via color-mix
      diffAddedSubtle: `color-mix(in srgb, ${vars.diffAdded} 10%, transparent)`,
      diffDeletedSubtle: `color-mix(in srgb, ${vars.diffDeleted} 10%, transparent)`,
    },
    borderColor: {
      border: vars.border,
      userCardBorder: vars.userCardBorder,
      userCardBorderHover: vars.userCardBorderHover,
      diffAdded: vars.diffAdded,
      diffDeleted: vars.diffDeleted,
      transparent: 'transparent',
    },
    outlineColor: {
      border: vars.border,
    },
  },
});

// ── Borders & Radius ──────────────────────────────────────────────────────────

const borderProps = defineProperties({
  properties: {
    borderWidth: { '0': '0', '1': '1px' },
    borderTopWidth: { '0': '0', '1': '1px', '3': '3px' },
    borderBottomWidth: { '0': '0', '1': '1px', '3': '3px' },
    borderLeftWidth: { '0': '0', '1': '1px', '3': '3px' },
    borderRightWidth: { '0': '0', '1': '1px', '3': '3px' },
    borderStyle: ['solid', 'dashed', 'none'],
    borderRadius: {
      '0': '0',
      sm: vars.radiusSm,
      md: vars.radiusMd,
      lg: vars.radiusLg,
      xl: vars.radiusXl,
      full: vars.radiusFull,
      '4': '4px',
    },
    borderTopLeftRadius: {
      '0': '0',
      lg: vars.radiusLg,
    },
    borderTopRightRadius: {
      '0': '0',
      lg: vars.radiusLg,
    },
    borderBottomLeftRadius: {
      '0': '0',
      lg: vars.radiusLg,
    },
    borderBottomRightRadius: {
      '0': '0',
      lg: vars.radiusLg,
    },
    opacity: {
      '0': 0,
      '75': 0.75,
      '100': 1,
    },
  },
});

// ── Combined sprinkles function ───────────────────────────────────────────────

export const sx = createSprinkles(
  layoutProps,
  spacingProps,
  typographyProps,
  colorProps,
  borderProps
);
export type Sprinkles = Parameters<typeof sx>[0];
