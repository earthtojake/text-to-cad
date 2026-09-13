import { Pill } from '@emdash/ui/react/components';
import type { ConnectionState } from '@core/primitives/ssh/api';
import { stateLabel } from './machine-formatters';

function variantForState(state: ConnectionState): {
  variant: 'neutral' | 'success' | 'info' | 'error';
  pulsing: boolean;
} {
  if (state === 'connected') {
    return { variant: 'success', pulsing: false };
  }
  if (state === 'connecting' || state === 'reconnecting') {
    return { variant: 'info', pulsing: true };
  }
  if (state === 'error') {
    return { variant: 'error', pulsing: false };
  }
  return { variant: 'neutral', pulsing: false };
}

export function MachineBadge({ state }: { state: ConnectionState }) {
  const { variant, pulsing } = variantForState(state);

  return (
    <Pill variant={variant} dot pulsing={pulsing}>
      {stateLabel(state)}
    </Pill>
  );
}
