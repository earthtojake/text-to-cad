import { useAppSettingsKey } from '@core/features/settings/api/browser/use-app-settings-key';
import type { ChangesListViewMode, ChangesSection } from '@core/primitives/app-settings/api';

export function useChangesViewMode(section: ChangesSection) {
  const { value, update } = useAppSettingsKey('changesViewMode');
  const mode: ChangesListViewMode = value?.[section] ?? 'flat';
  const setMode = (next: ChangesListViewMode) => update({ [section]: next });
  return { mode, setMode };
}
