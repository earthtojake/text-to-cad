import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/site";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      // The Shop's links are redirects out of the site (src/lib/shop-links.ts).
      disallow: "/go/",
    },
    sitemap: absoluteUrl("/sitemap.xml"),
  };
}
