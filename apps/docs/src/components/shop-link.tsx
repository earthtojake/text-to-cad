"use client";

import { track } from "@vercel/analytics";
import type { ComponentProps } from "react";

/** A Shop card's link out to a store: it records a "Shop click" event, with the product, in Vercel
 * Web Analytics (cookie-free, as the privacy policy says) as it opens the store. */
export function ShopLink({ product, ...props }: ComponentProps<"a"> & { product: string }) {
  return <a {...props} onClick={() => track("Shop click", { product })} />;
}
