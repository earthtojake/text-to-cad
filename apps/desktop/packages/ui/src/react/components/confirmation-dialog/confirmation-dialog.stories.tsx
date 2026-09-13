import type { Meta, StoryObj } from '@storybook/react-vite';
import { cx } from '@styles/utilities/cx';
import { useState } from 'react';
import { Box } from '@/react/primitives/box';
import { Button } from '@/react/primitives/button';
import { ConfirmationDialog } from '.';
import { sx } from '@styles/utilities/sprinkles.css';

const meta: Meta = {
  title: 'Components/ConfirmationDialog',
  parameters: { layout: 'centered' },
};
export default meta;

type Story = StoryObj;

function NeutralStory() {
  const [open, setOpen] = useState(false);
  const [lastAction, setLastAction] = useState<string>('—');
  return (
    <Box display="flex" flexDirection="column" alignItems="center" gap="3">
      <Button variant="ghost" onClick={() => setOpen(true)}>
        Leave page
      </Button>
      <p className={cx(sx({ fontSize: 'xs', color: 'foregroundMuted' }))}>
        Last action: {lastAction}
      </p>
      <ConfirmationDialog
        open={open}
        onOpenChange={setOpen}
        title="Discard changes?"
        description="You have unsaved changes that will be lost if you leave this page."
        confirmLabel="Discard"
        cancelLabel="Keep editing"
        onConfirm={() => setLastAction('confirmed')}
        onCancel={() => setLastAction('cancelled')}
      />
    </Box>
  );
}

function DestructiveStory() {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        Delete project
      </Button>
      <ConfirmationDialog
        open={open}
        onOpenChange={setOpen}
        title="Delete project?"
        description="This permanently removes the project and all of its worktrees. This action cannot be undone."
        confirmLabel="Delete"
        tone="destructive"
        onConfirm={() => {}}
      />
    </>
  );
}

function AsyncStory() {
  const [open, setOpen] = useState(false);
  const [isConfirming, setIsConfirming] = useState(false);
  return (
    <>
      <Button variant="ghost" onClick={() => setOpen(true)}>
        Submit (async)
      </Button>
      <ConfirmationDialog
        open={open}
        onOpenChange={setOpen}
        title="Submit for review?"
        description="This sends the change for review. It may take a moment."
        confirmLabel={isConfirming ? 'Submitting…' : 'Submit'}
        isConfirming={isConfirming}
        onConfirm={async () => {
          setIsConfirming(true);
          await new Promise((r) => setTimeout(r, 1200));
          setIsConfirming(false);
        }}
      />
    </>
  );
}

export const Neutral: Story = { render: () => <NeutralStory /> };
export const Destructive: Story = { render: () => <DestructiveStory /> };
export const AsyncConfirm: Story = { name: 'Async confirm', render: () => <AsyncStory /> };
