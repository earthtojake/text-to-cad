/**
 * ComboboxPopup — standalone stories for the floating listbox primitive.
 *
 * Since ComboboxPopup anchors itself to a DOMRect, each story wraps it in a
 * button that supplies its own bounding rect as the anchor. Keyboard events
 * are forwarded through the imperative handle.
 */

import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { AtSign, Braces, CircleDot, File } from 'lucide-react';
import React, { useEffect, useRef, useState } from 'react';
import { ComboboxPopup, type ComboboxPopupHandle, type ComboboxPopupItem } from './combobox-popup';
import * as s from '@react/story-layout.css';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Primitives/ComboboxPopup',
  parameters: { layout: 'centered' },
};
export default meta;
type Story = StoryObj;

const FILE_ITEMS: ComboboxPopupItem[] = [
  {
    id: 'src/components/chat-composer.tsx',
    icon: <i className="devicon-react-original colored" style={{ fontSize: '13px' }} />,
    label: 'chat-composer.tsx',
    description: 'src/components',
  },
  {
    id: 'src/lib/file-icons.ts',
    icon: <i className="devicon-typescript-plain colored" style={{ fontSize: '13px' }} />,
    label: 'file-icons.ts',
    description: 'src/lib',
  },
  {
    id: 'package.json',
    icon: <i className="devicon-npm-original-wordmark colored" style={{ fontSize: '13px' }} />,
    label: 'package.json',
    description: '',
  },
  {
    id: 'README.md',
    icon: <i className="devicon-markdown-original" style={{ fontSize: '13px' }} />,
    label: 'README.md',
    description: '',
  },
];

const MIXED_ITEMS: ComboboxPopupItem[] = [
  { id: 'f1', icon: <File className={s.size35} />, label: 'src/utils.ts', description: 'file' },
  { id: 'i1', icon: <CircleDot className={s.size35} />, label: 'Issue #42', description: 'issue' },
  { id: 's1', icon: <Braces className={s.size35} />, label: 'handleSubmit', description: 'symbol' },
  { id: 'c1', icon: <AtSign className={s.size35} />, label: 'custom item', description: 'custom' },
];

function AnchoredPopup({
  items,
  emptyLabel,
  header,
}: {
  items: ComboboxPopupItem[];
  emptyLabel?: string;
  header?: React.ReactNode;
}) {
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const popupRef = useRef<ComboboxPopupHandle | null>(null);

  function toggle() {
    if (anchorRect) {
      setAnchorRect(null);
    } else {
      const rect = buttonRef.current?.getBoundingClientRect() ?? null;
      if (rect) setAnchorRect(new DOMRect(rect.left, rect.bottom, rect.width, 0));
    }
  }

  useEffect(() => {
    if (!anchorRect) return;
    function handleKey(e: KeyboardEvent) {
      const consumed = popupRef.current?.onKeyDown(e);
      if (consumed) e.preventDefault();
    }
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [anchorRect]);

  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="2">
      <Button ref={buttonRef} variant="ghost" size="xs" onClick={toggle}>
        {anchorRect ? 'Close popup' : 'Open popup'}
      </Button>
      <p className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))}>
        {anchorRect ? 'Arrow keys to navigate, Enter to select, Esc to dismiss' : ''}
      </p>
      <ComboboxPopup
        ref={popupRef}
        items={items}
        anchorRect={anchorRect}
        onSelect={(item) => {
          alert(`Selected: ${item.label}`);
          setAnchorRect(null);
        }}
        emptyLabel={emptyLabel}
        header={header}
      />
    </Box>
  );
}

export const FileItems: Story = {
  render: () => <AnchoredPopup items={FILE_ITEMS} />,
};

export const MixedKinds: Story = {
  render: () => <AnchoredPopup items={MIXED_ITEMS} />,
};

export const WithHeader: Story = {
  render: () => (
    <AnchoredPopup
      items={FILE_ITEMS.slice(0, 3)}
      header={<span className={cx(sx({ color: 'foreground' }))}>Context files</span>}
    />
  ),
};

export const EmptyState: Story = {
  render: () => <AnchoredPopup items={[]} emptyLabel="No matches found" />,
};
