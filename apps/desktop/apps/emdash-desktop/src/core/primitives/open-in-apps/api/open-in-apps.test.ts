import { describe, expect, it } from 'vitest';
import { isValidOpenInAppId, OPEN_IN_APPS } from './open-in-apps';

describe('OPEN_IN_APPS', () => {
  it('registers Kaku as an open-in terminal option', () => {
    expect(isValidOpenInAppId('kaku')).toBe(true);
    expect(OPEN_IN_APPS.kaku).toMatchObject({
      id: 'kaku',
      iconPath: 'kaku.png',
      label: 'Kaku',
      supportsRemote: true,
    });
  });

  it('configures Kaku launch commands for supported desktop platforms', () => {
    expect(OPEN_IN_APPS.kaku.platforms.darwin?.appNames).toContain('Kaku');
    expect(OPEN_IN_APPS.kaku.platforms.darwin?.openCommands).toContain(
      'command -v kaku >/dev/null 2>&1 && kaku start --cwd {{path}}'
    );
    expect(OPEN_IN_APPS.kaku.platforms.darwin?.openCommands).toContain(
      'open -na "Kaku" --args start --cwd {{path}}'
    );
    expect(OPEN_IN_APPS.kaku.platforms.linux?.openCommands).toEqual(['kaku start --cwd {{path}}']);
  });

  it('registers Alacritty as an open-in terminal option', () => {
    expect(isValidOpenInAppId('alacritty')).toBe(true);
    expect(OPEN_IN_APPS.alacritty).toMatchObject({
      id: 'alacritty',
      iconPath: 'alacritty.svg',
      label: 'Alacritty',
      supportsRemote: true,
    });
  });

  it('configures Alacritty launch commands for supported desktop platforms', () => {
    expect(OPEN_IN_APPS.alacritty.platforms.darwin?.bundleIds).toContain('org.alacritty');
    expect(OPEN_IN_APPS.alacritty.platforms.darwin?.openCommands).toContain(
      'open -n -b org.alacritty --args --working-directory {{path}}'
    );
    expect(OPEN_IN_APPS.alacritty.platforms.linux?.openCommands).toEqual([
      'alacritty --working-directory {{path}}',
    ]);
    expect(OPEN_IN_APPS.alacritty.platforms.win32?.openCommands).toContain(
      'start "" alacritty --working-directory "{{path_raw}}"'
    );
  });

  it('registers Hyper as an open-in terminal option', () => {
    expect(isValidOpenInAppId('hyper')).toBe(true);
    expect(OPEN_IN_APPS.hyper).toMatchObject({
      id: 'hyper',
      iconPath: 'hyper.svg',
      label: 'Hyper',
      supportsRemote: true,
    });
  });

  it('configures Hyper launch commands for supported desktop platforms', () => {
    expect(OPEN_IN_APPS.hyper.platforms.darwin?.bundleIds).toContain('co.zeit.hyper');
    // Hyper has no cwd flag, so a path argument would be silently ignored; launch
    // plainly and rely on the exec cwd for best-effort directory on linux/win32.
    expect(OPEN_IN_APPS.hyper.platforms.darwin?.openCommands).toEqual(['open -na "Hyper"']);
    expect(OPEN_IN_APPS.hyper.platforms.win32?.openCommands).toEqual(['hyper']);
    expect(OPEN_IN_APPS.hyper.platforms.linux?.openCommands).toEqual(['hyper']);
  });

  it('registers Athas as an open-in editor option', () => {
    expect(isValidOpenInAppId('athas')).toBe(true);
    expect(OPEN_IN_APPS.athas).toMatchObject({
      id: 'athas',
      iconPath: 'athas.svg',
      label: 'Athas',
      supportsRemote: true,
    });
  });

  it('configures Athas launch commands for supported desktop platforms', () => {
    expect(OPEN_IN_APPS.athas.platforms.darwin?.bundleIds).toContain('com.code.athas');
    expect(OPEN_IN_APPS.athas.platforms.darwin?.openCommands).toContain(
      'command -v athas >/dev/null 2>&1 && athas {{path}}'
    );
    expect(OPEN_IN_APPS.athas.platforms.darwin?.openCommands).toContain(
      'open -n -b com.code.athas --args {{path}}'
    );
    expect(OPEN_IN_APPS.athas.platforms.win32?.openCommands).toEqual(['athas "{{path_raw}}"']);
    expect(OPEN_IN_APPS.athas.platforms.linux?.openCommands).toEqual(['athas {{path}}']);
  });

  it('registers Rider as an open-in JetBrains IDE option', () => {
    expect(isValidOpenInAppId('rider')).toBe(true);
    expect(OPEN_IN_APPS.rider).toMatchObject({
      id: 'rider',
      iconPath: 'rider.svg',
      label: 'Rider',
      hideIfUnavailable: true,
    });
  });

  it('configures Rider launch commands for supported desktop platforms', () => {
    expect(OPEN_IN_APPS.rider.platforms.darwin?.bundleIds).toContain('com.jetbrains.rider');
    expect(OPEN_IN_APPS.rider.platforms.darwin?.appNames).toContain('JetBrains Rider');
    expect(OPEN_IN_APPS.rider.platforms.darwin?.openCommands).toEqual([
      'open -a "Rider" {{path}}',
      'open -a "JetBrains Rider" {{path}}',
    ]);
    expect(OPEN_IN_APPS.rider.platforms.win32?.openCommands).toEqual([
      'rider64 {{path}}',
      'rider {{path}}',
    ]);
    expect(OPEN_IN_APPS.rider.platforms.linux?.openCommands).toEqual([
      'rider {{path}}',
      'rider.sh {{path}}',
    ]);
  });
});
