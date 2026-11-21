import type { ShopSlug } from "@/lib/shop-links";

/**
 * The Shop page (/shop): a section a category, a card a product, each chosen for what it is best
 * at. A product's picture is `public/shop/<category>/<slug>.webp`, an 800 px square, the product on
 * white. Its slug names its store link (src/lib/shop-links.ts). A category is added after the last.
 */
export type Product = {
  slug: ShopSlug;
  /** The maker and the model, as the maker names it. */
  name: string;
  /** What it is the pick for, in a few words. */
  bestFor: string;
  /** Facts a buyer compares, a few words each. */
  specs: string[];
};

export type Category = { id: string; title: string; products: Product[] };

export const categories: Category[] = [
  {
    id: "printers",
    title: "3D printers",
    // From a first printer to large format, then by what each is the pick for.
    products: [
      { slug: "bambu-lab-a1-mini", name: "Bambu Lab A1 mini", bestFor: "Best to start with", specs: ["180 mm cube", "Open frame"] },
      { slug: "bambu-lab-a1", name: "Bambu Lab A1", bestFor: "Best budget full-size", specs: ["256 mm cube", "Open frame"] },
      { slug: "prusa-mk4s", name: "Prusa MK4S", bestFor: "Best open-frame workhorse", specs: ["250 × 210 × 220 mm", "Open frame"] },
      { slug: "bambu-lab-p2s", name: "Bambu Lab P2S", bestFor: "Best all-rounder", specs: ["256 mm cube", "Enclosed"] },
      { slug: "elegoo-centauri-carbon-2", name: "Elegoo Centauri Carbon 2", bestFor: "Best value enclosed", specs: ["256 mm cube", "Enclosed"] },
      { slug: "prusa-core-one-plus", name: "Prusa CORE One+", bestFor: "Best open-source printer", specs: ["250 × 220 × 270 mm", "Enclosed"] },
      { slug: "anycubic-kobra-s1", name: "Anycubic Kobra S1", bestFor: "Best for multi-colour", specs: ["250 mm cube", "Enclosed"] },
      { slug: "snapmaker-u1", name: "Snapmaker U1", bestFor: "Best for multi-material", specs: ["270 mm cube", "Four toolheads"] },
      { slug: "bambu-lab-h2d", name: "Bambu Lab H2D", bestFor: "Best for professionals", specs: ["350 × 320 × 325 mm", "Two nozzles"] },
      { slug: "prusa-core-one-l", name: "Prusa CORE One L+", bestFor: "Best large open-source printer", specs: ["300 × 300 × 330 mm", "Enclosed"] },
      { slug: "creality-k2-plus", name: "Creality K2 Plus Combo", bestFor: "Best for big parts", specs: ["350 mm cube", "Enclosed"] },
      { slug: "anycubic-kobra-s1-max", name: "Anycubic Kobra S1 Max", bestFor: "Best large multi-colour", specs: ["350 mm cube", "Enclosed"] },
    ],
  },
];
