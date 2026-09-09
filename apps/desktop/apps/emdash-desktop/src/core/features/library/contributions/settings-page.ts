import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import {
  defineSettingsPageContribution,
  type SettingsPageContribution,
} from '@core/primitives/settings/api/page-contribution';
import { PromptLibraryView } from '../browser/prompts/prompt-library-view';

export const promptsSettingsPage = defineSettingsPageContribution({
  id: 'prompts',
  label: 'Prompts',
  icon: 'message-square-text',
  component: PromptLibraryView,
} satisfies SettingsPageContribution<SettingsPageTab>);
