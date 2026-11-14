import type { NextConfig } from "next";

// The UI calls /api/...; Next forwards it to the FastAPI server.
const API_URL = process.env.API_URL ?? "http://localhost:8010";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/:path*` }];
  },
};

export default nextConfig;
