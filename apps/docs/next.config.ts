import type { NextConfig } from "next";
import path from "node:path";

const repoRoot = path.resolve(process.cwd(), "../..");
const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  outputFileTracingRoot: repoRoot,
  transpilePackages: ["@hardcore/core"],
  images: { remotePatterns: [{ hostname: "www.skills.sh", protocol: "https" }] },
  turbopack: { root: repoRoot },
};
export default nextConfig;
