import Image from "next/image";
import wordmark from "../../public/brand/logo-texttocad.png";
import { HeroStepRender } from "@/components/hero-step-render";

export function HeroSection() {
  return (
    <section className="space-y-8">
      <div className="space-y-6 pt-4 sm:pt-6">
        <h1 className="sr-only">text-to-cad: Give your agent CAD superpowers</h1>
        <Image
          id="hero-wordmark"
          src={wordmark}
          alt=""
          priority
          className="h-auto w-full max-w-[800px]"
          sizes="(min-width: 848px) 800px, 100vw"
        />
        <p className="text-2xl font-semibold tracking-tight text-foreground sm:text-3xl lg:text-4xl">
          Give your agent CAD superpowers.{" "}
          <span className="text-brand">100% open source and free.</span>
        </p>
      </div>

      <div className="h-[260px] min-h-0 overflow-hidden rounded-xl border border-border bg-background sm:h-[300px] lg:h-[340px]">
        <HeroStepRender />
      </div>
    </section>
  );
}
