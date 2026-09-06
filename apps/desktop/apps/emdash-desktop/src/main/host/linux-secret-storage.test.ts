import { describe, expect, it } from 'vitest';
import { shouldForceLibsecretBackend } from './linux-secret-storage';

const BUS = 'unix:path=/run/user/1000/bus';

describe('shouldForceLibsecretBackend', () => {
  it('forces libsecret on an unrecognized desktop with a session bus (Hyprland/sway/…)', () => {
    expect(
      shouldForceLibsecretBackend({
        DBUS_SESSION_BUS_ADDRESS: BUS,
        XDG_CURRENT_DESKTOP: 'Hyprland',
      })
    ).toBe(true);
  });

  it('forces libsecret when no desktop is advertised but a session bus exists', () => {
    expect(shouldForceLibsecretBackend({ DBUS_SESSION_BUS_ADDRESS: BUS })).toBe(true);
  });

  it('returns true on GNOME (harmless — Chromium already selects libsecret there)', () => {
    expect(
      shouldForceLibsecretBackend({
        DBUS_SESSION_BUS_ADDRESS: BUS,
        XDG_CURRENT_DESKTOP: 'ubuntu:GNOME',
      })
    ).toBe(true);
  });

  it('leaves KDE to its native kwallet backend', () => {
    expect(
      shouldForceLibsecretBackend({ DBUS_SESSION_BUS_ADDRESS: BUS, XDG_CURRENT_DESKTOP: 'KDE' })
    ).toBe(false);
    expect(
      shouldForceLibsecretBackend({
        DBUS_SESSION_BUS_ADDRESS: BUS,
        XDG_CURRENT_DESKTOP: 'plasma:KDE',
      })
    ).toBe(false);
  });

  it('does not override an explicit password-store switch', () => {
    expect(
      shouldForceLibsecretBackend(
        {
          DBUS_SESSION_BUS_ADDRESS: BUS,
          XDG_CURRENT_DESKTOP: 'Hyprland',
        },
        { passwordStoreSwitchPresent: true }
      )
    ).toBe(false);
  });

  it('does nothing without a usable session bus (no Secret Service to reach)', () => {
    expect(shouldForceLibsecretBackend({ XDG_CURRENT_DESKTOP: 'Hyprland' })).toBe(false);
    expect(shouldForceLibsecretBackend({ DBUS_SESSION_BUS_ADDRESS: '   ' })).toBe(false);
  });
});
