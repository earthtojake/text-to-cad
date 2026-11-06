import { Star } from "lucide-react";
import { AgentCarousel } from "@/components/agent-carousel";
import { DiscordLogo, GitHubLogo } from "@/components/brand-marks";
import { HeroGear } from "@/components/hero-gear";
import { InstallBox } from "@/components/install-box";
import { LogoBuild } from "@/components/logo-build";
import { Button } from "@/components/ui/button";
import {
  formatGitHubStars,
  getGitHubStars,
  GITHUB_REPO_URL,
  normalizeDiscordUrl,
} from "@/lib/github";

/** The homepage's hero, the whole first screen under the header: the TEXTTOCAD wordmark and the
 * tagline, the two calls to action (GitHub with its stars, Join Discord) and the one-line install
 * -- the page's Install, at `#install` -- centred over the planetary gear turning in the background,
 * then the agents it works with at the foot of the screen. */
export async function HeroSection() {
  const stars = await getGitHubStars();

  return (
    // The screen's height less the header's (h-14), so the agents sit above the fold on a phone
    // too: the small viewport height, which the browser's bars never cover.
    <section className="flex min-h-[calc(100svh-3.5rem)] flex-col">
      {/* The gear sits behind this part only, and fades out above the agents. */}
      <div className="relative isolate flex flex-1 flex-col justify-center">
        <HeroGear />
        {/* Its gaps shrink on a short screen, and the wordmark with them, so the agents still fit
            above the fold on a laptop's 600-odd pixels under the browser's bars. */}
        <div className="mx-auto flex w-full max-w-[1200px] flex-col items-center px-4 pt-[clamp(1rem,4svh,3rem)] pb-[clamp(0.75rem,2.5svh,2rem)] text-center sm:px-6">
          <h1 className="sr-only">text-to-cad: Design physical products with AI.</h1>
          {/* A block of its own, so the centred column does not shrink the wordmark to fit. */}
          <div className="w-full max-w-[min(800px,calc((100svh-3.5rem)*1.15))]">
            <LogoBuild
              id="hero-wordmark"
              name="logo-texttocad"
              alt=""
              width={800}
              height={137}
              priority
              className="mx-auto h-auto w-full max-w-[800px]"
            />
          </div>
          <p className="mt-[clamp(0.75rem,2.7svh,1.5rem)] text-2xl font-semibold tracking-tight text-foreground sm:text-3xl [@media(min-width:64rem)_and_(min-height:44rem)]:text-4xl">
            Design physical products with AI.{" "}
            <span className="text-brand">100% open source and free.</span>
          </p>

          <div className="mt-[clamp(1rem,3.6svh,2rem)] flex flex-wrap items-center justify-center gap-3">
            <Button asChild size="lg" variant="outline" className="px-4">
              <a
                href={GITHUB_REPO_URL}
                target="_blank"
                rel="noreferrer"
                aria-label={
                  stars === null
                    ? "text-to-cad on GitHub"
                    : `text-to-cad on GitHub, ${formatGitHubStars(stars)} stars`
                }
              >
                <GitHubLogo />
                GitHub
                {stars !== null ? (
                  <>
                    <span className="mx-0.5 h-4 w-px bg-border" aria-hidden="true" />
                    <Star className="fill-current" aria-hidden="true" />
                    <span className="tabular-nums">{formatGitHubStars(stars)}</span>
                  </>
                ) : null}
              </a>
            </Button>
            <Button asChild size="lg" variant="outline" className="px-4">
              <a href={normalizeDiscordUrl()} target="_blank" rel="noreferrer">
                <DiscordLogo />
                Join Discord
              </a>
            </Button>
          </div>

          {/* The stable address of the install (`/install` redirects here). */}
          <div id="install" className="mt-[clamp(0.75rem,2.7svh,1.5rem)] flex w-full max-w-[660px] scroll-mt-20 justify-center">
            <InstallBox />
          </div>
        </div>
      </div>

      {/* At the foot of the screen, a label over the agents' logos, no section title. Under the
          names, as much room as the label has over the glyphs (its 12px gap and the third of a tile
          above each glyph), so the strip closes the screen evenly: 36px under the 72px tiles, 40px
          under the 88px ones. */}
      <div id="agents" className="mx-auto w-full max-w-[1200px] scroll-mt-20 px-4 pb-9 sm:px-6 [@media(min-width:64rem)_and_(min-height:44rem)]:pb-10">
        <p className="text-center text-xs font-medium uppercase tracking-[0.14em] text-muted-foreground">
          WORKS WITH THESE AGENTS
        </p>
        <div className="mt-3">
          <AgentCarousel />
        </div>
      </div>
    </section>
  );
}
