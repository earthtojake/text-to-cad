import { cx } from '@styles/utilities/cx';
import type { LucideProps } from 'lucide-react';
import { DynamicIcon, type IconName } from 'lucide-react/dynamic';
import * as React from 'react';
import { icon, type IconVariants } from './icon.css';

export type IconSize = NonNullable<IconVariants['size']>;

export interface IconProps extends Omit<LucideProps, 'size'> {
  /** Kebab-case Lucide icon name, such as `settings` or `external-link`. */
  name: IconName;
  /** Design-system icon size. Defaults to `md` (16px). */
  size?: IconSize;
}

/**
 * Renders a Lucide icon by name with consistent design-system sizing.
 *
 * Icons are decorative by default. Provide `aria-label` to expose an icon to
 * assistive technology.
 */
const Icon = React.forwardRef<SVGSVGElement, IconProps>(function Icon(
  { name, size = 'md', className, 'aria-label': ariaLabel, 'aria-hidden': ariaHidden, ...props },
  ref
) {
  const iconClassName = cx(icon({ size }), className);

  return (
    <DynamicIcon
      ref={ref}
      name={name}
      className={iconClassName}
      aria-label={ariaLabel}
      aria-hidden={ariaHidden ?? (ariaLabel ? undefined : true)}
      fallback={() => <span className={iconClassName} aria-hidden />}
      {...props}
    />
  );
});

export { Icon };
export type { IconName };
