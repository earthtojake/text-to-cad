import type { MetadataRoute } from "next";
import { docHref, docPages } from "@/lib/docs/nav";
import { absoluteUrl } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: absoluteUrl("/"),
      changeFrequency: "weekly",
      priority: 1,
    },
    // The documentation, each page of its map.
    ...docPages.map((page) => ({
      url: absoluteUrl(docHref(page.slug)),
      changeFrequency: "weekly" as const,
      priority: page.slug ? 0.7 : 0.9,
    })),
    {
      url: absoluteUrl("/icon"),
      changeFrequency: "monthly",
      priority: 0.2,
    },
    {
      url: absoluteUrl("/privacy-policy"),
      changeFrequency: "yearly",
      priority: 0.1,
    },
    {
      url: absoluteUrl("/terms-of-service"),
      changeFrequency: "yearly",
      priority: 0.1,
    },
  ];
}
