import { cx } from '@styles/utilities/cx';
import { ExpandIcon } from 'lucide-react';
import * as React from 'react';
import { Button } from '@/react/primitives/button';
import { ContainedImage } from './contained-image';
import { ZoomViewerDialog } from './zoom-viewer-dialog';
import * as styles from './image-viewer.css';

export interface ExpandableImageProps extends React.ComponentPropsWithoutRef<'img'> {
  /** Class applied to the wrapping inline container rather than the image. */
  containerClassName?: string;
}

/**
 * A contained image with a hover-revealed expand affordance that opens the
 * pan/zoom viewer dialog. The dialog renders lazily on first expand and stays
 * mounted afterwards so reopening is instant.
 */
export function ExpandableImage({
  className,
  containerClassName,
  src,
  alt,
  ...props
}: ExpandableImageProps) {
  const [isExpanded, setIsExpanded] = React.useState(false);
  const hasBeenOpenedRef = React.useRef(false);
  const imageAlt = alt ?? '';

  if (!src) {
    return <ContainedImage src={src} alt={imageAlt} className={className} {...props} />;
  }

  const openViewer = (event: React.MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    hasBeenOpenedRef.current = true;
    setIsExpanded(true);
  };

  const shouldRenderDialog = isExpanded || hasBeenOpenedRef.current;

  return (
    <span className={cx(styles.expandableContainer, containerClassName)}>
      <Button
        type="button"
        variant="secondary"
        size="xs"
        icon
        aria-label="Expand image"
        title="Expand image"
        className={styles.expandButton}
        onClick={openViewer}
      >
        <ExpandIcon style={{ width: '0.75rem', height: '0.75rem' }} />
      </Button>
      <ContainedImage src={src} alt={imageAlt} className={className} {...props} />
      {shouldRenderDialog && (
        <ZoomViewerDialog
          open={isExpanded}
          onOpenChange={setIsExpanded}
          ariaLabel={imageAlt ? `Image: ${imageAlt}` : 'Image'}
          contentKey={`${src}:${imageAlt}`}
        >
          {({ fitToView }) => (
            <ContainedImage
              src={src}
              alt={imageAlt}
              className={cx(className, styles.zoomTargetImage)}
              {...props}
              onLoad={(event) => {
                props.onLoad?.(event);
                fitToView();
              }}
            />
          )}
        </ZoomViewerDialog>
      )}
    </span>
  );
}
