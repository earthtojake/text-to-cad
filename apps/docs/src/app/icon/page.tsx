import type { Metadata } from "next";
import Image from "next/image";
import Link from "next/link";
import { IconPlayground } from "@/components/icon-playground";

export const metadata: Metadata = {
  title: "Icon",
  description: "Download the text-to-cad block logos and explore the original loading animation.",
  alternates: { canonical: "/icon" },
  openGraph: {
    title: "Icon | text-to-cad",
    description: "Download the text-to-cad block logos and explore the original loading animation.",
    url: "/icon",
    images: [{ url: "/favicon.png", width: 512, height: 512, alt: "Blue 3D text-to-cad icon" }],
  },
  twitter: {
    card: "summary",
    title: "Icon | text-to-cad",
    description: "Download the text-to-cad block logos and explore the original loading animation.",
    images: ["/favicon.png"],
  },
};

export default function IconPage() {
  return <>
    <main className="mx-auto max-w-5xl px-6 py-16">
      <Link href="/" className="text-sm text-muted-foreground">← text-to-cad</Link>
      <h1 className="mt-10 text-3xl font-medium tracking-tight">Built from blocks.</h1>
      <p className="mt-3 text-muted-foreground">Three blue marks, each two blocks deep. Download the SVGs at any size, or use the transparent PNGs.</p>
      <div className="mt-12 divide-y divide-border">
        {[
          { file: "logo-c", label: "C", width: 180, height: 240 },
          { file: "logo-cad", label: "CAD", width: 480, height: 240 },
          { file: "logo-text2cad", label: "TEXT2CAD", width: 880, height: 170 },
        ].map(({ file, label, width, height }) => (
          <section key={file} className="py-10">
            <Image src={`/brand/${file}.svg`} alt={`${label} block logo`} width={width} height={height}
              unoptimized className="h-auto max-w-full" />
            <a href={`/brand/${file}.svg`} download className="mt-6 inline-block text-sm text-muted-foreground underline underline-offset-4">Download {label} SVG</a>
            <a href={`/brand/${file}.png`} download className="ml-6 text-sm text-muted-foreground underline underline-offset-4">PNG</a>
          </section>
        ))}
      </div>
      <h2 className="mt-12 text-xl font-medium">The loading icon</h2>
      <p className="mt-2 text-muted-foreground">Our original animated mark stays with us while models load.</p>
    </main>
    <IconPlayground />
  </>;
}
