import { style } from '@vanilla-extract/css';

export const card = style({
  display: 'flex',
  flexDirection: 'column',
});

export const body = style({
  display: 'flex',
  flexDirection: 'column',
});

export const section = style({
  display: 'flex',
  flexDirection: 'column',
  gap: '0.75rem',
});

// Aligns the heading with the card's inner content (card padding is 1rem).
export const sectionTitle = style({
  paddingInline: '1rem',
});
