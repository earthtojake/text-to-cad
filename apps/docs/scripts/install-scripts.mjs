import { copyFile, mkdir } from 'node:fs/promises';

// The one-line installer, served as texttocad.dev/install.sh and www.texttocad.dev/install.ps1, and the
// program both download from beside themselves, /install.py: the repository's files (scripts/install/, the
// one source, which the release stamps) copied into public/ as the site builds. The copies are build
// output, ignored by Git; next.config.ts gives them their headers.
const source = new URL('../../../scripts/install/', import.meta.url);
const target = new URL('../public/', import.meta.url);
await mkdir(target, { recursive: true });
for (const name of ['install.sh', 'install.ps1', 'install.py']) {
  await copyFile(new URL(name, source), new URL(name, target));
}
console.log('Copied scripts/install/install.sh, install.ps1 and install.py into public/.');
