export const pullRequestsWorker = {
  id: 'pull-requests',
  entry: 'src/core/services/pull-requests/node/entries/pull-requests.ts',
  file: 'pull-requests-runtime.js',
} as const;
