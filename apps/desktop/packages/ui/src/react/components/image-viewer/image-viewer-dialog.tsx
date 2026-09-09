import { Dialog } from '@/react/primitives/dialog';
import { ContainedImage } from './contained-image';
import { ZoomViewerDialog } from './zoom-viewer-dialog';
import * as styles from './image-viewer.css';

export interface ImageViewerDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Data URL of the image to display; absent when bytes could not be resolved. */
  src?: string;
  /** Accessible name for the image and dialog. */
  alt?: string;
}

/** Pan/zoom viewer dialog for a single image. */
export function ImageViewerDialog({ open, onOpenChange, src, alt }: ImageViewerDialogProps) {
  if (!src) {
    return (
      <Dialog.Root open={open} onOpenChange={onOpenChange}>
        <Dialog.Content size="xl">
          <Dialog.Header>
            <Dialog.Title>{alt ?? 'Image'}</Dialog.Title>
          </Dialog.Header>
          <div className={styles.unavailableContainer}>
            <p className={styles.unavailable}>Image content unavailable.</p>
          </div>
        </Dialog.Content>
      </Dialog.Root>
    );
  }

  const imageAlt = alt ?? 'Image';

  return (
    <ZoomViewerDialog
      open={open}
      onOpenChange={onOpenChange}
      ariaLabel={`Image: ${imageAlt}`}
      contentKey={`${src}:${imageAlt}`}
    >
      {({ fitToView }) => (
        <ContainedImage
          src={src}
          alt={imageAlt}
          className={styles.zoomTargetImage}
          onLoad={() => fitToView()}
        />
      )}
    </ZoomViewerDialog>
  );
}
