import { McpIcon } from '@emdash/ui/react/components';
import { McpView } from '@core/features/mcp/browser/components/McpView';
import type { SettingsPageTab } from '@core/features/settings/contributions/views';
import {
  defineSettingsPageContribution,
  type SettingsPageContribution,
} from '@core/primitives/settings/api/page-contribution';

export const mcpSettingsPage = defineSettingsPageContribution({
  id: 'mcp',
  label: 'MCP',
  icon: <McpIcon size={14} />,
  component: McpView,
} satisfies SettingsPageContribution<SettingsPageTab>);
