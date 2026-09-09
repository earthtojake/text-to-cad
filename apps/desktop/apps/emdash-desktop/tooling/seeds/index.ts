import type { AppDb } from '@core/services/app-db/node/db';
import { baseline } from './baseline';
import { empty } from './empty';

export type SeedFn = (db: AppDb) => Promise<void>;

export const seeds: Record<string, SeedFn> = {
  empty,
  baseline,
};
