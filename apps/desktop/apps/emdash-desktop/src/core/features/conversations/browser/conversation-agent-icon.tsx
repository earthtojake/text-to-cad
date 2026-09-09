import { MessageSquare } from 'lucide-react';
import { AgentIcon } from '@core/features/agents/contributions/browser/agent-icon';

/**
 * Agent provider icon with an optional MessageSquare badge overlaid in the
 * bottom-right corner when the conversation is ACP-type. Used by both the
 * sidebar conversation list and the ACP tab bar item so the badge is rendered
 * consistently in one place.
 */
export function ConversationAgentIcon({
  providerId,
  isAcp,
  size = 16,
  className,
}: {
  providerId: string;
  isAcp: boolean;
  size?: number;
  className?: string;
}) {
  return (
    <span className="relative inline-flex shrink-0" style={{ width: size, height: size }}>
      <AgentIcon id={providerId} size={size} className={className} />
      {isAcp && (
        <span
          title="ACP chat"
          className="absolute -right-1 -bottom-1 flex items-center justify-center rounded-full bg-background ring-1 ring-background"
        >
          <MessageSquare className="size-2.5 text-foreground-muted" />
        </span>
      )}
    </span>
  );
}
