import type { ProviderAccountMeta } from '@core/primitives/provider-accounts/api';

export type ProviderAccount = {
  providerId: string;
  accountId: string;
  credentialRef: string;
  isDefault: boolean;
  meta: ProviderAccountMeta | null;
  createdAt: number;
  updatedAt: number;
};

export type ProviderAccountUpsert = {
  providerId: string;
  accountId: string;
  secret?: string;
  meta?: Omit<ProviderAccountMeta, 'version'>;
  credentialRef?: string;
};

export type ProviderAccountUpsertResult = {
  account: ProviderAccount;
  status: 'created' | 'updated';
};

export interface ProviderAccountStore {
  upsertAccount(input: ProviderAccountUpsert): Promise<ProviderAccountUpsertResult>;
  listAccounts(providerId: string): Promise<ProviderAccount[]>;
  getAccount(providerId: string, accountId?: string): Promise<ProviderAccount | null>;
  getDefaultAccountId(providerId: string): Promise<string | null>;
  setDefaultAccount(providerId: string, accountId: string): Promise<ProviderAccount | null>;
  resolveSecret(providerId: string, accountId?: string): Promise<string | null>;
  removeAccount(providerId: string, accountId: string): Promise<ProviderAccount | null>;
  removeAllAccounts(providerId: string): Promise<void>;
  isConfigured(providerId: string): Promise<boolean>;
}
