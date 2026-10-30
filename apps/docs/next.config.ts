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
  // texttocad.dev/install.sh and /install.ps1: the one-line installer, copied into public/ from
  // scripts/install/ as the site builds (scripts/install-scripts.mjs). Plain text, so `irm` hands
  // PowerShell a string and a browser shows the script; kept five minutes, so a release reaches
  // everyone soon after it deploys.
  async headers() {
    return ["/install.sh", "/install.ps1"].map((source) => ({
      source,
      headers: [
        { key: "Content-Type", value: "text/plain; charset=utf-8" },
        { key: "Cache-Control", value: "public, max-age=300" },
      ],
    }));
  },
};
export default nextConfig;
