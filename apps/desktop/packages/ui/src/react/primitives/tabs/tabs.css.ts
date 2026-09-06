import { globalStyle, style } from '@vanilla-extract/css';

/** TabsList container strip. */
export const tabsList = style({
  display: 'inline-flex',
  alignItems: 'center',
  gap: '2px',
  selectors: {
    '&[data-orientation="vertical"]': {
      flexDirection: 'column',
      alignItems: 'stretch',
      gap: '1px',
    },
  },
});

/**
 * Tabs use the shared ghost-control sizing and focus treatment, but remain
 * visually flat. Selection is communicated through foreground emphasis rather
 * than button-like surface fills.
 */
export const tab = style({
  backgroundColor: 'transparent',
});

globalStyle(`${tab}:hover`, { backgroundColor: 'transparent' });
globalStyle(`${tab}[data-selected]`, { backgroundColor: 'transparent' });
globalStyle(`${tab}[aria-selected='true']`, { backgroundColor: 'transparent' });
globalStyle(`${tab}[data-active='true']`, { backgroundColor: 'transparent' });

/** TabsPanel — only needs outline:none (focus). */
export const tabsPanel = style({
  outline: 'none',
});
