import { style } from '@vanilla-extract/css';
import { vars } from '@theme/core/contract/contract.css';
// Side-effect import so the @layer order declaration is emitted before these
// rules; otherwise `recipes` gets registered first and loses to app layers.
import '@styles/layers.css';

export const spinner = style({
  '@layer': {
    recipes: {
      color: vars.foregroundMuted,
      lineHeight: 1,
    },
  },
});
