import { Button, Dialog, Field, Input, Textarea } from '@emdash/ui/react/primitives';
import { useMemo, useState } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import type { PromptLibraryPrompt } from '@core/primitives/prompt-library/api';

export type PromptFormResult = Pick<PromptLibraryPrompt, 'title' | 'prompt'>;

type PromptModalArgs = {
  initialPrompt?: PromptLibraryPrompt | PromptFormResult;
};

type Props = PromptModalArgs;

export function PromptModal({ initialPrompt }: Props) {
  const { complete, dismiss } = useModalController('promptModal');
  const initialForm = useMemo<PromptFormResult>(
    () => ({
      title: initialPrompt?.title ?? '',
      prompt: initialPrompt?.prompt ?? '',
    }),
    [initialPrompt]
  );
  const [form, setForm] = useState(initialForm);

  const normalizedTitle = form.title.trim();
  const normalizedPrompt = form.prompt.trim();
  const canSave = normalizedTitle.length > 0 && normalizedPrompt.length > 0;

  const handleSave = () => {
    if (!canSave) return;
    complete({ title: normalizedTitle, prompt: normalizedPrompt });
  };

  return (
    <>
      <Dialog.Header>
        <Dialog.Title>{initialPrompt ? 'Edit Prompt' : 'New Prompt'}</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="gap-4 pt-0">
        <Field.Group>
          <Field.Root>
            <Field.Label>Title</Field.Label>
            <Input
              data-autofocus
              value={form.title}
              onChange={(e) => setForm((prev) => ({ ...prev, title: e.target.value }))}
              placeholder="Security review"
            />
          </Field.Root>
          <Field.Root>
            <Field.Label>Prompt</Field.Label>
            <Textarea
              value={form.prompt}
              onChange={(e) => setForm((prev) => ({ ...prev, prompt: e.target.value }))}
              placeholder="Write the prompt agents should receive."
              className="max-h-[50dvh] min-h-56 resize-y overflow-y-auto px-3 py-2.5 text-[14px] leading-relaxed"
            />
          </Field.Root>
        </Field.Group>
      </Dialog.Body>
      <Dialog.Footer>
        <Button variant="secondary" onClick={dismiss}>
          Cancel
        </Button>
        <ConfirmButton variant="primary" onClick={handleSave} disabled={!canSave}>
          Save
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
}

export const promptModal = defineModal<PromptFormResult>()({
  id: 'promptModal',
  component: PromptModal,
  size: 'lg',
});
