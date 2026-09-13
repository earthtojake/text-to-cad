import type { AppConfig } from '../core/config';
import { step } from '../core/phase';
import { applyIdentity } from './phases/apply-identity';
import { prepareElectron } from './phases/prepare-electron';
import type { BootSignals } from './types';

export async function runBootPreflight(config: AppConfig, signals: BootSignals): Promise<void> {
  await step('apply-identity', () => applyIdentity(config));
  await step('prepare-electron', () => prepareElectron(config, signals));
}
