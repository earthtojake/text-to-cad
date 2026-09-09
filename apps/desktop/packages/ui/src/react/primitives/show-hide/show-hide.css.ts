import { style } from '@vanilla-extract/css';

/**
 * The wrapper contributes no layout box of its own when visible
 * (display: contents) and removes the subtree from layout entirely when
 * hidden, without unmounting it.
 */
export const root = style({
  display: 'contents',
  selectors: {
    '&[data-hidden]': { display: 'none' },
  },
});
