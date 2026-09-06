import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';

export const root = style({
  display: 'flex',
});

export const separatorH = style({
  flexShrink: 0,
  width: '100%',
  height: '1px',
  backgroundColor: vars.borderSubtle,
});

export const separatorV = style({
  flexShrink: 0,
  alignSelf: 'stretch',
  width: '1px',
  height: 'auto',
  backgroundColor: vars.borderSubtle,
});
