"use client";

import Link from "next/link";
import { ThemeToggle } from "@/components/theme-toggle";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";

const GITHUB_REPO_URL = "https://github.com/earthtojake/text-to-cad";

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

  return (
    <a
      className="hidden px-2.5 py-1.5 text-ui text-muted-foreground transition hover:bg-secondary hover:text-foreground md:inline-flex"
      href={`${GITHUB_REPO_URL}/releases`}
      target="_blank"
      rel="noreferrer"
      aria-label={`Open GitHub releases for version ${normalizedVersion}`}
      title={`Open GitHub releases for version ${normalizedVersion}`}
    >
      {normalizedVersion}
    </a>
  );
}

export function SiteHeaderClient({
  githubStars,
  version,
}: {
  githubStars: number | null;
  version: string;
}) {
  const githubLabel =
    githubStars === null
      ? "Open text-to-cad on GitHub"
      : `Open text-to-cad on GitHub, ${new Intl.NumberFormat("en-US").format(
          githubStars
        )} stars`;

  return (
    <header className="sticky top-0 z-40 h-14 shrink-0 overflow-hidden border-b border-border bg-background">
      <div className="mx-auto flex h-full w-full max-w-[1200px] items-center gap-3 px-4 sm:px-6">
        <Link
          href="/"
          className="flex min-w-0 items-center text-foreground transition hover:text-primary"
        >
          <span className="min-w-0 truncate text-sm font-medium">
            CAD Skills
          </span>
        </Link>

        <nav
          aria-label="Primary"
          className="ml-auto hidden items-center gap-1 sm:flex"
        >
          <a
            className="px-2.5 py-1.5 text-ui text-muted-foreground transition hover:bg-secondary hover:text-foreground"
            href="#skills"
          >
            SKILLS
          </a>
          <a
            className="px-2.5 py-1.5 text-ui text-muted-foreground transition hover:bg-secondary hover:text-foreground"
            href="#installation"
          >
            INSTALL
          </a>
          <VersionLink version={version} />
        </nav>

        <div className="ml-auto flex shrink-0 items-center gap-1 sm:ml-0">
          <Button
            asChild
            variant="outline"
            className="card-glow h-8 border-border bg-card px-2 text-ui text-foreground hover:bg-secondary hover:text-primary"
          >
            <a
              href="https://demo.cadskills.xyz"
              target="_blank"
              rel="noreferrer"
              aria-label="Open demo in a new tab"
            >
              DEMO
            </a>
          </Button>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                asChild
                variant="outline"
                className="card-glow h-8 border-border bg-card px-2 text-foreground hover:bg-secondary hover:text-primary"
              >
                <a
                  href={GITHUB_REPO_URL}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={githubLabel}
                >
                  <GitHubLogo className="size-3.5" />
                  {githubStars !== null ? (
                    <span className="text-label font-medium tabular-nums tracking-wider">
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
