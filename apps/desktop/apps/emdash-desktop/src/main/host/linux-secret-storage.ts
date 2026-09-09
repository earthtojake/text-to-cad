/** Chromium password-store backend that routes `safeStorage` through the Secret Service. */
export const LIBSECRET_PASSWORD_STORE = 'gnome-libsecret';

/**
 * Decide whether to force Chromium's libsecret (Secret Service) backend for
 * `safeStorage` on Linux.
 *
 * Chromium only auto-selects a Secret Service backend when `XDG_CURRENT_DESKTOP`
 * names a desktop it recognizes (GNOME, KDE, Unity, Cinnamon, …). On Hyprland,
 * sway, i3, dwm and other compositors — a growing slice of the Linux desktop —
 * it falls back to the plaintext `basic_text` backend even when a working Secret
 * Service is on the session bus, which breaks every encrypted-secret feature
 * (account sign-in, cached GitHub/Linear tokens, SSH credentials, …). See #1875.
 *
 * Force `gnome-libsecret` when a session bus is present (a Secret Service can
 * only live on D-Bus) and the desktop is not KDE — KDE is left to its native
 * kwallet auto-detection. With no session bus we leave the default untouched:
 * there is no Secret Service to reach, so forcing would not help. On GNOME the
 * switch is a harmless no-op (Chromium already picks libsecret there).
 */
export function shouldForceLibsecretBackend(
  env: NodeJS.ProcessEnv = process.env,
  options: { passwordStoreSwitchPresent?: boolean } = {}
): boolean {
  if (options.passwordStoreSwitchPresent) return false;
  if (!env.DBUS_SESSION_BUS_ADDRESS?.trim()) return false;
  const desktop = (env.XDG_CURRENT_DESKTOP ?? '').toLowerCase();
  if (desktop.includes('kde')) return false;
  return true;
}
