import { style } from '@vanilla-extract/css';
import { vars } from '@styles/theme.css';
import { createVariableThemeContract } from '@styles/variable-theme-contract.css';

export type GeneratedImageStyleVars = {
  gap: number;
  tileSize: number;
};

export const generatedImageVars = createVariableThemeContract<GeneratedImageStyleVars>({
  gap: null,
  tileSize: null,
});

export const generatedImageGrid = style({
  display: 'grid',
  gridTemplateColumns: `repeat(auto-fit, ${generatedImageVars.tileSize})`,
  gap: generatedImageVars.gap,
  alignContent: 'start',
  justifyContent: 'start',
  width: '100%',
  height: '100%',
  overflow: 'hidden',
});

export const generatedImageButton = style({
  display: 'block',
  width: generatedImageVars.tileSize,
  height: generatedImageVars.tileSize,
  padding: 0,
  margin: 0,
  overflow: 'hidden',
  border: `1px solid ${vars.border}`,
  borderRadius: vars.radiusLg,
  background: vars.bg1,
  cursor: 'pointer',
  lineHeight: 0,
  transition: 'border-color 120ms ease, background-color 120ms ease',
  selectors: {
    '&:hover': {
      borderColor: vars.fgPassive,
      background: vars.bg2,
    },
    '&:focus-visible': {
      outline: `2px solid ${vars.link}`,
      outlineOffset: '2px',
    },
  },
});

export const generatedImage = style({
  display: 'block',
  width: '100%',
  height: '100%',
  objectFit: 'contain',
});

export const generatedImagePlaceholder = style({
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  justifyContent: 'center',
  gap: '8px',
  width: generatedImageVars.tileSize,
  height: generatedImageVars.tileSize,
  boxSizing: 'border-box',
  border: `1px solid ${vars.border}`,
  borderRadius: vars.radiusLg,
  background: vars.bg1,
  color: vars.fgMuted,
  fontFamily: vars.fontSans,
  fontSize: vars.typeBodyFontSize,
  textAlign: 'center',
});

export const generatedImagePlaceholderIcon = style({
  display: 'inline-flex',
  color: vars.fgPassive,
});
