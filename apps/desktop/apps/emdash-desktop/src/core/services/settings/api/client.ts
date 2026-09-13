import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { appSettingsContract, appSettingsDomain } from './contract';

export type AppSettingsClient = ContractClient<typeof appSettingsContract>;

export function getAppSettingsClient(): Promise<AppSettingsClient> {
  return domainClient<AppSettingsClient>(appSettingsDomain, appSettingsContract);
}
