import type { MetadataRoute } from "next";

// Public marketing pages are crawlable; the product, admin and auth flows are not.
export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: "/",
      disallow: [
        "/app",
        "/admin",
        "/api",
        "/design",
        "/dev-auto-login",
        "/forgot-password",
        "/reset-password",
        "/verify",
      ],
    },
    sitemap: "https://gng139.online/sitemap.xml",
  };
}
