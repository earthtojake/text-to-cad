import { useAgentIcon } from '@core/features/agents/api/browser/use-agent-metadata';
import { PluginIcon } from '@core/features/agents/contributions/browser/plugin-icon';

interface AgentIconProps {
  id: string;
  /** Icon size in pixels. Default: 16. */
  size?: number;
  /** Applied to the outer wrapper span — use for positioning, rounding, overflow, etc. */
  className?: string;
  grayscale?: boolean;
}

export function AgentIcon({ id, size = 16, className, grayscale }: AgentIconProps) {
  const icon = useAgentIcon(id);
  if (!icon) return null;

  return <PluginIcon id={id} icon={icon} size={size} className={className} grayscale={grayscale} />;
}
