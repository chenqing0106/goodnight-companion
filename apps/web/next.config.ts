import type { NextConfig } from "next";

const agentBackendUrl = (
  process.env.AGENT_BACKEND_URL ?? "http://127.0.0.1:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${agentBackendUrl}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${agentBackendUrl}/health`,
      },
    ];
  },
};

export default nextConfig;
