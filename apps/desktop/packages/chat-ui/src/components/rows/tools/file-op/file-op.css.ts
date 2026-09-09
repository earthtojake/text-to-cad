import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { sx } from '@styles/sprinkles.css';
import { vars } from '@styles/theme.css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

/**
 * Contract for the file-op card vars. `height` is set on the root by the def;
 * `padY` is set locally by FileOpList / FileOpPreviewBody where it is consumed
 * via `padding-block`.
 */
export type FileOpStyleVars = {
  height: number;
  padY: number;
};

export const fileOpCardVars = createVariableThemeContract<FileOpStyleVars>({
  height: null,
  padY: null,
});

export const fileOpRoot = style({ height: fileOpCardVars.height });

export const fileRow = recipe({
  base: sx({
    display: 'flex',
    alignItems: 'center',
    gap: '1.5',
    color: 'fgPassive',
    fontSize: 'sm',
  }),
  variants: {
    clickable: {
      true: {
        cursor: 'pointer',
        selectors: {
          '&:hover': { color: vars.fgMuted },
        },
      },
      false: {},
    },
  },
});

export const fileOpHeader = style({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
  cursor: 'pointer',
  color: vars.fgPassive,
  fontSize: vars.typeBodyFontSize,
  userSelect: 'none',
  selectors: {
    '&:hover': { color: vars.fgMuted },
  },
});

export const runningLabel = style({
  fontSize: vars.typeBodyFontSize,
  color: vars.fgPassive,
});

/** Single-file op wrapper — flex row, full height. */
export const singleOpRow = style({
  display: 'flex',
  alignItems: 'center',
  gap: '6px',
});

export const fileOpStatusIcon = style({
  marginLeft: 'auto',
  display: 'inline-flex',
  flexShrink: 0,
});

export const fileOpPermissionIcon = style([
  fileOpStatusIcon,
  {
    color: vars.planActive,
  },
]);

export const fileOpErrorIcon = style([
  fileOpStatusIcon,
  {
    color: vars.fgError,
  },
]);

export const chevronSm = recipe({
  base: {
    display: 'inline-block',
    fontSize: '10px',
    transition: 'transform 150ms ease-out',
  },
  variants: {
    expanded: {
      true: { transform: 'rotate(90deg)' },
      false: {},
    },
  },
});
