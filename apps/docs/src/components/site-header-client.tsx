"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { GitHubLogo } from "@/components/brand-marks";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { formatGitHubStars, GITHUB_REPO_URL } from "@/lib/github";
import { cn } from "@/lib/utils";

// A tab of the header, Shop or Docs: marked while a page under it is open.
function NavLink({ href, children }: { href: string; children: string }) {
  const current = usePathname().startsWith(href);
  return (
    <Link
      href={href}
      aria-current={current ? "page" : undefined}
      className={cn(
        "rounded-md px-2.5 py-1.5 text-sm font-medium transition hover:bg-secondary hover:text-foreground",
        current ? "text-foreground" : "text-muted-foreground",
      )}
    >
      {children}
    </Link>
  );
}

export function SiteHeaderClient({
  githubStars,
  wide = false,
}: {
  githubStars: number | null;
  wide?: boolean;
}) {
  const githubLabel =
    githubStars === null
      ? "Open text-to-cad on GitHub"
      : `Open text-to-cad on GitHub, ${formatGitHubStars(githubStars)} stars`;

  return (
    <header className="sticky top-0 z-40 h-14 shrink-0 overflow-hidden border-b border-border bg-background">
      <div className={cn("mx-auto flex h-full w-full items-center gap-3 px-4 sm:px-6", wide ? "max-w-[1400px]" : "max-w-[1200px]")}>
        {/* The C mark and the name, one link home, always there. */}
        <Link href="/" aria-label="text-to-cad home" className="flex shrink-0 items-center gap-2 rounded-md">
          <Image
            src="/brand/logo-c.svg"
            alt=""
            width={24}
            height={24}
            unoptimized
            priority
            className="h-6 w-auto shrink-0"
          />
          <span className="text-base font-semibold tracking-tight text-foreground sm:text-lg">text-to-cad</span>
        </Link>

        <div className="ml-auto flex shrink-0 items-center gap-1">
          <NavLink href="/shop">Shop</NavLink>
          <NavLink href="/docs">Docs</NavLink>
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
                  <GitHubLogo className="size-4" />
                  {githubStars !== null ? (
                    <span className="text-sm font-medium tabular-nums">
                      {formatGitHubStars(githubStars)}
                    </span>
                  ) : null}
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">GitHub</TooltipContent>
          </Tooltip>
        </div>
      </div>
    </header>
  );
}
