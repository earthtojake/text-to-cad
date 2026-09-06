import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { RocketIcon } from 'lucide-react';
import { toast, Toaster } from '.';

const meta: Meta = {
  title: 'Primitives/Toast',
  parameters: { layout: 'centered' },
  decorators: [
    (Story) => (
      <>
        <Story />
        <Toaster />
      </>
    ),
  ],
};

export default meta;
type Story = StoryObj;

export const Tones: Story = {
  render: () => (
    <Box display="flex" gap="2">
      <Button variant="secondary" onClick={() => toast('Task created')}>
        Neutral
      </Button>
      <Button variant="secondary" onClick={() => toast.success('Changes committed')}>
        Success
      </Button>
      <Button
        variant="secondary"
        onClick={() => toast.error('Could not push', { description: 'Remote rejected the ref.' })}
      >
        Error
      </Button>
      <Button
        variant="secondary"
        onClick={() =>
          toast.warning('Worktree is dirty', { description: 'Stash or commit first.' })
        }
      >
        Warning
      </Button>
      <Button variant="secondary" onClick={() => toast.info('Update available')}>
        Info
      </Button>
    </Box>
  ),
};

export const WithDescription: Story = {
  render: () => (
    <Button
      variant="secondary"
      onClick={() =>
        toast('Workspace archived', {
          description: 'You can restore it from the project settings at any time.',
        })
      }
    >
      Title + description
    </Button>
  ),
};

export const WithAction: Story = {
  render: () => (
    <Button
      variant="secondary"
      onClick={() =>
        toast('Update Available', {
          description: 'Version 1.2.3 is ready to download and install.',
          duration: 10_000,
          action: { label: 'Update', onClick: () => toast.success('Updating…') },
        })
      }
    >
      With action
    </Button>
  ),
};

export const WithCustomIcon: Story = {
  render: () => (
    <Button
      variant="secondary"
      onClick={() => toast('Deployed to production', { icon: <RocketIcon size={16} /> })}
    >
      Custom icon
    </Button>
  ),
};

export const PromiseToast: Story = {
  render: () => (
    <Box display="flex" gap="2">
      <Button
        variant="secondary"
        onClick={() =>
          toast.promise(
            new Promise<string>((resolve) => setTimeout(() => resolve('v2.1.0'), 2000)),
            {
              loading: 'Fetching latest version…',
              success: (version) => `Latest version: ${version}`,
              error: 'Could not fetch latest version',
            }
          )
        }
      >
        Resolving promise
      </Button>
      <Button
        variant="secondary"
        onClick={() =>
          toast.promise(new Promise((_, reject) => setTimeout(() => reject(new Error()), 2000)), {
            loading: 'Uninstalling…',
            success: 'Uninstalled',
            error: 'Uninstall failed',
          })
        }
      >
        Rejecting promise
      </Button>
    </Box>
  ),
};

export const UpdateInPlaceAndDismiss: Story = {
  render: () => (
    <Box display="flex" gap="2">
      <Button
        variant="secondary"
        onClick={() => toast('Working…', { id: 'progress', duration: 60_000 })}
      >
        Raise (id: progress)
      </Button>
      <Button variant="secondary" onClick={() => toast.success('Done', { id: 'progress' })}>
        Update in place
      </Button>
      <Button variant="secondary" onClick={() => toast.dismiss()}>
        Dismiss all
      </Button>
    </Box>
  ),
};
