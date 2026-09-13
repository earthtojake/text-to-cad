import type { HostRef } from '@emdash/core/primitives/host/api';
import { isValidSkillName } from '@emdash/core/primitives/skills/api';
import { Button, Dialog, Input, Label, Textarea } from '@emdash/ui/react/primitives';
import { useQueryClient } from '@tanstack/react-query';
import React, { useState } from 'react';
import { useModalController } from '@core/manifests/browser/modal-api';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import { useCloseGuard } from '@core/primitives/modals/react/use-close-guard';
import { captureTelemetry } from '@core/primitives/telemetry/browser/telemetry-client';
import { getSkillsClient } from '../client';

export function CreateSkillModal({ host }: { host: HostRef }) {
  const { complete, dismiss } = useModalController('createSkillModal');
  const queryClient = useQueryClient();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [content, setContent] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);

  useCloseGuard(isCreating);

  const handleCreateSkill = async () => {
    setCreateError(null);

    const trimmedName = name.trim();
    if (!isValidSkillName(trimmedName)) {
      setCreateError('Name must be lowercase letters, numbers, and hyphens (2-64 chars).');
      return;
    }
    if (!description.trim()) {
      setCreateError('Description is required.');
      return;
    }

    setIsCreating(true);
    try {
      const client = await getSkillsClient();
      const result = await client.create({
        host,
        name: trimmedName,
        description: description.trim(),
        content: content.trim(),
      });

      if (!result.success) {
        setCreateError(result.error.message || 'Failed to create skill');
        return;
      }

      captureTelemetry('skill_created');
      complete();
      void queryClient.invalidateQueries({ queryKey: ['skills', 'catalog'] });
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : 'Failed to create skill');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <>
      <Dialog.Header>
        <div className="flex flex-col gap-0.5">
          <Dialog.Title>New Skill</Dialog.Title>
        </div>
      </Dialog.Header>

      <Dialog.Body>
        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="skill-name">Name</Label>
            <Input
              id="skill-name"
              placeholder="my-skill"
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setCreateError(null);
              }}
              className="text-sm"
            />
            <p className="text-micro text-foreground-muted">
              Lowercase letters, numbers, and hyphens
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="skill-desc">Description</Label>
            <Input
              id="skill-desc"
              placeholder="What does this skill do?"
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setCreateError(null);
              }}
              className="text-sm"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="skill-content">Instructions</Label>
            <Textarea
              id="skill-content"
              placeholder="Write the skill instructions here. The YAML frontmatter (name and description) will be added automatically."
              value={content}
              onChange={(e) => {
                setContent(e.target.value);
                setCreateError(null);
              }}
              className="field-sizing-fixed h-64 max-h-[40dvh] resize-y overflow-y-auto font-mono text-sm"
            />
            <p className="text-micro text-foreground-muted">
              Define what this skill does and how agents should use it
            </p>
          </div>

          {createError && <p className="text-xs text-foreground-destructive">{createError}</p>}
        </div>
      </Dialog.Body>

      <Dialog.Footer className="gap-2 sm:gap-2">
        <Button type="button" variant="secondary" size="sm" onClick={dismiss} disabled={isCreating}>
          Cancel
        </Button>
        <ConfirmButton
          variant="primary"
          type="button"
          onClick={() => void handleCreateSkill()}
          size="sm"
          disabled={isCreating}
        >
          {isCreating ? 'Creating...' : 'Create'}
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
}

export const createSkillModal = defineModal<void>()({
  id: 'createSkillModal',
  component: CreateSkillModal,
});
