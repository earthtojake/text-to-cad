import type { CatalogSkill } from '@emdash/core/primitives/skills/api';
import { parseFrontmatter } from '@emdash/core/primitives/skills/api';
import { Markdown } from '@emdash/ui/react/components';
import { Button, Dialog } from '@emdash/ui/react/primitives';
import { useQuery } from '@tanstack/react-query';
import { FolderOpen, Trash2 } from 'lucide-react';
import React, { useCallback, useState } from 'react';
import { getCatalogClient } from '@core/features/catalog/api/browser/client';
import { useModalController } from '@core/manifests/browser/modal-api';
import { useMarkdownLinkOpener } from '@core/primitives/external-links/browser';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import { useCloseGuard } from '@core/primitives/modals/react/use-close-guard';
import { SkillIconRenderer } from './SkillIconRenderer';

const sourceMeta = {
  openai: { name: 'OpenAI', icon: 'https://github.com/openai.png' },
  anthropic: { name: 'Anthropic', icon: 'https://github.com/anthropics.png' },
  skillssh: { name: 'Skills.sh', icon: 'https://skills.sh/favicon.ico' },
} as const;

export interface SkillDetailModalProps {
  skill: CatalogSkill;
  onInstall: (skillId: string) => Promise<boolean>;
  onUninstall: (skillId: string) => Promise<boolean>;
  onOpenTerminal?: (skillPath: string) => void;
}

export const SkillDetailModal: React.FC<SkillDetailModalProps> = ({
  skill,
  onInstall,
  onUninstall,
  onOpenTerminal,
}) => {
  const { dismiss } = useModalController('skillDetailModal');
  const [isProcessing, setIsProcessing] = useState(false);
  const { data: detailedSkill = skill, isFetching: isLoading } = useQuery({
    queryKey: ['skills', 'detail', skill.id],
    queryFn: async () => {
      const client = await getCatalogClient();
      const result = await client.getSkillContent({ skillId: skill.id });
      if (result.success) return result.data;
      throw new Error(result.error.message);
    },
    placeholderData: skill,
  });

  useCloseGuard(isProcessing);

  const handleInstall = useCallback(async () => {
    setIsProcessing(true);
    try {
      const success = await onInstall(detailedSkill.id);
      if (success) dismiss();
    } finally {
      setIsProcessing(false);
    }
  }, [detailedSkill.id, dismiss, onInstall]);

  const handleUninstall = useCallback(async () => {
    setIsProcessing(true);
    try {
      const success = await onUninstall(detailedSkill.id);
      if (success) dismiss();
    } finally {
      setIsProcessing(false);
    }
  }, [detailedSkill.id, dismiss, onUninstall]);

  const handleOpen = useCallback(() => {
    if (detailedSkill.localPath && onOpenTerminal) {
      onOpenTerminal(detailedSkill.localPath);
    }
  }, [detailedSkill.localPath, onOpenTerminal]);

  const openLink = useMarkdownLinkOpener();

  const body = detailedSkill.skillMdContent
    ? parseFrontmatter(detailedSkill.skillMdContent).body.trim()
    : '';
  const visibleBody = isSkillShPathBody(body) ? '' : body;
  const meta = detailedSkill.source === 'local' ? null : sourceMeta[detailedSkill.source];
  const showLoadingContent = isLoading && !detailedSkill.skillMdContent;

  return (
    <>
      <Dialog.Header>
        <div className="flex items-center gap-3">
          <SkillIconRenderer skill={detailedSkill} />
          <div className="min-w-0 flex-1">
            <Dialog.Title className="font-sans text-base tracking-normal text-foreground normal-case">
              {detailedSkill.displayName}
            </Dialog.Title>
            {meta && (
              <div className="mt-0.5 flex items-center gap-1.5 text-xs text-foreground-muted">
                <img src={meta.icon} alt="" className="h-4 w-4 rounded-sm" />
                <span>From {meta.name} skill library</span>
              </div>
            )}
          </div>
        </div>
      </Dialog.Header>
      <Dialog.Body>
        {showLoadingContent && <SkillDetailShimmer />}

        {!showLoadingContent && detailedSkill.defaultPrompt && (
          <div className="space-y-1 rounded-md bg-background-2/40 pb-2">
            <p className="text-xs font-medium text-foreground-muted">Example prompt</p>
            <pre className="text-xs wrap-break-word whitespace-pre-wrap text-foreground">
              {detailedSkill.defaultPrompt}
            </pre>
          </div>
        )}

        {!showLoadingContent && visibleBody && (
          <Markdown
            content={visibleBody}
            variant="compact"
            className="rounded-md bg-background-2/20 px-3 py-2 text-xs text-foreground-muted"
            onOpenLink={openLink}
          />
        )}
      </Dialog.Body>

      <Dialog.Footer className="gap-2 sm:gap-2">
        {detailedSkill.installed && (
          <>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => void handleUninstall()}
              disabled={isProcessing}
              className="text-foreground-destructive hover:text-foreground-destructive"
            >
              <Trash2 className="mr-1.5 h-3.5 w-3.5" />
              Uninstall
            </Button>
            {detailedSkill.localPath && onOpenTerminal && (
              <Button variant="secondary" size="sm" onClick={handleOpen}>
                <FolderOpen className="mr-1.5 h-3.5 w-3.5" />
                Open
              </Button>
            )}
          </>
        )}
        {!detailedSkill.installed && (
          <ConfirmButton
            variant="primary"
            size="sm"
            onClick={() => void handleInstall()}
            disabled={isProcessing}
          >
            {isProcessing ? 'Installing...' : 'Install'}
          </ConfirmButton>
        )}
      </Dialog.Footer>
    </>
  );
};

export const skillDetailModal = defineModal<void>()({
  id: 'skillDetailModal',
  component: SkillDetailModal,
  size: 'lg',
});

function isSkillShPathBody(body: string): boolean {
  return /^\.\.\/.*\/SKILL\.md$/.test(body);
}

function SkillDetailShimmer() {
  const lineClass = 'h-3 animate-pulse rounded-full bg-foreground/10';

  return (
    <div
      className="min-h-32 space-y-4 rounded-md border border-border bg-background-quaternary-1 px-3 py-3"
      aria-label="Loading skill details"
    >
      <div className="space-y-2">
        <div className={`${lineClass} w-24`} />
        <div className={`${lineClass} w-full`} />
        <div className={`${lineClass} w-5/6`} />
      </div>
      <div className="space-y-2">
        <div className={`${lineClass} w-32`} />
        <div className={`${lineClass} w-11/12`} />
        <div className={`${lineClass} w-2/3`} />
      </div>
    </div>
  );
}
