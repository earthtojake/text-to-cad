import { useState, type ComponentProps, type ReactNode } from 'react';
import type { PromptContext, PromptDeliveryResult } from '@hardcore/core/prompt';
import { Button } from '../primitives/button.jsx';
import { usePromptDestination, useViewerHost } from './context.js';

export interface PromptContextActionProps extends Omit<ComponentProps<typeof Button>, 'onClick' | 'children'> {
  createContext(): PromptContext;
  onResult?(result: PromptDeliveryResult): void;
  children?: ReactNode;
  clipboardLabel?: string;
}
/**
 * One action, whose environmental delivery is selected by the host. Why it is unavailable is the
 * button's accessible description, not a hover hint: a disabled control has none (settings-ui.md).
 */
export function PromptContextAction({ createContext, onResult, children, clipboardLabel = 'Copy for prompt', disabled, ...props }: PromptContextActionProps) {
  const { promptContext } = useViewerHost();
  const destination = usePromptDestination();
  const [pending, setPending] = useState(false);
  return <Button {...props} disabled={disabled || pending || !destination.available}
    aria-description={destination.available ? undefined : destination.reason}
    onClick={() => {
      setPending(true);
      // Call before awaiting: browser activation and desktop draft binding belong to this gesture.
      let delivery: Promise<PromptDeliveryResult>;
      try { delivery = promptContext.deliver(createContext()); }
      catch (error) { delivery = Promise.resolve({ status: 'failed', message: error instanceof Error ? error.message : String(error) }); }
      void delivery.catch((error: unknown): PromptDeliveryResult => ({ status: 'failed', message: error instanceof Error ? error.message : String(error) }))
        .then(result => onResult?.(result)).finally(() => setPending(false));
    }}>{children ?? (destination.kind === 'composer' ? 'Add to prompt' : clipboardLabel)}</Button>;
}
