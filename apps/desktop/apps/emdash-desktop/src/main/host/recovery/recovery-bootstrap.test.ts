import { describe, expect, it } from 'vitest';
import { injectBootstrap, type RecoveryState } from './recovery-bootstrap';
import recoveryHtmlTemplate from './recovery.html?raw';

const base: RecoveryState = {
  errorMessage: 'Test error',
  version: '1.2.3',
  updaterActive: false,
  updateStatus: 'idle',
  availableVersion: undefined,
  downloadProgress: undefined,
  error: undefined,
};

const SENTINEL = '__RECOVERY_BOOTSTRAP__';

describe('injectBootstrap', () => {
  it('replaces the sentinel with serialised JSON', () => {
    const result = injectBootstrap(`var state = ${SENTINEL};`, base);
    expect(result).not.toContain(SENTINEL);
    expect(result).toContain('"errorMessage":"Test error"');
    expect(result).toContain('"version":"1.2.3"');
    expect(result).toContain('"updaterActive":false');
    expect(result).toContain('"updateStatus":"idle"');
  });

  it('injects the payload into the real recovery HTML template', () => {
    const result = injectBootstrap(recoveryHtmlTemplate, base);

    expect(result).not.toContain(SENTINEL);
    expect(result).toContain('"errorMessage":"Test error"');
  });

  it('fails closed when the template has no sentinel', () => {
    expect(() => injectBootstrap('<html></html>', base)).toThrow(
      'Recovery HTML is missing its bootstrap sentinel'
    );
  });

  it('serialises undefined values as null so the JS literal is valid', () => {
    const result = injectBootstrap(`var state = ${SENTINEL};`, base);
    expect(result).toContain('"availableVersion":null');
    expect(result).toContain('"downloadProgress":null');
    expect(result).toContain('"error":null');
  });

  it('escapes </script> sequences in the error message', () => {
    const state: RecoveryState = {
      ...base,
      errorMessage: 'x</script><script>alert(1)</script>y',
    };
    const result = injectBootstrap(`var state = ${SENTINEL};`, state);
    expect(result).not.toContain('</script><script>');
    expect(result).toContain('<\\/script>');
  });

  it('preserves surrounding HTML unchanged', () => {
    const html = `<p>before</p>var state = ${SENTINEL};<p>after</p>`;
    const result = injectBootstrap(html, base);
    expect(result).toContain('<p>before</p>');
    expect(result).toContain('<p>after</p>');
  });

  it('reflects updaterActive and updateStatus correctly', () => {
    const state: RecoveryState = { ...base, updaterActive: true, updateStatus: 'checking' };
    const result = injectBootstrap(`var state = ${SENTINEL};`, state);
    expect(result).toContain('"updaterActive":true');
    expect(result).toContain('"updateStatus":"checking"');
  });
});
