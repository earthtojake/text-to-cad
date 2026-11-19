import type { Metadata } from "next";
import { ArrowRight } from "lucide-react";
import { SiteFooter } from "@/components/site-footer";
import { ShopLink } from "@/components/shop-link";
import { SiteHeader } from "@/components/site-header";
import { categories, type Product } from "@/lib/shop";
import { shopLinkHref } from "@/lib/shop-links";

export const metadata: Metadata = {
  title: "Shop",
  description: "Turn your text-to-cad designs into reality: the 3D printers to make them on.",
  alternates: { canonical: "/shop" },
};

// A product: its picture on a white panel, then its name, what it is the pick for, its specs and
// where to buy it. The whole card links to its store, and a click on it is counted (ShopLink).
function ProductCard({ product, category }: { product: Product; category: string }) {
  return (
    <li>
      <ShopLink
        product={product.slug}
        href={shopLinkHref(product.slug)}
        target="_blank"
        rel="noopener"
        className="group flex h-full flex-col overflow-hidden rounded-xl border border-border transition hover:border-foreground/30 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      >
        <div className="aspect-[4/3] bg-white">
          {/* eslint-disable-next-line @next/next/no-img-element -- small static files, no optimisation needed */}
          <img
            src={`/shop/${category}/${product.slug}.webp`}
            alt={product.name}
            loading="lazy"
            className="size-full object-contain p-6 transition duration-300 group-hover:scale-[1.03]"
          />
        </div>
        <div className="flex flex-1 flex-col gap-3 border-t border-border bg-muted/60 p-4">
          <div>
            <h3 className="font-medium text-foreground">{product.name}</h3>
            <p className="mt-0.5 text-sm text-muted-foreground">{product.bestFor}</p>
          </div>
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
            {product.specs.map((spec) => (
              <li key={spec}>{spec}</li>
            ))}
          </ul>
          <span className="mt-auto inline-flex items-center gap-1 text-sm font-medium text-primary">
            Buy now
            <ArrowRight className="size-3.5 transition group-hover:translate-x-0.5" aria-hidden />
          </span>
        </div>
      </ShopLink>
    </li>
  );
}

export default function ShopPage() {
  return (
    // The Shop is always light, like most stores: its product photos are shot on white.
    <main className="theme-light flex min-h-screen flex-col bg-background text-foreground">
      <SiteHeader />
      <div className="mx-auto w-full max-w-[1200px] flex-1 px-4 py-12 sm:px-6">
        <h1 className="text-3xl font-medium tracking-tight">Shop</h1>
        <p className="mt-2 text-muted-foreground">Turn your designs into reality.</p>

        {categories.map((category) => (
          <section key={category.id} id={category.id} className="mt-10 scroll-mt-20">
            <h2 className="text-xs font-medium uppercase tracking-widest text-muted-foreground">{category.title}</h2>
            <ul className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {category.products.map((product) => (
                <ProductCard key={product.slug} product={product} category={category.id} />
              ))}
            </ul>
          </section>
        ))}
      </div>
      <SiteFooter />
    </main>
  );
}
