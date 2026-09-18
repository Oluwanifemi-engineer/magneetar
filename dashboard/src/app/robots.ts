import type { MetadataRoute } from "next";

// This route is the single source of truth for /robots.txt: it is what
// `next build` writes to out/robots.txt, and Next's generated page wins over
// any dashboard/public/robots.txt (which is why that hand-written copy was
// deleted — its extra rules never reached production).
const DISALLOW = ["/dashboard/", "/admin/", "/api/", "/login", "/signup", "/apk/"];

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: DISALLOW,
      },
      {
        userAgent: "Googlebot",
        allow: "/",
        disallow: DISALLOW,
      },
    ],
    sitemap: "https://magneetar.me/sitemap.xml",
  };
}
