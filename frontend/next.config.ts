import type { NextConfig } from "next";

// The UI calls /api/...; Next forwards it to the FastAPI server.
const API_URL = process.env.API_URL ?? "http://localhost:8010";

const nextConfig: NextConfig = {
  // Queue evaluation can include model retries; Next's 30s default can cut
  // off the response while the backend is still saving audited evaluations.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
