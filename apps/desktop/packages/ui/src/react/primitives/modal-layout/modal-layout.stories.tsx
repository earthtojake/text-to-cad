import { Box } from '@react/primitives/box';
import { Button } from '@react/primitives/button';
import { Dialog } from '@react/primitives/dialog';
import { Input } from '@react/primitives/input';
import { Text } from '@react/primitives/typography/Text';
import type { Meta, StoryObj } from '@storybook/react-vite';
import { useState } from 'react';
import { ModalLayout } from '.';

const meta: Meta = {
  title: 'Primitives/ModalLayout',
  parameters: { layout: 'centered' },
};

export default meta;
type Story = StoryObj;

function SteppedModalContent() {
  const [step, setStep] = useState<1 | 2>(1);
  return (
    <ModalLayout
      header={
        <Dialog.Header>
          <Dialog.Title>{step === 1 ? 'Choose a name' : 'Confirm details'}</Dialog.Title>
        </Dialog.Header>
      }
      footer={
        <Dialog.Footer>
          {step === 2 && (
            <Button variant="ghost" onClick={() => setStep(1)}>
              Back
            </Button>
          )}
          {step === 1 ? (
            <Button variant="primary" onClick={() => setStep(2)}>
              Next
            </Button>
          ) : (
            <Dialog.Close render={<Button variant="primary">Create</Button>} />
          )}
        </Dialog.Footer>
      }
    >
      <Dialog.Body>
        {step === 1 ? (
          <Input placeholder="Project name" />
        ) : (
          <Box display="flex" flexDirection="column" gap="2">
            <Text variant="description">
              The header and footer stay put while this middle section height-animates between
              steps.
            </Text>
            <Text variant="description" tone="muted">
              Step two intentionally has taller content than step one, so switching steps shows the
              animated middle expanding and collapsing.
            </Text>
          </Box>
        )}
      </Dialog.Body>
    </ModalLayout>
  );
}

export const SteppedComposition: Story = {
  render: () => (
    <Dialog.Root>
      <Dialog.Trigger render={<Button variant="ghost">Open stepped modal</Button>} />
      <Dialog.Content>
        <SteppedModalContent />
      </Dialog.Content>
    </Dialog.Root>
  ),
};
