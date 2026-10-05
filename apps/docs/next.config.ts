import type { NextConfig } from "next";
import path from "node:path";

const repoRoot = path.resolve(process.cwd(), "../..");
const nextConfig: NextConfig = {
  allowedDevOrigins: ["127.0.0.1"],
  outputFileTracingRoot: repoRoot,
  transpilePackages: ["@text-to-cad/core"],
  images: { remotePatterns: [{ hostname: "www.skills.sh", protocol: "https" }] },
  turbopack: { root: repoRoot },
  // texttocad.dev/install: the stable link to the Install section, the full install instructions
  // the CAD app's update card links to (cadgen's `updates.INSTRUCTIONS`). Temporary, so it can move.
  async redirects() {
    return [{ source: "/install", destination: "/#install", permanent: false }];
  },
};
export default nextConfig;
