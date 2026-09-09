import { style } from '@vanilla-extract/css';
import { recipe } from '@vanilla-extract/recipes';
import { messageGroup } from '@components/primitives/copy-button.css';
import { vars } from '@styles/theme.css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

// ── Runtime geometry contract ─────────────────────────────────────────────────

export type AssistantStyleVars = { height: number };

export const assistantVars = createVariableThemeContract<AssistantStyleVars>({ height: null });

export const assistantRoot = style({ height: assistantVars.height });

export const messageText = recipe({
  variants: {
    role: {
      assistant: { color: vars.fgBody },
      thought: { color: vars.fgMuted, fontStyle: 'italic' },
    },
  },
});

export const assistantOuter = style([messageGroup, { position: 'relative' }]);

export const srOnly = style({
  position: 'absolute',
  width: '1px',
  height: '1px',
  padding: 0,
  margin: '-1px',
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  borderWidth: 0,
});

export const footerRow = style({
  display: 'flex',
  alignItems: 'center',
  position: 'absolute',
  bottom: 0,
  left: 0,
  right: 0,
});
