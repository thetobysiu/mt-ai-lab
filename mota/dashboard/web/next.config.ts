import type { NextConfig } from "next";

// Static export: FastAPI serves web/out at /; no Node at runtime.
const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
