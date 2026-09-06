import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { Box } from '@/react/primitives/box';
import { Button } from '@/react/primitives/button';
import { ContainedImage } from './contained-image';
import { ExpandableImage } from './expandable-image';
import { ImageViewerDialog } from './image-viewer-dialog';
import { ZoomViewerDialog } from './zoom-viewer-dialog';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Components/ImageViewer',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

const sampleSvg = `
<svg xmlns="http://www.w3.org/2000/svg" width="640" height="400" viewBox="0 0 640 400">
  <defs>
    <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#3b82f6"/>
      <stop offset="1" stop-color="#a855f7"/>
    </linearGradient>
  </defs>
  <rect width="640" height="400" fill="url(#g)" rx="16"/>
  <circle cx="180" cy="160" r="70" fill="#fbbf24"/>
  <rect x="330" y="90" width="200" height="140" fill="#ffffff" opacity="0.85" rx="12"/>
  <text x="320" y="330" font-size="28" font-family="sans-serif" fill="#ffffff" text-anchor="middle">
    640 x 400 sample image
  </text>
</svg>`;

const sampleImageSrc = `data:image/svg+xml;charset=utf-8,${encodeURIComponent(sampleSvg)}`;

function ExpandableStory() {
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="3">
      <p className={sx({ fontSize: 'xs', color: 'foregroundMuted' })}>
        Hover the image to reveal the expand affordance; expanding opens the zoom dialog.
      </p>
      <ExpandableImage src={sampleImageSrc} alt="Sample gradient" style={{ width: 320 }} />
    </Box>
  );
}

function ImageDialogStory({ src }: { src?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        Open image viewer
      </Button>
      <ImageViewerDialog open={open} onOpenChange={setOpen} src={src} alt="Sample gradient" />
    </>
  );
}

function ArbitraryContentStory() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        Open SVG viewer
      </Button>
      <ZoomViewerDialog
        open={open}
        onOpenChange={setOpen}
        ariaLabel="Diagram: flow chart"
        contentKey="story-inline-svg"
      >
        <div dangerouslySetInnerHTML={{ __html: sampleSvg }} />
      </ZoomViewerDialog>
    </>
  );
}

function ContainedStory() {
  return (
    <div style={{ width: 240, height: 120, border: '1px dashed currentColor' }}>
      <ContainedImage
        src={sampleImageSrc}
        alt="Sample gradient"
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
}

export const Expandable: Story = { render: () => <ExpandableStory /> };
export const ImageDialog: Story = {
  name: 'Image dialog',
  render: () => <ImageDialogStory src={sampleImageSrc} />,
};
export const ImageUnavailable: Story = {
  name: 'Image unavailable',
  render: () => <ImageDialogStory />,
};
export const ArbitraryContent: Story = {
  name: 'Arbitrary content (inline SVG)',
  render: () => <ArbitraryContentStory />,
};
export const Contained: Story = { render: () => <ContainedStory /> };
