import { ExpandableImage } from '@emdash/ui/react/components';

interface ImageRendererProps {
  file: { path: string; content: string };
}

/** Renders raster image files (png, jpg, gif, webp, ico, bmp). */
export function ImageRenderer({ file }: ImageRendererProps) {
  const fileName = file.path.split('/').pop() ?? file.path;

  return (
    <div className="flex h-full items-center justify-center overflow-auto p-4">
      <ExpandableImage
        src={file.content}
        alt={fileName}
        containerClassName="max-h-full max-w-full"
        className="max-h-full max-w-full"
      />
    </div>
  );
}
