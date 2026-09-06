import {
  parseChannelPointer,
  protocolMajor,
  releaseChannelSchema,
  releaseVersionSchema,
  type ReleaseChannel,
} from '@emdash/core/workspace-server';
import { channelPointerUrl } from './upload-helpers.ts';

type VerifyOptions = {
  baseUrl: string;
  channel: ReleaseChannel;
  version: string;
};

async function main(): Promise<void> {
  const options = parseArgs(process.argv.slice(2));
  const major = protocolMajor();
  const pointerUrl = channelPointerUrl(options.baseUrl, options.channel, major);
  const deadline = Date.now() + 30_000;
  let lastError = 'pointer was never checked';

  while (Date.now() < deadline) {
    try {
      const response = await fetch(pointerUrl, { cache: 'no-store' });
      if (!response.ok) {
        lastError = `HTTP ${response.status}`;
      } else {
        const pointer = parseChannelPointer(await response.text(), major);
        if (!pointer.success) {
          lastError = `invalid pointer: ${JSON.stringify(pointer.error)}`;
        } else if (pointer.data.artifactVersion !== options.version) {
          lastError = `pointer reports ${pointer.data.artifactVersion}, expected ${options.version}`;
        } else {
          process.stdout.write(
            `Verified ${options.channel} workspace-server pointer ${pointerUrl} -> ${options.version}\n`
          );
          return;
        }
      }
    } catch (error) {
      lastError = error instanceof Error ? error.message : String(error);
    }
    await delay(1_000);
  }

  throw new Error(`Could not verify workspace-server pointer ${pointerUrl}: ${lastError}`);
}

function parseArgs(args: string[]): VerifyOptions {
  let baseUrl: string | undefined;
  let channel: ReleaseChannel | undefined;
  let version: string | undefined;

  for (let index = 0; index < args.length; index += 1) {
    const argument = args[index];
    const next = args[index + 1];
    if (argument === '--base-url') {
      if (next === undefined) throw new Error('--base-url requires a value');
      baseUrl = next;
      index += 1;
      continue;
    }
    if (argument === '--channel') {
      if (next === undefined) throw new Error('--channel requires a value');
      const parsed = releaseChannelSchema.safeParse(next);
      if (!parsed.success) throw new Error(`Invalid workspace-server release channel '${next}'`);
      channel = parsed.data;
      index += 1;
      continue;
    }
    if (argument === '--version') {
      if (next === undefined) throw new Error('--version requires a value');
      const parsed = releaseVersionSchema.safeParse(next);
      if (!parsed.success) throw new Error(`Invalid workspace-server release version '${next}'`);
      version = parsed.data;
      index += 1;
      continue;
    }
    throw new Error(`Unknown pointer verification option '${argument}'`);
  }

  if (baseUrl === undefined || channel === undefined || version === undefined) {
    throw new Error('--base-url, --channel and --version are required');
  }
  return { baseUrl, channel, version };
}

async function delay(ms: number): Promise<void> {
  await new Promise((resolvePromise) => setTimeout(resolvePromise, ms));
}

void main().catch((error: unknown) => {
  process.stderr.write(
    `workspace-server pointer verification failed: ${error instanceof Error ? error.message : String(error)}\n`
  );
  process.exit(1);
});
