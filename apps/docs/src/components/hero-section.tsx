import Link from "next/link";
import { Button } from "@/components/ui/button";
import Image from "next/image";
import { HeroStepRender } from "@/components/hero-step-render";

function HeroSubtitle({ className = "" }: { className?: string }) {
  return (
    <p
      className={`text-[15px] font-medium leading-6 text-foreground sm:text-[17px] sm:leading-7 lg:text-[19px] lg:leading-8 ${className}`}
    >
      Give your agent CAD superpowers.{" "}
      <span className="mt-2 block text-sm font-normal leading-6 text-muted-foreground">
        100% open source + free, runs locally
      </span>
    </p>
  );
}

export function HeroSection() {
  return (
    <section className="overflow-hidden rounded-xl border border-border bg-card shadow-sm">
      {/* Wordmark and byline stack on smaller screens. */}
      <div className="grid min-w-0 lg:grid-cols-3">
        <div className="flex min-w-0 items-center px-4 py-4 sm:px-5 lg:col-span-2 lg:min-h-[156px] lg:px-6 lg:py-5">
          <h1 className="sr-only">text.to.cad</h1>
          <Image
            src="/brand/logo-text2cad.png"
            alt=""
            width={3157}
            height={512}
            priority
            className="h-auto w-full"
            sizes="(min-width: 1200px) 750px, (min-width: 1024px) 65vw, 100vw"
          />
        </div>

        <div className="flex min-w-0 items-center border-t border-border px-4 py-4 sm:px-5 lg:col-span-1 lg:min-h-[156px] lg:border-l lg:border-t-0 lg:px-6 lg:py-5">
          <div className="space-y-4">
            <HeroSubtitle className="w-full" />
            <Button asChild className="px-4">
              <Link href="#installation">Get started</Link>
            </Button>
          </div>
        </div>
      </div>

      <div className="h-[260px] min-h-0 border-t border-border bg-background sm:h-[300px] lg:h-[340px]">
        <HeroStepRender />
      </div>
    </section>
  );
}
