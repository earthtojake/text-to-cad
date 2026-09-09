import { recipe } from '@vanilla-extract/recipes';
import type { RecipeVariants } from '@vanilla-extract/recipes';

export const icon = recipe({
  base: {
    display: 'inline-block',
    flexShrink: 0,
    color: 'currentColor',
    verticalAlign: 'middle',
  },
  variants: {
    size: {
      xs: { width: '0.75rem', height: '0.75rem' },
      sm: { width: '0.875rem', height: '0.875rem' },
      md: { width: '1rem', height: '1rem' },
      lg: { width: '1.25rem', height: '1.25rem' },
      xl: { width: '1.5rem', height: '1.5rem' },
    },
  },
  defaultVariants: {
    size: 'md',
  },
});

export type IconVariants = NonNullable<RecipeVariants<typeof icon>>;
