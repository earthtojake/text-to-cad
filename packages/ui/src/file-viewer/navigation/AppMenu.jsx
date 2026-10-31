import { ArrowLeft, Check, ChevronRight, Info, MessageCircle, Monitor, Moon, Sun } from "lucide-react";
import { Fragment, useState } from "react";

import { DropdownMenu as MenuPrimitive } from "radix-ui";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator,
  DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { LOCALES, useI18n } from "@text-to-cad/ui/i18n";
import { cn } from "@text-to-cad/ui/utils";
import { TooltipHint } from "../../primitives/tooltip.jsx";

import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";

import { useViewerMobile } from "../responsive.js";
import { DiscordMark, GitHubMark } from "./brandMarks.jsx";
import { feedbackUrl, MadeBy, useFollow } from "./NavbarLinks.jsx";
import { useControlUsage } from "../../usage/controls.js";

const NONE = Object.freeze([]);
// A setting's row: 32px, its name and its control spaced apart, the control's centre on one line.
const SETTING_ROW_CLASS = "flex min-h-8 items-center justify-between gap-2 py-0.5 pr-1 pl-2 text-tiny text-foreground";
const COLOR_SCHEMES = Object.freeze([["system", Monitor], ["light", Sun], ["dark", Moon]]);
// AUTOMATIC is the Language submenu's value for "no choice": the context decides.
const AUTOMATIC = "automatic";

/** Language's choices: Automatic, naming what the context infers, then each language under its own name. */
const languageOptions = (language, t, className = undefined) => [
  <DropdownMenuRadioItem key={AUTOMATIC} value={AUTOMATIC} onSelect={event => event.preventDefault()} className={className} data-language-option={AUTOMATIC}>
    {t("menu.languageAutomatic", { language: t(`language.${language.inferred}`) })}
  </DropdownMenuRadioItem>,
  ...LOCALES.map(id => <DropdownMenuRadioItem key={id} value={id} lang={id} onSelect={event => event.preventDefault()} className={className} data-language-option={id}>
    {t(`language.${id}`)}
  </DropdownMenuRadioItem>),
];

/**
 * The app's menu, from the navbar's logo over every file and over the host's home: what is the
 * person's rather than a file's. First, where the host has a home, Back to home (`onHome`). Then the
 * person's settings, a press keeping the menu open: Language (`language`), one row naming the language in
 * force, whose submenu offers Automatic (the language the context infers, named) and each language under
 * its own name; the host's on/off settings (`appSettings`: Telemetry), a checkbox at the right, filled while on, and
 * an info icon whose hint says what the setting means; then Theme (`colorScheme`), its System, Light and
 * Dark a segmented control, the one in force lit; then Send feedback (a new issue on the host's tracker, naming the version and the
 * `platform`), GitHub and Discord; and last, in gray, the version this host runs (a link to its
 * release notes) and, under it, who made it. The menu is 12rem wide and never wider: a long
 * setting's name wraps, and a custom build's long version truncates, whole in its hint. Every link
 * opens the host's way (`links.open`).
 *
 * @param {{ trigger: import("react").ReactElement, onHome?: () => void,
 *   links?: import("../../host/types.js").ViewerLinks, appSettings?: readonly import("../types.js").AppSetting[],
 *   colorScheme?: import("../types.js").ColorSchemeSetting, platform?: string }} props
 */
export function AppMenu({ trigger, onHome, links, appSettings = NONE, colorScheme, language, platform }) {
  const { t } = useI18n();
  const mobile = useViewerMobile();
  // A phone's Language row opens its choices in place; each opening of the menu starts it closed.
  const [languageOpen, setLanguageOpen] = useState(false);
  const follow = useFollow(links);
  const usage = useControlUsage();
  const feedback = links ? feedbackUrl(links, platform) : "";
  const outward = [
    feedback ? { id: "feedback", label: t("menu.feedback"), href: feedback, icon: MessageCircle } : null,
    links?.github ? { id: "github", label: "GitHub", href: links.github, icon: GitHubMark } : null,
    links?.discord ? { id: "discord", label: "Discord", href: links.discord, icon: DiscordMark } : null,
  ].filter(Boolean);
  const groups = [
    onHome ? [<DropdownMenuItem key="home" onSelect={onHome} data-menu-home=""><ArrowLeft aria-hidden="true" />{t("menu.backToHome")}</DropdownMenuItem>] : [],
    // The person's settings, one group of like rows — Language, the host's on/off settings, Theme: a name
    // on the left in the menu's own text and its control on the right — the language in force, a checkbox
    // filled while on, Theme's segmented System, Light and Dark. A press keeps the menu open.
    [
      // Language: the language in force at the row's end; its submenu, Automatic (what the context infers,
      // named) then each language under its own name, whatever the menu is reading in. A phone has no
      // room beside the menu for a submenu: there the same row opens its choices under it, in the menu
      // itself (its chevron turning down), and a choice closes them again.
      ...(language && mobile ? [<MenuPrimitive.Item key="language" onSelect={event => { event.preventDefault(); setLanguageOpen(open => !open); }}
        aria-expanded={languageOpen} className={cn(SETTING_ROW_CLASS, "cursor-default rounded-sm pr-2 outline-none focus:bg-accent")}
        data-slot="dropdown-menu-item" data-menu-language="" data-state={languageOpen ? "open" : "closed"}>
        <span className="min-w-0 flex-1">{t("menu.language")}</span>
        <span className="shrink-0 text-muted-foreground" lang={language.locale}>{t(`language.${language.locale}`)}</span>
        <ChevronRight className={cn("size-4 shrink-0 text-muted-foreground transition-transform", languageOpen && "rotate-90")} aria-hidden="true" />
      </MenuPrimitive.Item>, ...(languageOpen ? [<DropdownMenuRadioGroup key="language-options" aria-label={t("menu.language")} value={language.choice ?? AUTOMATIC}
        onValueChange={value => { usage.used("language"); language.onChoiceChange(value === AUTOMATIC ? null : value); setLanguageOpen(false); }}>
        {languageOptions(language, t, "pl-5")}
      </DropdownMenuRadioGroup>] : [])] : []),
      ...(language && !mobile ? [<DropdownMenuSub key="language">
        {/* The chevron's 16px box is centred where the checkbox's and Theme's last segment are (16px in
            from the row's end), and the row keeps the setting rows' text colour while its submenu is open. */}
        <DropdownMenuSubTrigger className={cn(SETTING_ROW_CLASS, "pr-2 focus:text-foreground data-[state=open]:text-foreground")} data-menu-language="">
          <span className="min-w-0 flex-1">{t("menu.language")}</span>
          <span className="shrink-0 text-muted-foreground" lang={language.locale}>{t(`language.${language.locale}`)}</span>
        </DropdownMenuSubTrigger>
        <DropdownMenuSubContent className={cn(FLOATING_SURFACE_CLASS, "min-w-40")} aria-label={t("menu.language")}>
          <DropdownMenuRadioGroup value={language.choice ?? AUTOMATIC} onValueChange={value => { usage.used("language"); language.onChoiceChange(value === AUTOMATIC ? null : value); }}>
            {languageOptions(language, t)}
          </DropdownMenuRadioGroup>
        </DropdownMenuSubContent>
      </DropdownMenuSub>] : []),
      ...appSettings.map(setting => <MenuPrimitive.CheckboxItem key={setting.id} checked={setting.checked} disabled={setting.disabled}
        onCheckedChange={checked => setting.onCheckedChange(checked === true)} onSelect={event => event.preventDefault()}
        className={cn(SETTING_ROW_CLASS, "group/setting cursor-default rounded-sm outline-none focus:bg-accent data-[disabled]:pointer-events-none data-[disabled]:opacity-50")}
        data-slot="dropdown-menu-checkbox-item" data-app-setting={setting.id}>
        <span className="flex min-w-0 flex-1 items-center gap-1">
          <span className="min-w-0">{setting.label}</span>
          {setting.info ? <TooltipHint content={setting.info} side="right">
            <span className="pointer-events-auto grid size-4 shrink-0 place-items-center text-muted-foreground" aria-label={setting.info} role="img" data-app-setting-info="">
              <Info className="size-3" aria-hidden="true" />
            </span>
          </TooltipHint> : null}
        </span>
        <span className="grid size-6 shrink-0 place-items-center" aria-hidden="true">
          <span className="grid size-3.5 place-items-center rounded-[4px] border border-input text-primary-foreground group-data-[state=checked]/setting:border-primary group-data-[state=checked]/setting:bg-primary">
            <Check className="hidden size-3 group-data-[state=checked]/setting:block" strokeWidth={3} />
          </span>
        </span>
      </MenuPrimitive.CheckboxItem>),
      ...(colorScheme ? [<div key="theme" className={SETTING_ROW_CLASS} data-menu-theme="">
        <span className="min-w-0">{t("menu.theme")}</span>
        <MenuPrimitive.RadioGroup value={colorScheme.preference} onValueChange={value => { usage.used(`theme_${value}`); colorScheme.onPreferenceChange(value); }} aria-label={t("menu.theme")}
          className="-mr-0.5 flex shrink-0 items-center gap-0.5 rounded-md bg-muted p-0.5">
          {COLOR_SCHEMES.map(([id, Icon]) => <MenuPrimitive.RadioItem key={id} value={id} aria-label={t(`appearance.${id}`)} onSelect={event => event.preventDefault()}
            className="grid size-6 cursor-default place-items-center rounded-sm text-muted-foreground outline-none transition-colors hover:text-foreground focus:bg-accent focus:text-foreground data-[state=checked]:bg-background data-[state=checked]:text-foreground data-[state=checked]:shadow-xs"
            data-theme-option={id}>
            <Icon className="size-3.5" aria-hidden="true" />
          </MenuPrimitive.RadioItem>)}
        </MenuPrimitive.RadioGroup>
      </div>] : []),
    ],
    outward.map(({ id, label, href, icon: Icon }) => <DropdownMenuItem key={id} asChild>
      <a href={href} target="_blank" rel="noreferrer" onClick={event => { if (id === "feedback") usage.used("feedback"); follow?.(event); }} data-link={id}><Icon className="size-3.5" aria-hidden="true" />{label}</a>
    </DropdownMenuItem>),
  ].filter(group => group.length);
  // Only the version shortens to fit the line, never the rest of it, and says itself whole when it does.
  const version = links?.version ? <TooltipHint content={`v${links.version}`} overflowOnly>{links.release
    ? <a href={links.release} target="_blank" rel="noreferrer" onClick={follow} className="min-w-0 truncate hover:text-foreground"
      data-menu-version="">v{links.version}</a>
    : <span className="min-w-0 truncate" data-menu-version="">v{links.version}</span>}</TooltipHint> : null;
  const madeBy = links?.x ? <MadeBy links={links} /> : null;
  return <DropdownMenu modal={false} onOpenChange={() => setLanguageOpen(false)}>
    <DropdownMenuTrigger asChild>{trigger}</DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={6} collisionPadding={8} aria-label={t("navbar.menu")} data-app-menu=""
      className={cn(FLOATING_SURFACE_CLASS, "w-48 max-w-(--radix-dropdown-menu-content-available-width) data-[state=closed]:animate-none!")}>
      {groups.map((group, index) => <Fragment key={index}>{index ? <DropdownMenuSeparator /> : null}{group}</Fragment>)}
      {version || madeBy ? <>
        {groups.length ? <DropdownMenuSeparator /> : null}
        <div className="flex min-w-0 flex-col gap-0.5 whitespace-nowrap px-2 py-1.5 text-tiny text-muted-foreground tabular-nums" data-menu-footer="">
          {version ? <div className="flex min-w-0">{version}</div> : null}
          {madeBy ? <div className="flex min-w-0">{madeBy}</div> : null}
        </div>
      </> : null}
    </DropdownMenuContent>
  </DropdownMenu>;
}
