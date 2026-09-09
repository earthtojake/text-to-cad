// DPkg::Lock::Timeout only waits on the dpkg lock held by processes outside Emdash
// (manual apt, unattended-upgrades); Emdash-owned installs serialize in-process.
const APT_COMMAND_PREFIX = 'DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=60';

export const APT_UPDATE_COMMAND = `${APT_COMMAND_PREFIX} update`;

export function aptInstallPackagesCommand(packages: string[]): string {
  return `${APT_COMMAND_PREFIX} install -y ${packages.join(' ')}`;
}

/** Full canonical command used for option previews and manual-retry guidance. */
export function aptInstallCommand(packages: string[]): string {
  return `${APT_UPDATE_COMMAND} && ${aptInstallPackagesCommand(packages)}`;
}
