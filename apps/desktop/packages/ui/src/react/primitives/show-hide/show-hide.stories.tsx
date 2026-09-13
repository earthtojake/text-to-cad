import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import { Input } from '@react/primitives/input';
import { Text } from '@react/primitives/typography/Text';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { ShowHide } from '.';

const meta: Meta = {
  title: 'Primitives/ShowHide',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

export const StatePreservation: Story = {
  render: function StatePreservationStory() {
    const [tab, setTab] = useState<'first' | 'second'>('first');
    return (
      <Box display="flex" flexDirection="column" gap="3" style={{ width: '20rem' }}>
        <Text variant="description" tone="muted">
          Both panels stay mounted — type in an input, switch tabs, and switch back: the text is
          preserved.
        </Text>
        <Box display="flex" gap="2">
          <Button
            size="sm"
            variant={tab === 'first' ? 'primary' : 'secondary'}
            onClick={() => setTab('first')}
          >
            First
          </Button>
          <Button
            size="sm"
            variant={tab === 'second' ? 'primary' : 'secondary'}
            onClick={() => setTab('second')}
          >
            Second
          </Button>
        </Box>
        <ShowHide visible={tab === 'first'}>
          <Input placeholder="First panel input" />
        </ShowHide>
        <ShowHide visible={tab === 'second'}>
          <Input placeholder="Second panel input" />
        </ShowHide>
      </Box>
    );
  },
};

function MountTimestamp() {
  const [mountedAt] = useState(() => new Date().toLocaleTimeString());
  return <Text variant="description">Mounted at {mountedAt}</Text>;
}

export const Lazy: Story = {
  render: function LazyStory() {
    const [visible, setVisible] = useState(false);
    return (
      <Box display="flex" flexDirection="column" gap="3" style={{ width: '22rem' }}>
        <Text variant="description" tone="muted">
          With `lazy`, children stay unmounted until the first time they become visible; after that
          they stay mounted (the timestamp doesn't change when re-shown).
        </Text>
        <Button size="sm" onClick={() => setVisible((v) => !v)}>
          {visible ? 'Hide' : 'Show'} lazy content
        </Button>
        <ShowHide visible={visible} lazy>
          <MountTimestamp />
        </ShowHide>
      </Box>
    );
  },
};
