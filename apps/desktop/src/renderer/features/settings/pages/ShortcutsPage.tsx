/**
 * Keyboard shortcuts: the table from `src/renderer/lib/shortcuts.ts`, printed
 * with this platform's glyphs.
 *
 * Read-only for now (plan §10). Rebinding means a stored map, a conflict check
 * and a way to reach the app menu's accelerators, none of which is worth
 * building before the list has settled.
 */
import {
  SHORTCUT_GROUPS,
  shortcutKeys,
  shortcutsIn,
  type ShortcutGroup,
} from "@renderer/lib/shortcuts";
import { SettingCard, SettingRow } from "@renderer/features/settings/SettingCard";
import { isMac } from "@renderer/lib/platform";

export function ShortcutsPage() {
  return (
    <>
      {SHORTCUT_GROUPS.map((group) => (
        <Group group={group} key={group} />
      ))}
      <p className="px-1 text-xs text-muted-foreground">
        Shortcuts are fixed for now. The ones with a menu item work even when the keyboard is
        inside an editor or a browser tab.
      </p>
    </>
  );
}

function Group({ group }: { group: ShortcutGroup }) {
  return (
    <SettingCard title={group}>
      {shortcutsIn(group).map((shortcut) => (
        <SettingRow
          control={
            <kbd className="rounded-md border bg-muted px-2 py-1 font-mono text-xs whitespace-nowrap">
              {shortcutKeys(shortcut.binding, isMac)}
              {shortcut.through ? ` – ${shortcutKeys(shortcut.through, isMac)}` : ""}
            </kbd>
          }
          key={shortcut.id}
          keywords={`${shortcut.binding} shortcut key binding`}
          title={shortcut.label}
        />
      ))}
    </SettingCard>
  );
}
