import { spawnSync } from 'node:child_process';
import { chmod, mkdir, mkdtemp, readFile, readlink, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { describe, expect, it } from 'vitest';

const appDirectory = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const installScript = resolve(appDirectory, 'install.sh');

describe('workspace-server install.sh', () => {
  it('is valid POSIX shell syntax', () => {
    const result = spawnSync('sh', ['-n', installScript]);

    expect(result.status).toBe(0);
    expect(result.stderr.toString()).toBe('');
  });

  it('rejects unknown options with an install failure', () => {
    const result = spawnSync('sh', [installScript, '--unknown']);

    expect(result.status).toBe(42);
    expect(result.stderr.toString()).toContain("unknown option '--unknown'");
  });

  it('rejects unsupported base URL protocols before probing the host', () => {
    const result = spawnSync('sh', [installScript, '--base-url', 'ftp://example.test']);

    expect(result.status).toBe(41);
    expect(result.stderr.toString()).toContain('base URL must use https, http, or file');
  });

  it('requires an explicit immutable version', () => {
    const result = spawnSync('sh', [installScript]);

    expect(result.status).toBe(42);
    expect(result.stderr.toString()).toContain('--version is required');
  });

  it('installs a pinned version atomically and skips the artifact on a repeated run', async () => {
    const directory = await mkdtemp(resolve(tmpdir(), 'emdash-install-script-'));
    const source = resolve(directory, 'source');
    const home = resolve(directory, 'home');
    const bin = resolve(directory, 'bin');
    const curlLog = resolve(directory, 'curl.log');
    const version = '1.2.3';
    const artifact = `emdash-workspace-server-${version}-linux-x64.tar.gz`;
    await Promise.all([
      mkdir(resolve(source, version), { recursive: true }),
      mkdir(home, { recursive: true }),
      mkdir(bin, { recursive: true }),
    ]);
    await Promise.all([
      writeFile(resolve(source, version, artifact), 'fixture archive'),
      writeFile(resolve(source, version, `${artifact}.sha256`), `${'a'.repeat(64)}  ${artifact}\n`),
      writeExecutable(
        resolve(bin, 'uname'),
        `case "$1" in -s) printf 'Linux\\n' ;; -m) printf 'x86_64\\n' ;; esac`
      ),
      writeExecutable(resolve(bin, 'getconf'), `printf 'glibc 2.36\\n'`),
      writeExecutable(
        resolve(bin, 'curl'),
        `output=
url=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --output) output=$2; shift 2 ;;
    --) shift; url=$1; shift ;;
    *) shift ;;
  esac
done
printf '%s\\n' "$url" >> "$CURL_LOG"
cp "\${url#file://}" "$output"`
      ),
      writeExecutable(resolve(bin, 'sha256sum'), 'cat >/dev/null'),
      writeExecutable(
        resolve(bin, 'tar'),
        `destination=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --directory) destination=$2; shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$destination/bin"
printf '#!/bin/sh\\nexit 0\\n' > "$destination/bin/emdash-workspace-server"
chmod +x "$destination/bin/emdash-workspace-server"`
      ),
      writeExecutable(
        resolve(bin, 'mv'),
        `if [ "\${1-}" = "-Tf" ]; then
  shift
  if [ "\${1-}" = "--" ]; then shift; fi
  source=$1
  destination=$2
  rm -f -- "$destination"
  /bin/mv "$source" "$destination"
elif [ "\${1-}" = "--" ]; then
  /bin/mv "$2" "$3"
else
  /bin/mv "$@"
fi`
      ),
    ]);
    const env = {
      ...process.env,
      CURL_LOG: curlLog,
      HOME: home,
      PATH: `${bin}:${process.env['PATH'] ?? ''}`,
    };

    try {
      const baseUrl = pathToFileURL(source).href;
      const args = [installScript, '--base-url', baseUrl, '--version', version];
      const first = spawnSync('sh', args, { env });
      expect(first.status, first.stderr.toString()).toBe(0);
      expect(await readlink(resolve(home, '.emdash/workspace-server/current'))).toBe(
        `versions/${version}`
      );

      const second = spawnSync('sh', args, { env });
      expect(second.status, second.stderr.toString()).toBe(0);
      expect((await readFile(curlLog, 'utf8')).trim().split('\n')).toHaveLength(3);
    } finally {
      await rm(directory, { recursive: true, force: true });
    }
  });
});

async function writeExecutable(path: string, body: string): Promise<void> {
  await writeFile(path, `#!/bin/sh\nset -eu\n${body}\n`);
  await chmod(path, 0o755);
}
