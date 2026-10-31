import { Star } from "lucide-react";
import { DiscordLogo, GitHubLogo } from "@/components/brand-marks";
import { HeroGlbRender } from "@/components/hero-glb-render";
import { InstallBox } from "@/components/install-box";
import { LogoBuild } from "@/components/logo-build";
import { Button } from "@/components/ui/button";
import {
  formatGitHubStars,
  getGitHubStars,
  GITHUB_REPO_URL,
  normalizeDiscordUrl,
} from "@/lib/github";

/** The homepage's hero, centred: the TEXTTOCAD wordmark and the tagline, the two calls to action
 * (GitHub with its stars, Join Discord), the one-line install -- the page's Install, at `#install`
 * -- then the framed CAD demo. */
export async function HeroSection() {
  const stars = await getGitHubStars();

  return (
    <section className="flex flex-col items-center text-center">
      <div className="flex w-full flex-col items-center space-y-6 pt-4 sm:pt-6">
        <h1 className="sr-only">text-to-cad: Design physical products with AI.</h1>
        {/* A block of its own, so the centred column does not shrink the wordmark to fit. */}
        <div className="w-full max-w-[800px]">
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
        <p className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl lg:text-4xl">
          Design physical products with AI.{" "}
          <span className="text-brand">100% open source and free.</span>
        </p>
      </div>

      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
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

      {/* The stable address of the install (`/install` redirects here; the CAD app's update card links it). */}
      <div id="install" className="mt-6 flex w-full max-w-[660px] scroll-mt-20 justify-center">
        <InstallBox />
      </div>

      <div className="mt-10 h-[260px] min-h-0 w-full overflow-hidden rounded-xl border border-border bg-background sm:h-[300px] lg:h-[340px]">
        <HeroGlbRender />
      </div>
    </section>
  );
}
