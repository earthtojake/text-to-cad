import { defineConfig } from 'tsdown';

export default defineConfig({
  entry: {
    index: 'src/index.ts',
    scheduling: 'src/scheduling/index.ts',
    concurrency: 'src/concurrency/index.ts',
    requests: 'src/requests/index.ts',
    util: 'src/util/index.ts',
    testing: 'src/testing/index.ts',
    config: 'src/config/index.ts',
    logger: 'src/logger/index.ts',
    'logger-node': 'src/logger/node/index.ts',
    markdown: 'src/markdown/index.ts',
    perf: 'src/perf/index.ts',
    'perf-node': 'src/perf/node/index.ts',
    plugins: 'src/plugins/index.ts',
  },
  format: ['esm'],
  dts: true,
  deps: {
    neverBundle: ['pino', 'fast-redact', 'zod'],
  },
  sourcemap: true,
  clean: true,
});
