import { mergeProps } from '@base-ui/react/merge-props';
import { useRender } from '@base-ui/react/use-render';
import { cx } from '@styles/utilities/cx';
import { badge } from './badge.css';

export type BadgeVariant = 'soft' | 'outline';
export type BadgeTone = 'neutral' | 'success' | 'warning' | 'error' | 'info';

export type BadgeProps = useRender.ComponentProps<'span'> & {
  /** Visual treatment: tinted background (soft) or hairline border (outline). */
  variant?: BadgeVariant;
  /** Semantic color; drives text plus the variant's derived background/border. */
  tone?: BadgeTone;
};

/**
 * Badge — small inline status chip.
 *
 * Polymorphic via base-ui `useRender`: pass `render` to change the underlying
 * element (defaults to `span`).
 */
function Badge({ className, variant = 'soft', tone = 'neutral', render, ...props }: BadgeProps) {
  return useRender({
    defaultTagName: 'span',
    props: mergeProps<'span'>(
      {
        className: cx(badge({ variant, tone }), className),
      },
      props
    ),
    render,
    state: {
      slot: 'badge',
      variant,
      tone,
    },
  });
}

export { Badge };
