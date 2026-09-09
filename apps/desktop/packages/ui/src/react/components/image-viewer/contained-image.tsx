import { cx } from '@styles/utilities/cx';
import * as React from 'react';
import * as styles from './image-viewer.css';

export type ContainedImageProps = React.ComponentPropsWithoutRef<'img'>;

/** An `<img>` that letterboxes into its box (`object-fit: contain`). */
export function ContainedImage({ className, alt, ...props }: ContainedImageProps) {
  return <img alt={alt ?? ''} className={cx(styles.containedImage, className)} {...props} />;
}
