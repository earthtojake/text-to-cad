import type { Meta, StoryObj } from '@storybook/react-vite';
import * as React from 'react';
import { UpdateCard, type UpdateCardProps } from './update-card';
import * as s from '@react/story-layout.css';

type StoryStatusType = 'up-to-date' | 'update-download-available' | 'update-install-available';

interface UpdateCardStoryArgs {
  currentVersion: string;
  appName: string;
  statusType: StoryStatusType;
  downloadVersion: string;
  downloadSize: number;
  error?: { message: string };
}

const meta: Meta<UpdateCardStoryArgs> = {
  title: 'Components/UpdateCard',
  parameters: { layout: 'centered' },
  argTypes: {
    statusType: {
      control: 'radio',
      options: ['up-to-date', 'update-download-available', 'update-install-available'],
    },
  },
  args: {
    currentVersion: '1.4.2',
    appName: 'Emdash',
    statusType: 'update-download-available',
    downloadVersion: '1.5.0',
    downloadSize: 42_000_000,
    error: { message: 'Network request failed' },
  },
};
export default meta;
type Story = StoryObj<UpdateCardStoryArgs>;

function buildStatus(
  statusType: StoryStatusType,
  downloadVersion: string,
  downloadSize: number
): UpdateCardProps['status'] {
  switch (statusType) {
    case 'up-to-date':
      return { type: 'up-to-date' };
    case 'update-download-available':
      return {
        type: 'update-download-available',
        version: downloadVersion,
        size: downloadSize,
        onDownload: async (onProgress) => {
          for (let progress = 0; progress <= 100; progress += 10) {
            onProgress(progress);
            await new Promise((resolve) => setTimeout(resolve, 100));
          }
        },
      };
    case 'update-install-available':
      return {
        type: 'update-install-available',
        onInstall: async () => {},
      };
  }
}

function DefaultStory(args: UpdateCardStoryArgs) {
  const { statusType, downloadVersion, downloadSize, error, ...rest } = args;
  const status = React.useMemo(
    () => buildStatus(statusType, downloadVersion, downloadSize),
    [statusType, downloadVersion, downloadSize]
  );

  return (
    <div className={s.maxW2xl}>
      <UpdateCard {...rest} status={status} error={error} onCheckForUpdates={async () => {}} />
    </div>
  );
}

export const Default: Story = {
  render: (args) => <DefaultStory {...args} />,
};

export const AllStates: Story = {
  render: () => (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', width: '32rem' }}>
      <div>
        <p
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
            marginBottom: '0.375rem',
            fontFamily: 'var(--em-font-mono)',
          }}
        >
          up-to-date
        </p>
        <div className={s.maxW2xl}>
          <UpdateCard
            currentVersion="1.4.2"
            appName="Emdash"
            status={{ type: 'up-to-date' }}
            onCheckForUpdates={async () => {}}
          />
        </div>
      </div>

      <div>
        <p
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
            marginBottom: '0.375rem',
            fontFamily: 'var(--em-font-mono)',
          }}
        >
          update-download-available
        </p>
        <div className={s.maxW2xl}>
          <UpdateCard
            currentVersion="1.4.2"
            appName="Emdash"
            status={{
              type: 'update-download-available',
              version: '1.5.0',
              size: 42_000_000,
              onDownload: async (onProgress) => {
                for (let progress = 0; progress <= 100; progress += 10) {
                  onProgress(progress);
                  await new Promise((resolve) => setTimeout(resolve, 100));
                }
              },
            }}
            onCheckForUpdates={async () => {}}
          />
        </div>
      </div>

      <div>
        <p
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
            marginBottom: '0.375rem',
            fontFamily: 'var(--em-font-mono)',
          }}
        >
          update-install-available
        </p>
        <div className={s.maxW2xl}>
          <UpdateCard
            currentVersion="1.4.2"
            appName="Emdash"
            status={{ type: 'update-install-available', onInstall: async () => {} }}
            onCheckForUpdates={async () => {}}
          />
        </div>
      </div>

      <div>
        <p
          style={{
            fontSize: 'var(--em-text-xs)',
            color: 'var(--em-foreground-muted)',
            marginBottom: '0.375rem',
            fontFamily: 'var(--em-font-mono)',
          }}
        >
          update-download-available + error
        </p>
        <div className={s.maxW2xl}>
          <UpdateCard
            currentVersion="1.4.2"
            appName="Emdash"
            status={{
              type: 'update-download-available',
              version: '1.5.0',
              size: 42_000_000,
              onDownload: async () => {},
            }}
            error={{ message: 'Network request failed' }}
            onCheckForUpdates={async () => {}}
          />
        </div>
      </div>
    </div>
  ),
};
