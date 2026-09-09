import { createVariadicAdapter } from '@emdash/shared/logger';
import { initProcessLogging } from '@emdash/shared/logger/node';
import { getLogFileDestination } from '@main/host/file-logger';

const inner = initProcessLogging({
  name: 'hardcore-main',
  env: process.env,
  debugFlag: process.argv.includes('--debug-logs'),
  destination: getLogFileDestination(),
});

export const log = createVariadicAdapter(inner);

export type Logger = typeof log;
