import type { MetadataRoute } from "next";

const SITE = "https://gng139.online";

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: `${SITE}/`, changeFrequency: "weekly", priority: 1 },
    { url: `${SITE}/signup`, changeFrequency: "monthly", priority: 0.6 },
    { url: `${SITE}/login`, changeFrequency: "yearly", priority: 0.3 },
  ];
}
