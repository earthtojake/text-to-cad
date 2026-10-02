import type { MetadataRoute } from "next";
import { absoluteUrl } from "@/lib/site";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: absoluteUrl("/"),
      changeFrequency: "weekly",
      priority: 1,
    },
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
