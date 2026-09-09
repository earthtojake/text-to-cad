import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import { ARTIFACT_PREFIX, RELEASE_DIR } from './lib/config.ts';
import { exec } from './lib/exec.ts';
import { fail, info, step } from './lib/log.ts';

if (process.platform !== 'win32') {
  console.log('Not Windows — skipping signature verification.');
  process.exit(0);
}

step('Verify Windows code signatures');

const files = readdirSync(RELEASE_DIR).filter(
  (f) => f.startsWith(ARTIFACT_PREFIX) && (f.endsWith('.exe') || f.endsWith('.msi'))
);

if (files.length === 0) {
  fail('No .exe or .msi files found in release/ to verify');
}

let failed = false;

for (const f of files) {
  const fullPath = join(RELEASE_DIR, f);
  info(`Verifying signature on ${f}...`);
  try {
    const output = exec(
      `powershell -Command "` +
        `$sig = Get-AuthenticodeSignature -FilePath '${fullPath}'; ` +
        `if ($sig.Status -ne 'Valid') { Write-Error \\"Invalid: $($sig.Status) - $($sig.StatusMessage)\\"; exit 1 } ` +
        `Write-Host \\"Status: $($sig.Status)\\"; Write-Host \\"Subject: $($sig.SignerCertificate.Subject)\\""`
    );
    info(output);
  } catch {
    console.error(`Signature invalid on ${f}`);
    failed = true;
  }
}

if (failed) {
  fail('One or more Windows installers have invalid signatures');
}

info('All Windows installers are properly signed.');
