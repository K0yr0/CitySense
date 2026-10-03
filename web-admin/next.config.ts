import type { NextConfig } from "next";

// Same-origin proxy to the FastAPI backend: with NEXT_PUBLIC_API_URL=/api the browser
// only talks to Next, which avoids CORS and mixed-content problems when a phone opens
// the app over an HTTPS tunnel (needed for /ride motion sensors).
const publicApi = process.env.NEXT_PUBLIC_API_URL ?? "";
const backend = (
  process.env.BACKEND_URL ||
  (publicApi.startsWith("http") ? publicApi : "") ||
  "http://localhost:8000"
).replace(/\/$/, "");

const nextConfig: NextConfig = {
  // Let phones on the LAN or a tunnel load the dev server (for the /ride demo).
  allowedDevOrigins: [
    "192.168.*.*",
    "10.*.*.*",
    "172.*.*.*",
    "*.ngrok-free.app",
    "*.ngrok.app",
    "*.trycloudflare.com",
  ],
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
};

export default nextConfig;
