import { Settings } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { TooltipHint } from "@cad/ui/primitives/tooltip";

import { AppMenu } from "./navigation/AppMenu.jsx";
import { useOutwardLinks } from "./navigation/NavbarLinks.jsx";
import { useAppMenu } from "./navbarSlots.js";

// The panel's foot: the app's own links and settings, which have ONE place wherever the host has a home: the bottom
// of the sidebar, the same on the home (`library/LibrarySidebar.jsx`) and over a document
// (`renderers/kit/shell/FlatPanel.jsx`), pinned, peeking or a phone's sheet. One component, so it is the same height
// and on the same lines in both, and nothing shifts between the home and a document. The file viewer feeds it
// (`navbarSlots.js`'s `AppMenuContext`: the host's links, the person's settings); a host with no home hands none, keeps
// them in the menu its navbar's logo opens, and has no foot, so nothing is offered twice.

/**
 * A foot's icon tile: the panel head's icon button (the control square, a 14px muted glyph, the foreground and a faint
 * fill under the pointer, the accent fill while its menu is open), so the foot reads as the panel's own chrome.
 */
const FOOT_TILE_CLASS = "grid size-control shrink-0 cursor-pointer place-items-center rounded-md text-muted-foreground no-underline outline-none transition-colors hover:bg-accent/50 hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 aria-expanded:bg-accent aria-expanded:text-foreground [&_svg]:size-3.5";
/**
 * Its row: 8px over and under the tiles (clear of a host's composer floating over the bottom), which hang past the
 * panel's inset by their own padding (a 14px glyph in the control), so the first glyph and the cog's stand on the
 * panel's two lines.
 */
const FOOT_STYLE = Object.freeze({ padding: "8px calc(var(--panel-inset) - (var(--cad-control) - 14px) / 2) max(8px, calc(var(--cad-host-bottom-inset, 0px) + 8px))" });

/**
 * The foot, for a panel's surface (`PanelSurface`'s `foot`): one row under a hairline rule that runs the panel's full
 * width, pinned under the panel's content while it scrolls. At its left, the host's links out, each an icon tile with
 * its name in a hint: GitHub and Discord (each only where the host gives that link), then Send feedback; a press
 * follows the link as the app menu's item does (`useOutwardLinks`: the host's `links.open` where it has one, Send
 * feedback counted). At its right corner, the cog, Settings, which opens the app's menu upward with what is left of it
 * (`AppMenu`, `outward: false`): Language, the host's switches, Theme, and the version and who made it. In a panel
 * too narrow for them all the links wrap, upward; the cog keeps its corner. Nothing where the file viewer hands no
 * menu (a host with no home; a panel drawn outside a file viewer).
 */
export function PanelFoot() {
  const menu = useAppMenu();
  return menu ? <Foot menu={menu} /> : null;
}

function Foot({ menu }) {
  const { t } = useI18n();
  const out = useOutwardLinks(menu.links, menu.platform);
  const links = [out.github, out.discord, out.feedback].filter(Boolean);
  const settings = t("menu.settings");
  return <div className="flex shrink-0 items-end gap-1 border-t border-border" style={FOOT_STYLE} data-app-foot="">
    <div className="flex min-w-0 flex-1 flex-wrap-reverse gap-0.5" data-app-foot-links="">
      {links.map(({ id, label, href, Icon, onClick }) => <TooltipHint key={id} content={label} side="top">
        <a href={href} target="_blank" rel="noreferrer" aria-label={label} onClick={onClick} className={FOOT_TILE_CLASS} data-link={id}><Icon aria-hidden="true" /></a>
      </TooltipHint>)}
    </div>
    <AppMenu {...menu} outward={false} side="top" align="end" label={settings} trigger={<TooltipHint content={settings} side="top">
      <button type="button" aria-label={settings} className={FOOT_TILE_CLASS} data-app-settings=""><Settings aria-hidden="true" /></button>
    </TooltipHint>} />
  </div>;
}
