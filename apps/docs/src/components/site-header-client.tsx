"use client";

import { Menu } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

const NAV_SECTIONS = [
  { id: "overview", label: "Overview" },
  { id: "install", label: "Install" },
  { id: "skills", label: "Skills" },
  { id: "contributing", label: "Contributing" },
] as const;

const GITHUB_REPO_URL = "https://github.com/earthtojake/text-to-cad";

function DiscordLogo({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="currentColor"
      focusable="false"
      viewBox="0 0 24 24"
    >
      <path d="M20.32 4.37a19.8 19.8 0 0 0-4.89-1.51.07.07 0 0 0-.07.03c-.21.38-.44.86-.61 1.25a18.27 18.27 0 0 0-5.49 0 12.64 12.64 0 0 0-.62-1.25.08.08 0 0 0-.07-.03 19.74 19.74 0 0 0-4.89 1.51.07.07 0 0 0-.03.03C.53 9.05-.32 13.58.1 18.06a.08.08 0 0 0 .03.06 19.9 19.9 0 0 0 5.99 3.03.08.08 0 0 0 .08-.03c.46-.63.87-1.3 1.23-1.99a.08.08 0 0 0-.04-.11 13.1 13.1 0 0 1-1.87-.89.08.08 0 0 1-.01-.13c.13-.09.25-.19.37-.29a.07.07 0 0 1 .08-.01c3.93 1.79 8.18 1.79 12.06 0a.07.07 0 0 1 .08.01c.12.1.25.2.37.29a.08.08 0 0 1-.01.13 12.3 12.3 0 0 1-1.87.89.08.08 0 0 0-.04.11c.36.7.77 1.36 1.23 1.99a.08.08 0 0 0 .08.03 19.84 19.84 0 0 0 6-3.03.08.08 0 0 0 .03-.05c.5-5.18-.84-9.67-3.55-13.66a.06.06 0 0 0-.02-.04ZM8.02 15.33c-1.18 0-2.16-1.09-2.16-2.42s.96-2.42 2.16-2.42c1.21 0 2.18 1.1 2.16 2.42 0 1.33-.96 2.42-2.16 2.42Zm7.98 0c-1.18 0-2.16-1.09-2.16-2.42s.96-2.42 2.16-2.42c1.21 0 2.18 1.1 2.16 2.42 0 1.33-.95 2.42-2.16 2.42Z" />
    </svg>
  );
}

function GitHubLogo({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="currentColor"
      focusable="false"
      viewBox="0 0 24 24"
    >
      <path d="M12 .3a12 12 0 0 0-3.8 23.4c.6.1.8-.3.8-.6v-2c-3.3.7-4-1.6-4-1.6-.5-1.3-1.2-1.6-1.2-1.6-1-.7.1-.7.1-.7 1.1.1 1.7 1.2 1.7 1.2 1 1.7 2.6 1.2 3.3.9.1-.7.4-1.2.7-1.5-2.7-.3-5.5-1.3-5.5-5.9 0-1.3.5-2.4 1.2-3.2-.1-.3-.5-1.6.1-3.2 0 0 1-.3 3.3 1.2a11.2 11.2 0 0 1 6 0C17 4.7 18 5 18 5c.7 1.6.3 2.9.1 3.2.8.8 1.2 1.9 1.2 3.2 0 4.6-2.8 5.6-5.5 5.9.4.4.8 1.1.8 2.2v3.3c0 .3.2.7.8.6A12 12 0 0 0 12 .3Z" />
    </svg>
  );
}

function formatGitHubStars(stars: number) {
  return new Intl.NumberFormat("en-US").format(stars);
}

function VersionLink({ version }: { version: string }) {
  const normalizedVersion = version.trim();

  if (!normalizedVersion) {
    return null;
  }

  // Shown as the release is tagged: v0.7.14 for the 0.7.14 the release stamps.
  const label = `v${normalizedVersion}`;

  // A phone's header needs 349px for it beside the CAD logo and the burger, so it shows from 360px,
  // the logo in or not. Between the phone and desktop layouts it stays out, as before.
  return (
    <a
      className="hidden rounded-md px-2.5 py-1.5 text-ui text-muted-foreground transition hover:bg-secondary hover:text-foreground min-[360px]:inline-flex sm:hidden md:inline-flex"
      href={`${GITHUB_REPO_URL}/releases`}
      target="_blank"
      rel="noreferrer"
      aria-label={`Open GitHub releases for ${label}`}
      title={`Open GitHub releases for ${label}`}
    >
      {label}
    </a>
  );
}

/** A phone's section links: a burger that drops them down under the header. The browser's own
 * popover (`popoverTarget`), so the browser opens and closes it -- the burger again, a tap outside
 * or Escape -- from the first paint on, before this page has hydrated, and its links follow the
 * burger in the tab order. Choosing a section closes it too. It shows in the top layer, held under
 * the header at the burger by anchor positioning, or where the burger stands at the top of the page
 * where that is missing (the header is sticky, so the page's top is the header's). The burger reads
 * pressed while it is open (`aria-expanded`, from the popover's toggle). */
function SectionMenu({ activeSection }: { activeSection: string }) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);

  return (
    <nav aria-label="Primary" className="flex items-center self-stretch [anchor-name:--section-menu] sm:hidden">
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-muted-foreground hover:text-foreground"
        aria-label="Sections"
        aria-expanded={open}
        popoverTarget="section-menu"
      >
        <Menu className="size-4" />
      </Button>
      <div
        ref={menuRef}
        id="section-menu"
        popover="auto"
        onToggle={(event) => setOpen(event.newState === "open")}
        className="inset-auto top-14 left-4 m-0 mt-1 min-w-40 origin-top-left flex-col rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-md open:flex open:animate-in open:fade-in-0 open:zoom-in-95 open:slide-in-from-top-2 motion-reduce:animate-none supports-[anchor-name:--a]:top-[anchor(bottom)] supports-[anchor-name:--a]:left-[anchor(left)] supports-[anchor-name:--a]:[position-anchor:--section-menu]"
      >
        {NAV_SECTIONS.map(({ id, label }) => (
          <a
            key={id}
            href={`/#${id}`}
            aria-current={activeSection === id ? "location" : undefined}
            onClick={() => menuRef.current?.hidePopover()}
            className={`rounded-md px-2.5 py-2 text-ui transition hover:bg-secondary hover:text-foreground ${activeSection === id ? "text-foreground" : "text-muted-foreground"}`}
          >
            {label}
          </a>
        ))}
      </div>
    </nav>
  );
}

export function SiteHeaderClient({
  heroWordmark,
  githubStars,
  discordUrl,
  version,
}: {
  heroWordmark: boolean;
  githubStars: number | null;
  discordUrl: string;
  version: string;
}) {
  const [activeSection, setActiveSection] = useState<string>(NAV_SECTIONS[0].id);
  // The hero's wordmark in sight (below this header). Once it is out of sight -- scrolled away, or a
  // page without one -- the CAD logo slides into the header's corner, pushing the section links (a
  // phone's section menu) right: the brand still in view, and a way back home.
  const [wordmarkInSight, setWordmarkInSight] = useState(heroWordmark);

  useEffect(() => {
    const wordmark = heroWordmark ? document.getElementById("hero-wordmark") : null;
    if (!wordmark) return;
    const observer = new IntersectionObserver(([entry]) => setWordmarkInSight(entry.isIntersecting), {
      rootMargin: "-56px 0px 0px 0px", // this sticky header's height: under it is out of sight
    });
    observer.observe(wordmark);
    return () => observer.disconnect();
  }, [heroWordmark]);

  useEffect(() => {
    let frame = 0;
    const updateActiveSection = () => {
      frame = 0;
      const sections = NAV_SECTIONS.map(({ id }) => document.getElementById(id));
      if (!sections.some(Boolean)) {
        setActiveSection("");
        return;
      }
      let active: string = NAV_SECTIONS[0].id;
      for (const section of sections) {
        if (section && section.getBoundingClientRect().top <= 96) {
          active = section.id;
        }
      }
      // The final section may not be tall enough to reach the header.
      if (window.scrollY > 0 && window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 2) {
        active = NAV_SECTIONS[NAV_SECTIONS.length - 1].id;
      }
      setActiveSection(active);
    };
    const scheduleUpdate = () => {
      if (!frame) frame = window.requestAnimationFrame(updateActiveSection);
    };
    updateActiveSection();
    window.addEventListener("scroll", scheduleUpdate, { passive: true });
    window.addEventListener("resize", scheduleUpdate);
    return () => {
      window.removeEventListener("scroll", scheduleUpdate);
      window.removeEventListener("resize", scheduleUpdate);
      window.cancelAnimationFrame(frame);
    };
  }, []);

  const githubLabel =
    githubStars === null
      ? "Open text-to-cad on GitHub"
      : `Open text-to-cad on GitHub, ${new Intl.NumberFormat("en-US").format(
          githubStars
        )} stars`;

  return (
    // A phone's section menu is a popover, in the top layer, so nothing here clips it.
    <header className="sticky top-0 z-40 h-14 shrink-0 overflow-hidden border-b border-border bg-background">
      <div className="mx-auto flex h-full w-full max-w-[1200px] items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          aria-label="text-to-cad home"
          className={cn(
            "flex w-[46px] shrink-0 items-center overflow-hidden transition-[width,margin,opacity,visibility] duration-300 ease-out",
            // Out of the row while the wordmark shows: no width, the row's gap taken back, and out of
            // the tab order.
            wordmarkInSight && "invisible -mr-3 w-0 opacity-0"
          )}
        >
          <Image
            src="/brand/logo-cad.svg"
            alt=""
            width={52}
            height={22}
            unoptimized
            className="h-[22px] w-auto shrink-0"
          />
        </Link>
        <nav
          aria-label="Primary"
          className="hidden items-center gap-1 sm:flex"
        >
          {NAV_SECTIONS.map(({ id, label }) => (
            <a
              key={id}
              href={`/#${id}`}
              aria-current={activeSection === id ? "location" : undefined}
              className={`rounded-md px-2.5 py-1.5 text-ui transition hover:bg-secondary hover:text-foreground ${activeSection === id ? "text-foreground" : "text-muted-foreground"}`}
            >
              {label}
            </a>
          ))}
        </nav>
        <SectionMenu activeSection={activeSection} />

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <VersionLink version={version} />
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                asChild
                variant="ghost"
                size="icon"
                className="text-muted-foreground hover:text-foreground"
              >
                <a
                  href={discordUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label="Join the text-to-cad Discord"
                >
                  <DiscordLogo className="size-3.5" />
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">Discord</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                asChild
                variant="ghost"
                className="px-2 text-muted-foreground hover:text-foreground"
              >
                <a
                  href={GITHUB_REPO_URL}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={githubLabel}
                >
                  <GitHubLogo className="size-3.5" />
                  {githubStars !== null ? (
                    <span className="text-label font-medium tabular-nums">
                      {formatGitHubStars(githubStars)}
                    </span>
                  ) : null}
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">GitHub</TooltipContent>
          </Tooltip>
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
