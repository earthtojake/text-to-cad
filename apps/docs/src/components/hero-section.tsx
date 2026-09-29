import Link from "next/link";
import Image from "next/image";
import { Button } from "@/components/ui/button";
import { HeroStepRender } from "@/components/hero-step-render";

export function HeroSection() {
  return (
    <section className="space-y-8">
      <div className="space-y-6 pt-4 sm:pt-6">
        <h1 className="sr-only">text.to.cad</h1>
        <Image
          src="/brand/logo-text2cad.png"
          alt=""
          width={3157}
          height={512}
          priority
          className="h-auto w-full max-w-[800px]"
          sizes="(min-width: 848px) 800px, 100vw"
        />
        <div className="flex flex-col gap-6 sm:flex-row sm:items-end sm:justify-between">
          <div className="max-w-4xl space-y-3">
            <p className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl lg:text-4xl">
              Give your agent CAD superpowers.
            </p>
            <p className="text-lg leading-relaxed text-muted-foreground sm:text-xl">
              100% open source and free, runs locally with your favorite agent.
            </p>
          </div>
          <Button asChild size="lg" className="shrink-0 self-start px-5 sm:self-auto">
            <Link href="#installation">Get started</Link>
          </Button>
        </div>
      </div>

      <div className="h-[260px] min-h-0 overflow-hidden rounded-xl border border-border bg-background sm:h-[300px] lg:h-[340px]">
        <HeroStepRender />
      </div>
    </section>
  );
}
