import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';
import { createFileTransport, trimToLineBoundary } from './index';

// Shaped like a GitHub personal access token: caught by the default redactAll scan.
const VENDOR_TOKEN = `ghp_${'a'.repeat(36)}`;

const tempDirs: string[] = [];

async function tempLogPath(): Promise<string> {
  const dir = await mkdtemp(join(tmpdir(), 'emdash-transport-test-'));
  tempDirs.push(dir);
  return join(dir, 'test.log');
}

afterEach(async () => {
  await Promise.all(tempDirs.splice(0).map((dir) => rm(dir, { recursive: true, force: true })));
});

describe('createFileTransport redaction contract', () => {
  it('redacts secret-shaped strings by default through write()', async () => {
    const path = await tempLogPath();
    const transport = createFileTransport({ path });

    transport.write(JSON.stringify({ msg: `token is ${VENDOR_TOKEN}` }));
    await transport.flush();

    const written = await readFile(path, 'utf8');
    expect(written).not.toContain(VENDOR_TOKEN);
    expect(written).toContain('[REDACTED_GITHUB_TOKEN]');
  });

  it('redacts secret-shaped strings by default through the pino destination', async () => {
    const path = await tempLogPath();
    const transport = createFileTransport({ path });

    transport.asDestination().write(JSON.stringify({ msg: `token is ${VENDOR_TOKEN}` }));
    await transport.flush();

    const written = await readFile(path, 'utf8');
    expect(written).not.toContain(VENDOR_TOKEN);
    expect(written).toContain('[REDACTED_GITHUB_TOKEN]');
  });

  it('writes raw lines through both paths when redact is explicitly false', async () => {
    const path = await tempLogPath();
    const transport = createFileTransport({ path, redact: false });

    transport.write(`direct ${VENDOR_TOKEN}`);
    transport.asDestination().write(`destination ${VENDOR_TOKEN}`);
    await transport.flush();

    const written = await readFile(path, 'utf8');
    expect(written).toContain(`direct ${VENDOR_TOKEN}`);
    expect(written).toContain(`destination ${VENDOR_TOKEN}`);
  });

  it('lets a custom redact function replace the default through both paths', async () => {
    const path = await tempLogPath();
    const transport = createFileTransport({
      path,
      redact: (line) => line.replaceAll(VENDOR_TOKEN, '<custom>'),
    });

    transport.write(`direct ${VENDOR_TOKEN} and email person@example.com`);
    transport.asDestination().write(`destination ${VENDOR_TOKEN}`);
    await transport.flush();

    const written = await readFile(path, 'utf8');
    expect(written).toContain('direct <custom>');
    expect(written).toContain('destination <custom>');
    // The default scan is replaced, not layered: the email survives untouched.
    expect(written).toContain('person@example.com');
  });
});

describe('trimToLineBoundary', () => {
  it('returns the value unchanged when within the byte budget', () => {
    expect(trimToLineBoundary('a\nb\n', 10)).toBe('a\nb\n');
  });

  it('trims to a line boundary when over budget', () => {
    const value = 'first line\nsecond line\nthird line\n';
    const trimmed = trimToLineBoundary(value, 20);
    expect(trimmed).toBe('third line\n');
  });
});
