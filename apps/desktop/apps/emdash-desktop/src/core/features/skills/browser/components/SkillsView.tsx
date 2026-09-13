import { LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import React from 'react';
import { SkillsPanel } from '@core/features/skills/contributions/browser/SkillsPanel';

export const SkillsView: React.FC = () => (
  <SkillsPanel
    host={LOCAL_HOST_REF}
    header={{
      title: 'Skills',
      description: 'Extend your agents with reusable skill modules',
    }}
  />
);
