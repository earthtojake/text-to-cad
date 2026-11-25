/**
 * Where each Shop product is bought: a card links `/go/<slug>`, and the site redirects it to the
 * product's page on its store (next.config.ts). A store's address is written once, here, so it can
 * change without touching the page. `/go/` is kept from crawlers (app/robots.ts).
 */
export const shopLinks = {
  "bambu-lab-a1-mini": "https://us.store.bambulab.com/products/a1-mini",
  "bambu-lab-a1": "https://us.store.bambulab.com/products/a1",
  "bambu-lab-h2d": "https://us.store.bambulab.com/products/h2d",
  "prusa-mk4s": "https://www.prusa3d.com/product/original-prusa-mk4s-3d-printer-5/",
  "prusa-core-one-l": "https://www.prusa3d.com/product/prusa-core-one-l-2/",
  "anycubic-kobra-s1-max": "https://store.anycubic.com/products/kobra-s1-max-combo",
  "snapmaker-u1": "https://us.snapmaker.com/products/snapmaker-u1-3d-printer",
  "bambu-lab-p2s": "https://us.store.bambulab.com/products/p2s",
  "prusa-core-one-plus": "https://www.prusa3d.com/product/prusa-core-one/",
  "creality-k2-plus": "https://store.creality.com/products/creality-k2-plus-combo-3d-printer",
  "elegoo-centauri-carbon-2": "https://elegoo.sjv.io/c/8271003/1692726/19663?u=https%3A%2F%2Fus.elegoo.com%2Fproducts%2Fcentauri-carbon-2-combo",
  "anycubic-kobra-s1": "https://store.anycubic.com/products/kobra-s1-ace-2-pro-combo-3d-printer",
} as const;

export type ShopSlug = keyof typeof shopLinks;

export const SHOP_LINK_PREFIX = "/go/";

export const shopLinkHref = (slug: ShopSlug) => `${SHOP_LINK_PREFIX}${slug}`;
