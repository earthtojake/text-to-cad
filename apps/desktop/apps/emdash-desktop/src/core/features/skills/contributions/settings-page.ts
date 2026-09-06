import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import { SkillsView } from '@core/features/skills/browser/components/SkillsView';
import {
  defineSettingsPageContribution,
  type SettingsPageContribution,
} from '@core/primitives/settings/api/page-contribution';

export const skillsSettingsPage = defineSettingsPageContribution({
  id: 'skills',
  label: 'Skills',
  icon: 'brain',
  component: SkillsView,
} satisfies SettingsPageContribution<SettingsPageTab>);
