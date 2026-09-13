import { createScope } from '@emdash/shared/concurrency';
import { log } from '@main/lib/logger';

export const appScope = createScope({ label: 'main', logger: log });
