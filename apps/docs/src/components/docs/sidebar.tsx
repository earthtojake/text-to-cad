"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

export type DocsNavigation = { title: string; pages: { href: string; label: string }[] }[];

// The sections a reader starts in stay open; the long reference lists open with their own pages.
const OPEN_BY_DEFAULT = new Set(["Get started", "Guides"]);

/** The documentation's sections and pages: the page being read is marked, and its section is open. */
export function DocsSidebar({ sections, onNavigate }: { sections: DocsNavigation; onNavigate?: () => void }) {
  const pathname = usePathname().replace(/\/$/, "") || "/docs";
  // What the reader opened or closed by hand, by section; else a section is open by default or for its page.
  const [chosen, setChosen] = useState<Record<string, boolean>>({});
  // The page being read is brought into the list's view, where a long list has scrolled it out.
  const nav = useRef<HTMLElement>(null);
  useEffect(() => {
    nav.current?.querySelector('[aria-current="page"]')?.scrollIntoView({ block: "nearest" });
  }, [pathname]);

  return (
    <nav ref={nav} aria-label="Documentation" className="space-y-1">
      {sections.map((section) => {
        const current = section.pages.some((page) => page.href === pathname);
        const open = chosen[section.title] ?? (current || OPEN_BY_DEFAULT.has(section.title));
        const id = `docs-nav-${section.title.toLowerCase().replace(/\s+/g, "-")}`;
        return (
          <div key={section.title}>
            <button
              type="button"
              aria-expanded={open}
              aria-controls={id}
              onClick={() => setChosen((state) => ({ ...state, [section.title]: !open }))}
              className="flex w-full cursor-pointer items-center justify-between gap-2 rounded-md px-2 py-1.5 text-left text-sm font-medium text-foreground outline-none hover:bg-secondary focus-visible:ring-2 focus-visible:ring-ring"
            >
              {section.title}
              <ChevronRight
                className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")}
                aria-hidden="true"
              />
            </button>
            <ul id={id} hidden={!open} className="mt-0.5 mb-2 ml-2 space-y-px border-l border-border pl-2">
              {section.pages.map((page) => {
                const active = page.href === pathname;
                return (
                  <li key={page.href}>
                    <Link
                      href={page.href}
                      aria-current={active ? "page" : undefined}
                      onClick={onNavigate}
                      className={cn(
                        "block rounded-md px-2 py-1 text-sm leading-5 outline-none transition-colors focus-visible:ring-2 focus-visible:ring-ring",
                        active
                          ? "bg-secondary font-medium text-foreground"
                          : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                      )}
                    >
                      {page.label}
                    </Link>
                  </li>
                );
              })}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}
