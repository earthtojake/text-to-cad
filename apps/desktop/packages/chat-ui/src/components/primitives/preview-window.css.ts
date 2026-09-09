import { recipe } from '@vanilla-extract/recipes';

export const overlay = recipe({
  base: {
    pointerEvents: 'none',
    position: 'absolute',
    left: 0,
    right: 0,
    zIndex: 10,
  },
  variants: {
    position: {
      top: { top: 0 },
      bottom: { bottom: 0 },
    },
  },
});
