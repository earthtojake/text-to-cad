import { CardGridSection } from '@emdash/ui/react/components';
import { Loader2 } from 'lucide-react';
import React, { useCallback } from 'react';
import { SkillCard } from '@core/features/skills/browser/components/SkillCard';
import type { UseSkillsResult } from '@core/features/skills/browser/components/useSkills';
import { useOpenModal } from '@core/manifests/browser/modal-api';

type SkillsListProps = {
  skills: UseSkillsResult;
  onOpenTerminal?: (skillPath: string) => void;
};

export const SkillsList: React.FC<SkillsListProps> = ({ skills, onOpenTerminal }) => {
  const openConfirm = useOpenModal('confirmActionModal');
  const openSkillDetail = useOpenModal('skillDetailModal');

  const handleUninstallRequest = useCallback(
    async (skillId: string): Promise<boolean> => {
      const displayName =
        skills.catalog?.skills.find((skill) => skill.id === skillId)?.displayName ?? skillId;
      const outcome = await openConfirm({
        title: 'Uninstall skill?',
        description: `This will uninstall "${displayName}" from all agents. This action cannot be undone.`,
        confirmLabel: 'Uninstall',
      });
      if (!outcome.success) return false;
      return skills.uninstall(skillId);
    },
    [openConfirm, skills]
  );

  const handleOpenDetail = useCallback(
    (skill: UseSkillsResult['filteredSkills'][number]) => {
      void openSkillDetail({
        skill,
        onInstall: skills.install,
        onUninstall: handleUninstallRequest,
        onOpenTerminal,
      });
    },
    [handleUninstallRequest, onOpenTerminal, openSkillDetail, skills.install]
  );

  if (skills.isLoading) {
    return (
      <div className="flex min-h-64 items-center justify-center text-foreground">
        <Loader2 className="h-6 w-6 animate-spin text-foreground-muted" />
      </div>
    );
  }

  return (
    <div className="flex flex-col text-foreground">
      <div className="flex flex-col gap-8 py-8">
        {skills.installedSkills.length > 0 && (
          <CardGridSection title="Installed">
            {skills.installedSkills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                isInstalled={true}
                onInstall={skills.install}
                onUninstall={handleUninstallRequest}
                onClick={() => handleOpenDetail(skill)}
              />
            ))}
          </CardGridSection>
        )}
        {skills.recommendedSkills.length > 0 && (
          <CardGridSection title="Recommended">
            {skills.recommendedSkills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                isInstalled={false}
                onInstall={skills.install}
                onUninstall={handleUninstallRequest}
                onClick={() => handleOpenDetail(skill)}
              />
            ))}
          </CardGridSection>
        )}
        {(skills.isSearchingSkillSh || skills.skillShSearchSkills.length > 0) && (
          <CardGridSection
            title={skills.isSearchingSkillSh ? 'Searching Skills.sh...' : 'Skills.sh'}
          >
            {skills.skillShSearchSkills.map((skill) => (
              <SkillCard
                key={skill.id}
                skill={skill}
                isInstalled={false}
                onInstall={skills.install}
                onUninstall={handleUninstallRequest}
                onClick={() => handleOpenDetail(skill)}
              />
            ))}
          </CardGridSection>
        )}
      </div>
    </div>
  );
};
