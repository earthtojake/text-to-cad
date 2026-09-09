import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { adapterAssets } from '../src/agents/adapter-manifest';
import { validateAdapterBundleAssets } from '../src/agents/helpers/adapter-validation';

const packageDirectory = dirname(fileURLToPath(new URL('../package.json', import.meta.url)));

await validateAdapterBundleAssets({
  adapterDirectory: join(packageDirectory, 'dist/adapters'),
  assets: adapterAssets,
});
