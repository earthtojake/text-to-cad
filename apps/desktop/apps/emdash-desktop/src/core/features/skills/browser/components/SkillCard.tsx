import type { CatalogSkill } from '@emdash/core/primitives/skills/api';
import { CardGridItem } from '@emdash/ui/react/components';
import { Button, Tooltip } from '@emdash/ui/react/primitives';
import { Plus, Trash2 } from 'lucide-react';
import React from 'react';
import { SkillIconRenderer } from './SkillIconRenderer';

interface SkillCardProps {
  skill: CatalogSkill;
  isInstalled: boolean;
  onInstall: (skillId: string) => void;
  onUninstall: (skillId: string) => void;
  onClick: () => void;
}

export const SkillCard: React.FC<SkillCardProps> = ({
  skill,
  isInstalled,
  onInstall,
  onUninstall,
  onClick,
}) => {
  return (
    <CardGridItem role="button" tabIndex={0} onClick={onClick} className="group relative">
      <SkillIconRenderer skill={skill} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <h3 className="text-md truncate">{skill.displayName}</h3>
        <p className="mt-0.5 line-clamp-1 text-xs text-foreground-muted">{skill.description}</p>
      </div>
      <div className="absolute top-1/2 right-2 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100">
        <Tooltip.Root>
          <Tooltip.Trigger
            render={
              <Button
                size="sm"
                icon
                variant="ghost"
                onClick={(e: React.MouseEvent<HTMLButtonElement>) => {
                  e.stopPropagation();
                  if (isInstalled) {
                    onUninstall(skill.id);
                  } else {
                    onInstall(skill.id);
                  }
                }}
              >
                {isInstalled ? <Trash2 className="h-4 w-4" /> : <Plus className="h-4 w-4" />}
              </Button>
            }
          />
          <Tooltip.Content>{isInstalled ? 'Uninstall' : 'Install'}</Tooltip.Content>
        </Tooltip.Root>
      </div>
    </CardGridItem>
  );
};
