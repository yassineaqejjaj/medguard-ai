import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
  async rewrites() {
    // Dev convenience; in the compose stack Caddy routes /api to the API itself.
    return process.env.MEDGUARD_API_URL
      ? [{ source: "/api/:path*", destination: `${process.env.MEDGUARD_API_URL}/api/:path*` }]
      : [];
  },
};

export default nextConfig;
